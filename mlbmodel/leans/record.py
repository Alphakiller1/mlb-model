"""Persist model leans from a report build (idempotent upsert)."""
from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from mlbmodel import settings
from mlbmodel.storage.supabase import SupabaseWriter

log = logging.getLogger(__name__)
MODEL_VERSION = settings.MODEL_VERSION

# Minimum model edge (percentage points) to record as a lean.
MIN_EDGE_PTS = 0.5
# Pick'em rows below this distance from 50% are still stored but tagged WATCH.
PICKEM_LEAN_PTS = 8.0

_PROJECTION_PROPS = ("K", "BB", "ER", "Outs", "H", "Fantasy", "F5_ER", "PP_Fantasy")
_PRESERVED_STATES = {"BET", "MONITOR", "STRONG", "LEAN", "REVIEW", "AVOID"}
_MARKET_ALIASES = {
    "moneyline": "ml",
    "h2h": "ml",
    "ml": "ml",
    "total": "total",
    "totals": "total",
    "spread": "runline",
    "spreads": "runline",
    "run_line": "runline",
    "runline": "runline",
}


def _pitcher_key(pitcher: dict) -> str:
    name = str(pitcher.get("pitcher") or pitcher.get("pitcher_name") or "").strip()
    if not name:
        pid = pitcher.get("pitcher_id")
        return f"id:{pid}" if pid is not None else "unknown"
    return name.lower().replace(" ", "_")


def _projection_lean_tag(trust: str | None) -> str:
    trust = str(trust or "").lower()
    if trust == "thin":
        return "PROJECTION_THIN"
    if trust == "trusted":
        return "PROJECTION"
    return "PROJECTION"


def _row(
    *,
    slate_date: str,
    game_pk: int | None,
    source: str,
    market: str,
    selection: str,
    line: float | None,
    model_value: float | None,
    model_prob: float | None,
    edge: float | None,
    lean: str,
    entry_odds: float | None = None,
    pitcher_name: str | None = None,
) -> dict:
    row = {
        "slate_date": slate_date,
        "game_pk": game_pk,
        "source": source,
        "market": market,
        "selection": selection,
        "line": line,
        "model_value": model_value,
        "model_prob": model_prob,
        "edge": edge,
        "lean": lean,
        "model_version": MODEL_VERSION,
        "sport": "mlb",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "settled": False,
        # PostgREST batch upserts require identical keys on every object.
        "entry_odds": entry_odds,
        "pitcher_name": pitcher_name or None,
    }
    return row


def edge_points(edge) -> float | None:
    """Normalize edge to percentage points (model% − market%)."""
    if edge is None:
        return None
    try:
        value = float(edge)
    except (TypeError, ValueError):
        return None
    return value * 100 if abs(value) <= 1 else value


def _market_line(play: dict) -> float | None:
    raw = play.get("market_line")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _entry_odds(play: dict) -> float | None:
    raw = play.get("entry_odds", play.get("price"))
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _canonical_market(market: str) -> str:
    key = str(market or "market").strip().lower()
    if key.startswith("f5_"):
        suffix = _MARKET_ALIASES.get(key[3:], key[3:])
        return f"f5_{suffix}"
    return _MARKET_ALIASES.get(key, key)


def _lean_label(state: str, edge_pts: float | None) -> str:
    state = str(state or "").upper().replace("-", " ")
    if state == "PROJECTION":
        return "PROJECTION"
    if state in _PRESERVED_STATES:
        return state
    if state in {"NO EDGE", "NO PRICE"} and edge_pts is None:
        return "PROJECTION"
    if edge_pts is not None and edge_pts >= 2.0:
        return "LEAN"
    if edge_pts is not None and edge_pts >= MIN_EDGE_PTS:
        return "EDGE"
    return "WATCH"


def _collect_sharp_plays(slate_date: str, market_plays: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for play in market_plays:
        verdict = str(play.get("verdict") or "")
        if verdict not in {"STRONG", "BET", "LEAN"}:
            continue
        pk = play.get("pk")
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=int(pk) if pk is not None else None,
                source="sharp",
                market=str(play.get("mkt_type") or "market"),
                selection=str(play.get("sel") or ""),
                line=_market_line(play),
                entry_odds=_entry_odds(play),
                model_value=play.get("model_p"),
                model_prob=(
                    float(play["model_p"]) / 100
                    if play.get("model_p") is not None else None
                ),
                edge=play.get("medge"),
                lean=verdict,
            )
        )
    return rows


