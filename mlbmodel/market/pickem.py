"""Pick'em board rows from cached DFS lines + model projections."""
from __future__ import annotations

import json
from pathlib import Path

from mlbmodel.market import prizepicks
from mlbmodel.market.probability import p_over_line_erf, p_over_line_normal
from mlbmodel import settings

PICKEM_BOOKS = ("prizepicks", "underdog", "sleeper")
_PICKEM_ORDER = ["PP_Fantasy", "K", "Outs", "ER", "H", "BB"]


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
