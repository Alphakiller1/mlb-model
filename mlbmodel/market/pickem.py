"""Pick'em board rows from cached DFS lines + model projections."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from mlbmodel.market import prizepicks
from mlbmodel.market.probability import p_over_line_erf, p_over_line_normal
from mlbmodel import settings

log = logging.getLogger(__name__)

PICKEM_BOOKS = ("prizepicks", "underdog", "sleeper")
_PICKEM_ORDER = ["PP_Fantasy", "K", "Outs", "ER", "H", "BB"]
_PICKEM_LEAN_PTS = 8.0


def load_pickem_lines(
    loader,
    cache_path: Path,
    *,
    fetch: bool = False,
    fallback_path: Path | None = None,
) -> list[dict]:
    """Load pick'em lines: live fetch when asked, then cache, then bundled snapshot."""
    lines, _ = load_pickem_lines_with_meta(
        loader, cache_path, fetch=fetch, fallback_path=fallback_path
    )
    return lines


def load_pickem_lines_with_meta(
    loader,
    cache_path: Path,
    *,
    fetch: bool = False,
    fallback_path: Path | None = None,
) -> tuple[list[dict], str | None]:
    """Like load_pickem_lines, but also returns the snapshot timestamp (None = undated/stale)."""
    from mlbmodel.market.lines_cache import read_lines_cache

    cache_path = Path(cache_path)
    if fetch:
        try:
            lines = loader.fetch_lines(cache_path)
            if lines:
                log.info("pick'em %s: fetched %s live lines", cache_path.name, len(lines))
                _, snapshot_at = read_lines_cache(cache_path)
                return lines, snapshot_at
        except Exception as exc:
            log.warning("pick'em %s live fetch failed: %s", cache_path.name, exc)
    lines, snapshot_at = read_lines_cache(cache_path)
    if lines:
        return lines, snapshot_at
    if fallback_path is None:
        fallback_path = settings.ROOT / "deployment_data" / cache_path.name
    fallback_path = Path(fallback_path)
    if fallback_path != cache_path:
        lines, snapshot_at = read_lines_cache(fallback_path)
        if lines:
            log.info(
                "pick'em %s: using fallback snapshot (%s lines)",
                cache_path.name,
                len(lines),
            )
            return lines, snapshot_at
    return [], None


def fresh_pickem_books(snapshots: dict[str, str | None], slate_date: str | None) -> set[str]:
    """Books whose line snapshot was taken on/after the slate date — only these
    may record leans. Undated (legacy committed) snapshots are never fresh."""
    from mlbmodel.market.lines_cache import snapshot_is_fresh

    return {
        book.lower()
        for book, snapshot_at in snapshots.items()
        if snapshot_is_fresh(snapshot_at, slate_date)
    }