def _collect_matchup_markets(
    slate_date: str,
    matchup_markets_by_pk: dict[int, list[dict]],
) -> list[dict]:
    """Record every model-graded game and F5 market (ML, total, runline), priced or not."""
    rows: list[dict] = []
    for pk, markets in (matchup_markets_by_pk or {}).items():
        game_pk = int(pk) if pk is not None else None
        for market in markets or []:
            model_pct = market.get("model")
            if model_pct is None:
                continue
            state = str(market.get("state") or "")
            edge_pts = edge_points(market.get("edge"))
            market_type = _canonical_market(str(market.get("market") or "market"))
            source = "f5" if market_type.startswith("f5_") else "matchup"
            rows.append(
                _row(
                    slate_date=slate_date,
                    game_pk=game_pk,
                    source=source,
                    market=market_type,
                    selection=str(market.get("side") or ""),
                    line=float(market["line"]) if market.get("line") is not None else None,
                    model_value=model_pct,
                    model_prob=float(model_pct) / 100,
                    edge=edge_pts,
                    lean=_lean_label(state, edge_pts),
                    entry_odds=(
                        float(market["mkt"])
                        # bool is an int subclass; JSON round-trips often float odds.
                        if isinstance(market.get("mkt"), (int, float))
                        and not isinstance(market.get("mkt"), bool) else None
                    ),
                )
            )
    return rows


def _collect_pickem(
    slate_date: str,
    pickem_rows: list[dict],
    fresh_books: set[str] | None = None,
) -> list[dict]:
    """Record pick'em prop leans only when the source snapshot is fresh."""
    rows: list[dict] = []
    stale = 0
    for item in pickem_rows:
        lean = str(item.get("lean") or "").upper()
        if lean not in {"OVER", "UNDER"}:
            continue
        book = str(item.get("book") or "pickem").lower()
        is_fresh = fresh_books is None or book in fresh_books
        if not is_fresh:
            stale += 1
            continue
        edge_pts = item.get("edge_pts")
        if edge_pts is None and item.get("p_over") is not None:
            edge_pts = abs(float(item["p_over"]) - 0.5) * 100
        if (edge_pts or 0) >= PICKEM_LEAN_PTS:
            lean_tag = lean
        else:
            lean_tag = "WATCH"
        prop = str(item.get("prop") or "prop")
        market = prop.lower().replace(" ", "_")
        if market == "fantasy":
            market = "fantasy_score"
        # `model_prob` must be the probability of the SELECTION that was recorded, the way
        # every other source stores it — otherwise a graded UNDER is scored against P(over)
        # and the reliability curve is inverted for that whole source. Every one of the 92
        # graded pick'em UNDER rows in the ledger carried a probability below 0.5 while the
        # projection sat below the line, i.e. the pick was the likely side and the stored
        # number said the opposite.
        p_over = item.get("p_over")
        model_probability = (
            None if p_over is None
            else float(p_over) if lean == "OVER"
            else 1.0 - float(p_over)
        )
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=item.get("game_pk"),
                source=book,
                market=market,
                selection=lean.lower(),
                line=float(item["line"]) if item.get("line") is not None else None,
                model_value=item.get("projection"),
                model_prob=model_probability,
                edge=edge_pts,
                lean=lean_tag,
                pitcher_name=str(item.get("pitcher") or "") or None,
            )
        )
    if stale:
        log.warning(
            "pick'em: excluded %s stale line snapshot(s) from the lean ledger",
            stale,
        )
    return rows


def _collect_prop_leans(slate_date: str, prop_reports: list[dict]) -> list[dict]:
    """Record every sportsbook prop row the engine evaluated."""
    rows: list[dict] = []
    for item in prop_reports:
        prop = str(item.get("prop") or "").strip()
        if not prop:
            continue
        edge_pts = edge_points(item.get("edge"))
        state = str(item.get("state") or item.get("market_state") or "")
        side = str(item.get("side") or "model").lower()
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=item.get("game_pk"),
                source="prop",
                market=prop.lower(),
                selection=side,
                line=float(item["line"]) if item.get("line") is not None else None,
                model_value=item.get("model_mean"),
                model_prob=item.get("model_probability"),
                edge=edge_pts,
                lean=_lean_label(state, edge_pts),
                entry_odds=(
                    float(item["best_odds"])
                    if item.get("best_odds") is not None else None
                ),
                pitcher_name=str(item.get("pitcher") or "") or None,
            )
        )
    return rows


