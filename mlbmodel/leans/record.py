"""Persist model leans from a report build (idempotent upsert)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from mlbmodel import settings
from mlbmodel.storage.supabase import SupabaseWriter

log = logging.getLogger(__name__)
MODEL_VERSION = settings.MODEL_VERSION

# Minimum model edge (percentage points) to record as a lean.
MIN_EDGE_PTS = 0.5
# Pick'em rows below this distance from 50% are still stored but tagged WATCH.
PICKEM_LEAN_PTS = 8.0

_PROJECTION_PROPS = ("K", "BB", "ER", "Outs", "H", "Fantasy", "F5_ER", "PP_Fantasy")


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


def _lean_label(state: str, edge_pts: float | None) -> str:
    state = str(state or "").upper()
    if state in {"BET", "MONITOR", "STRONG", "LEAN"}:
        return state
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
    """Model-graded game and F5 markets with a positive edge or actionable state."""
    rows: list[dict] = []
    for pk, markets in (matchup_markets_by_pk or {}).items():
        game_pk = int(pk) if pk is not None else None
        for market in markets or []:
            state = str(market.get("state") or "")
            edge_pts = edge_points(market.get("edge"))
            actionable = state in {"BET", "MONITOR"}
            has_edge = edge_pts is not None and edge_pts >= MIN_EDGE_PTS
            if not actionable and not has_edge:
                continue
            market_type = str(market.get("market") or "market").lower()
            source = "f5" if market_type.startswith("f5_") else "matchup"
            model_pct = market.get("model")
            rows.append(
                _row(
                    slate_date=slate_date,
                    game_pk=game_pk,
                    source=source,
                    market=market_type,
                    selection=str(market.get("side") or ""),
                    line=float(market["line"]) if market.get("line") is not None else None,
                    model_value=model_pct,
                    model_prob=(
                        float(model_pct) / 100
                        if model_pct is not None else None
                    ),
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
    """Pick'em leans. When `fresh_books` is given, rows from books whose line
    snapshot is stale for this slate are NOT recorded — grading a lean against
    a line nobody could actually bet contaminates the track record."""
    rows: list[dict] = []
    skipped_stale = 0
    for item in pickem_rows:
        lean = str(item.get("lean") or "").upper()
        if lean not in {"OVER", "UNDER"}:
            continue
        book = str(item.get("book") or "pickem").lower()
        if fresh_books is not None and book not in fresh_books:
            skipped_stale += 1
            continue
        edge_pts = item.get("edge_pts")
        if edge_pts is None and item.get("p_over") is not None:
            edge_pts = abs(float(item["p_over"]) - 0.5) * 100
        lean_tag = lean if (edge_pts or 0) >= PICKEM_LEAN_PTS else "WATCH"
        prop = str(item.get("prop") or "prop")
        market = prop.lower().replace(" ", "_")
        if market == "fantasy":
            market = "fantasy_score"
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=item.get("game_pk"),
                source=book,
                market=market,
                selection=lean.lower(),
                line=float(item["line"]) if item.get("line") is not None else None,
                model_value=item.get("projection"),
                model_prob=item.get("p_over"),
                edge=edge_pts,
                lean=lean_tag,
                pitcher_name=str(item.get("pitcher") or "") or None,
            )
        )
    if skipped_stale:
        log.warning(
            "pick'em: skipped %s lean(s) from stale line snapshots (fresh books: %s)",
            skipped_stale,
            ", ".join(sorted(fresh_books or set())) or "none",
        )
    return rows


def _collect_prop_edges(slate_date: str, prop_reports: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in prop_reports:
        edge_pts = edge_points(item.get("edge"))
        state = str(item.get("state") or "")
        actionable = state in {"BET", "MONITOR"}
        has_edge = edge_pts is not None and edge_pts >= MIN_EDGE_PTS
        if not actionable and not has_edge:
            continue
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=item.get("game_pk"),
                source="prop",
                market=str(item.get("prop") or "prop").lower(),
                selection=str(item.get("side") or ""),
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
    """Log trusted model projection means for each pitcher stat."""
    rows: list[dict] = []
    for pitcher in pitchers:
        if pitcher.get("projection_trust") != "trusted":
            continue
        projections = pitcher.get("projections") or {}
        for prop in _PROJECTION_PROPS:
            dist = projections.get(prop)
            if not dist or dist.get("mean") is None:
                continue
            market = prop.lower()
            if market == "pp_fantasy":
                market = "fantasy_score"
            rows.append(
                _row(
                    slate_date=slate_date,
                    game_pk=pitcher.get("game_pk"),
                    source="projection",
                    market=market,
                    selection="model",
                    line=None,
                    model_value=float(dist["mean"]),
                    model_prob=None,
                    edge=None,
                    lean="PROJECTION",
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
    rows.extend(_collect_prop_edges(slate_date, prop_reports))
    rows.extend(_collect_pitcher_projections(slate_date, pitchers or []))
    build_run = run_id or uuid.uuid4().hex[:12]
    for row in rows:
        row["run_id"] = build_run
    return rows


def record_leans(rows: list[dict], *, writer: SupabaseWriter | None = None) -> int:
    """Upsert leans; returns count written. Skips gracefully without credentials."""
    if not rows:
        return 0
    writer = writer or SupabaseWriter()
    if not writer.url or not writer.key:
        return 0
    return writer.upsert(
        "model_leans",
        rows,
        on_conflict="slate_date,game_pk,source,market,selection,line",
    )