def _load_cache(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return payload
    return list(payload.get("lines") or payload.get("rows") or [])


def _p_over(mean: float, sd: float, line: float) -> float:
    return p_over_line_normal(line, mean, sd)


def _p_over_erf(line: float, mean: float, sd: float) -> float:
    return p_over_line_erf(line, mean, sd)


def pickem_market_reports(
    pitcher: dict,
    sources: list[tuple[str, dict]],
    *,
    lean_threshold_pts: float = _PICKEM_LEAN_PTS,
) -> list[dict]:
    """Sportsbook-shaped market rows from pick'em lines when Odds API props are absent."""
    name_key = prizepicks.normalize_name(pitcher.get("pitcher"))
    projections = pitcher.get("projections") or {}
    reports: list[dict] = []
    for label, board in sources:
        lines = board.get(name_key, {})
        if not lines:
            continue
        book = label.lower()
        for key in _PICKEM_ORDER:
            line_obj, proj = lines.get(key), projections.get(key)
            if not line_obj or not proj:
                continue
            line = float(line_obj["line"])
            mean, sd = proj.get("mean"), proj.get("sd")
            p_over = _p_over_erf(line, mean, sd or 0)
            lean = "OVER" if p_over >= 0.5 else "UNDER"
            edge_pts = abs(p_over - 0.5) * 100
            model_probability = p_over if lean == "OVER" else 1 - p_over
            edge = (p_over - 0.5) if lean == "OVER" else (0.5 - p_over)
            state = lean if edge_pts >= lean_threshold_pts else "WATCH"
            reports.append(
                {
                    "prop": key,
                    "side": lean.lower(),
                    "line": line,
                    "best_odds": None,
                    "best_book": book,
                    "books": 1,
                    "model_probability": round(model_probability, 4),
                    "market_probability": None,
                    "edge": round(edge, 4),
                    "state": state,
                    "source": "pickem",
                }
            )
    return sorted(
        reports,
        key=lambda row: (-(row.get("edge") or 0), row["prop"], row["side"]),
    )


def build_pickem_rows_from_boards(
    pitchers: list[dict],
    sources: list[tuple[str, dict]],
) -> list[dict]:
    """Structured pick'em rows from PrizePicks/Underdog/Sleeper boards (main app parity)."""
    rows: list[dict] = []
    for row in pitchers:
        name_key = prizepicks.normalize_name(row.get("pitcher"))
        projections = row.get("projections") or {}
        game_pk = row.get("game_pk")
        for label, board in sources:
            lines = board.get(name_key, {})
            if not lines:
                continue
            book = label.lower()
            for key in _PICKEM_ORDER:
                line, proj = lines.get(key), projections.get(key)
                if not line or not proj:
                    continue
                mean, sd = proj.get("mean"), proj.get("sd")
                p_over = _p_over_erf(line["line"], mean, sd or 0)
                lean = "OVER" if p_over >= 0.5 else "UNDER"
                prop = prizepicks.STAT_LABEL.get(key, key)
                rows.append({
                    "pitcher": str(row.get("pitcher") or ""),
                    "team": str(row.get("team") or ""),
                    "opponent": str(row.get("opponent") or ""),
                    "game_pk": game_pk,
                    "book": book,
                    "prop": prop,
                    "line": float(line["line"]),
                    "projection": float(mean),
                    "p_over": round(p_over, 4),
                    "lean": lean,
                    "edge_pts": abs(p_over - 0.5) * 100,
                })
    return rows


def build_pickem_rows(
    pitchers: list[dict],
    *,
    cache_path: Path | None = None,
) -> list[dict]:
    """Build pick'em rows: one per book/market/pitcher when a line exists."""
    if cache_path is None:
        cache_dir = Path(settings.CACHE_DIR) if settings.CACHE_DIR else None
        if cache_dir:
            cache_path = cache_dir / "pickem_odds_latest.json"

    cached = _load_cache(cache_path)
    rows: list[dict] = []

    if cached:
        for item in cached:
            rows.append(dict(item))
        return rows

    # Fallback: synthesize from sportsbook prop snapshots embedded in pitcher market_report
    for pitcher in pitchers:
        if pitcher.get("projection_trust") != "trusted":
            continue
        name = str(pitcher.get("pitcher") or "")
        team = str(pitcher.get("team") or "")
        opp = str(pitcher.get("opponent") or "")
        game_pk = pitcher.get("game_pk")
        for report in pitcher.get("market_report") or []:
            prop = str(report.get("prop") or "")
            line = report.get("line")
            if line is None:
                continue
            dist = (pitcher.get("projections") or {}).get(prop) or {}
            mean = dist.get("mean")
            sd = dist.get("sd")
            if mean is None:
                continue
            p_over = _p_over(float(mean), float(sd or 1.0), float(line))
            lean = "OVER" if p_over >= 0.5 else "UNDER"
            book = str(report.get("best_book") or "sportsbook").lower()
            rows.append({
                "pitcher": name,
                "team": team,
                "opponent": opp,
                "game_pk": game_pk,
                "book": book,
                "prop": prop,
                "line": float(line),
                "projection": float(mean),
                "p_over": round(p_over, 4),
                "lean": lean,
                "edge_pts": abs(p_over - 0.5) * 100,
            })
    return rows


def group_cross_book(rows: list[dict]) -> list[dict]:
    """Group rows by pitcher+prop for side-by-side book comparison."""
    groups: dict[tuple, dict] = {}
    for row in rows:
        key = (
            str(row.get("pitcher") or "").lower(),
            str(row.get("prop") or "").upper(),
        )
        grp = groups.setdefault(
            key,
            {
                "pitcher": row.get("pitcher"),
                "prop": row.get("prop"),
                "team": row.get("team"),
                "opponent": row.get("opponent"),
                "game_pk": row.get("game_pk"),
                "projection": row.get("projection"),
                "books": {},
            },
        )
        book = str(row.get("book") or "unknown").lower()
        grp["books"][book] = {
            "line": row.get("line"),
            "p_over": row.get("p_over"),
            "lean": row.get("lean"),
        }
        if row.get("projection") is not None:
            grp["projection"] = row.get("projection")
    return list(groups.values())