def _collect_pitcher_projections(slate_date: str, pitchers: list[dict]) -> list[dict]:
    """Log every simulated projection mean for each slate starter."""
    rows: list[dict] = []
    for pitcher in pitchers or []:
        projections = pitcher.get("projections") or {}
        if not projections:
            continue
        lean_tag = _projection_lean_tag(pitcher.get("projection_trust"))
        pitcher_key = _pitcher_key(pitcher)
        for prop in _PROJECTION_PROPS:
            dist = projections.get(prop)
            if not dist or dist.get("mean") is None:
                continue
            market = str(prop).lower()
            if market == "pp_fantasy":
                market = "fantasy_score"
            rows.append(
                _row(
                    slate_date=slate_date,
                    game_pk=pitcher.get("game_pk"),
                    source="projection",
                    market=market,
                    selection=f"model:{pitcher_key}",
                    line=None,
                    model_value=float(dist["mean"]),
                    model_prob=None,
                    edge=None,
                    lean=lean_tag,
                    pitcher_name=str(pitcher.get("pitcher") or "") or None,
                )
            )
    return rows


def collect_leans(
    *,
    slate_date: str,
    market_plays: list[dict],
    pickem_rows: list[dict],
    prop_reports: list[dict],
    matchup_markets_by_pk: dict[int, list[dict]] | None = None,
    pitchers: list[dict] | None = None,
    pkmap: dict[int, str] | None = None,
    fresh_pickem_books: set[str] | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """Gather lean dicts from sharp fusion, matchup/F5, props, pick'em, and projections."""
    _ = pkmap  # reserved for future game-key enrichment
    rows: list[dict] = []
    rows.extend(_collect_sharp_plays(slate_date, market_plays))
    rows.extend(_collect_matchup_markets(slate_date, matchup_markets_by_pk or {}))
    rows.extend(_collect_pickem(slate_date, pickem_rows, fresh_books=fresh_pickem_books))
    rows.extend(_collect_prop_leans(slate_date, prop_reports))
    rows.extend(_collect_pitcher_projections(slate_date, pitchers or []))
    build_run = run_id or uuid.uuid4().hex[:12]
    for row in rows:
        row["run_id"] = build_run
    return rows


def write_lean_snapshot(rows: list[dict], path: Path | None = None) -> Path:
    """Persist the collected ledger locally so a run still records without warehouse creds."""
    dest = path or (settings.CACHE_DIR / "model_leans_latest.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    by_source = Counter(str(row.get("source") or "") for row in rows)
    by_market = Counter(str(row.get("market") or "") for row in rows)
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(rows),
        "by_source": dict(sorted(by_source.items())),
        "by_market": dict(sorted(by_market.items())),
        "rows": rows,
    }
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Also keep a per-slate copy. `model_leans_latest.json` is overwritten every run, so a
    # warehouse write that fails is unrecoverable once the next build starts — which is how
    # a 336-lean slate ended up existing only as a file nobody could replay. These accumulate
    # and are what `scripts/replay_leans.py` reads.
    slate_dates = {str(row.get("slate_date") or "") for row in rows} - {""}
    if len(slate_dates) == 1:
        archive = dest.parent / "lean_snapshots"
        try:
            archive.mkdir(parents=True, exist_ok=True)
            (archive / f"{slate_dates.pop()}.json").write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:  # never let archiving break a build
            log.warning("lean snapshot archive failed: %s", exc)
    return dest


def record_leans(
    rows: list[dict],
    *,
    writer: SupabaseWriter | None = None,
    snapshot_path: Path | None | bool = None,
) -> int:
    """Upsert leans; returns warehouse count written. Always writes a local snapshot.

    ``snapshot_path=False`` skips the local file (tests). ``None`` uses CACHE_DIR.
    """
    if not rows:
        return 0
    if snapshot_path is not False:
        try:
            dest = snapshot_path if isinstance(snapshot_path, Path) else None
            write_lean_snapshot(rows, dest)
        except OSError as exc:
            log.warning("lean snapshot write failed: %s", exc)
    writer = writer or SupabaseWriter()
    if not writer.url or not writer.key:
        return 0
    return writer.upsert(
        "model_leans",
        rows,
        on_conflict="slate_date,game_pk,source,market,selection,line",
    )
