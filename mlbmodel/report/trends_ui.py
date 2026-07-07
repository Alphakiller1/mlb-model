"""Situational trends UI — matchup-first cards grouped by game, props, fantasy, and markets."""
from __future__ import annotations

import html
import re

from mlbmodel.report.html_fmt import lean_dir_html, section_head, val_chip_html
from mlbmodel.report.matchup import _logo
from mlbmodel.trends.types import RUN_BOOST, RUN_SUPPRESSION

e = html.escape

_CAT_LABEL = {
    "bullpen_fatigue": "Bullpen",
    "form_vs_hand": "Form",
    "starter_quality": "SP",
    "park": "Park",
    "prop_strikeouts": "K prop",
    "prop_walks": "BB prop",
    "prop_earned_runs": "ER prop",
    "prop_outs": "Outs prop",
    "prop_hits": "Hits prop",
    "prop_f5_er": "F5 ER",
    "fantasy_dk": "DK fantasy",
    "fantasy_pp": "PP fantasy",
    "market_total": "Total",
    "market_ml": "ML",
    "market_runline": "Run line",
}
_CAT_FILTER = {
    "bullpen_fatigue": "bullpen",
    "form_vs_hand": "form",
    "starter_quality": "sp",
    "platoon": "form",
    "park": "park",
    "prop_strikeouts": "props",
    "prop_walks": "props",
    "prop_earned_runs": "props",
    "prop_outs": "props",
    "prop_hits": "props",
    "prop_f5_er": "props",
    "fantasy_dk": "fantasy",
    "fantasy_pp": "fantasy",
    "market_total": "markets",
    "market_ml": "markets",
    "market_runline": "markets",
}
_CAT_TONE = {
    "bullpen_fatigue": "warnc",
    "form_vs_hand": "side",
    "starter_quality": "pos",
    "park": "mut",
    "prop_strikeouts": "side",
    "prop_earned_runs": "warnc",
    "fantasy_dk": "pos",
    "fantasy_pp": "pos",
    "market_total": "side",
    "market_ml": "pos",
}
_LANES = (
    ("game", "Game & situational"),
    ("props", "Prop trends"),
    ("fantasy", "Fantasy score"),
    ("markets", "Market edges"),
)


def _trend_lane(category: str) -> str:
    cat = str(category or "")
    if cat.startswith("prop_"):
        return "props"
    if cat.startswith("fantasy_"):
        return "fantasy"
    if cat.startswith("market_"):
        return "markets"
    return "game"


def _get(obj, key, default=None):
    return getattr(obj, key, default) if not isinstance(obj, dict) else obj.get(key, default)


def trend_headline(trend) -> str:
    desc = str(_get(trend, "trend_description") or "").strip()
    if not desc:
        return "—"
    first = re.split(r"[.;]\s+", desc, maxsplit=1)[0].strip()
    if len(first) <= 78:
        return first
    return first[:75] + "…"


def mag_chip_html(effect_size) -> str:
    try:
        value = float(effect_size)
    except (TypeError, ValueError):
        return '<span class="c-na">—</span>'
    return val_chip_html(
        min(100.0, value * 40.0),
        "osi",
        display_text=f"{value:.1f}σ",
    )


def trend_bet_html(implication: str | None) -> str:
    text = str(implication or "").strip()
    if not text:
        return '<span class="c-na">—</span>'
    upper = text.upper()
    side = "UNDER" if "UNDER" in upper else ("OVER" if "OVER" in upper else None)
    if side:
        filter_side = "under" if side == "UNDER" else "over"
        rest = re.sub(rf"\b{side}\b", "", text, flags=re.I).strip(" ·-")
        return (
            f'<span class="trend-bet" data-side="{filter_side}">'
            f'{lean_dir_html(side, as_pill=False)} '
            f'<span class=mut>{e(rest or text)}</span></span>'
        )
    tokens = text.split()
    team = tokens[0] if tokens else ""
    if "F5" in upper and "TOTAL" in upper:
        market = "F5 total"
    elif "TEAM TOTAL" in upper or ("TOTAL" in upper and team):
        market = "Team total"
    elif " ML" in upper or upper.endswith(" ML"):
        market = "ML"
    elif "RUN LINE" in upper or "RUNLINE" in upper:
        market = "Run line"
    else:
        market = text
    return f'<span class=mut>{e(team)} {e(market)}</span>' if team else f'<span class=mut>{e(text)}</span>'


def _confidence_pill(confidence: str | None) -> str:
    key = str(confidence or "").strip().lower()
    if not key:
        return ""
    tone = {"high": "pos", "medium": "warnc", "low": "mut"}.get(key, "mut")
    return f'<span class="pill {tone}">{e(key)}</span>'


def _significance_pill(significance: str | None, sample_size) -> str:
    key = str(significance or "").strip().lower()
    if key == "small-sample" or (isinstance(sample_size, int) and sample_size < 6):
        return '<span class="pill warnc">small n</span>'
    if key in {"strong", "moderate", "weak"}:
        tone = {"strong": "pos", "moderate": "side", "weak": "mut"}[key]
        return f'<span class="pill {tone}">{e(key)}</span>'
    return ""


def _direction_pill(direction: str | None) -> str:
    key = str(direction or "").strip().lower()
    if key == RUN_BOOST or key == "run_boost":
        return '<span class="pill pos">run boost</span>'
    if key == RUN_SUPPRESSION or key == "run_suppression":
        return '<span class="pill neg">run suppress</span>'
    return ""


def _trend_filter_attrs(trend) -> str:
    category = str(_get(trend, "category") or "")
    cat_filter = _CAT_FILTER.get(category, category.replace("_", "-"))
    lane = _trend_lane(category)
    implication = (_get(trend, "betting_implications") or [None])[0]
    side_filter = ""
    if implication:
        upper = str(implication).upper()
        if "UNDER" in upper:
            side_filter = "under"
        elif "OVER" in upper:
            side_filter = "over"
    return (
        f'data-cat="{e(cat_filter)}" data-lane="{e(lane)}" data-side="{e(side_filter)}"'
    )


def _trend_table_row(game: str, trend, *, detail: bool = False, show_game: bool = False) -> str:
    implication = (_get(trend, "betting_implications") or [None])[0]
    team = _get(trend, "team") or ""
    category = _get(trend, "category") or ""
    effect = _get(trend, "effect_size")
    sample = _get(trend, "sample_size")
    conf = _confidence_pill(_get(trend, "confidence"))
    sig = _significance_pill(_get(trend, "significance"), sample)
    pills = " ".join(p for p in (_direction_pill(_get(trend, "direction")), sig, conf) if p)
    colspan = 7
    detail_row = ""
    if detail:
        mech = str(_get(trend, "mechanistic_explanation") or "").strip()
        hist = str(_get(trend, "historical_record") or "").strip()
        if mech or hist:
            detail_row = (
                f'<tr class="trend-detail-row"><td colspan={colspan} class=mut>'
                f'{e(mech)}{" · " if mech and hist else ""}{e(hist)}</td></tr>'
            )
    game_cell = (
        f'<td><button type=button class=gamepick onclick="openGame(\'{e(game)}\')">{e(game)}</button></td>'
        if show_game else ""
    )
    return (
        f'<tr class="trend-row" {_trend_filter_attrs(trend)}>'
        f'{game_cell}'
        f'<td><span class=gcell>{_logo(team, "tlogo sm")}{e(team)}</span></td>'
        f'<td><span class="pill {_CAT_TONE.get(category, "mut")}">'
        f'{e(_CAT_LABEL.get(category, category.replace("_", " ").title()))}</span></td>'
        f'<td class=trend-headline>{e(trend_headline(trend))}</td>'
        f'<td class=num>{mag_chip_html(effect)}</td>'
        f'<td class=num>{sample if sample is not None else "—"}</td>'
        f'<td>{trend_bet_html(implication)}</td>'
        f'<td class=trend-pills>{pills}</td></tr>{detail_row}'
    )


def _top_trend_summary(report) -> str:
    trends = [t for t in (_get(report, "trends") or []) if _get(t, "category") != "park"]
    if not trends:
        return "No ranked trends"
    top = max(trends, key=lambda t: float(_get(t, "trend_score") or 0))
    implication = (_get(top, "betting_implications") or [None])[0]
    lean = trend_bet_html(implication)
    lane = _trend_lane(_get(top, "category"))
    lane_label = next((lbl for key, lbl in _LANES if key == lane), "Trend")
    return f'{e(lane_label)} · {e(_CAT_LABEL.get(_get(top, "category"), "Signal"))} · {lean}'


def _lane_block(game: str, lane_key: str, lane_label: str, trends: list) -> str:
    if not trends:
        return ""
    rows = "".join(_trend_table_row(game, t, detail=True) for t in trends)
    return f"""<div class="trend-lane" data-lane="{e(lane_key)}">
  <div class=trend-lane-head>{e(lane_label)} <span class=mut>({len(trends)})</span></div>
  <div class=table-scroll><table class="trend-game-table sortable">
    <tr><th>Team</th><th>Type</th><th>Signal</th><th>Mag</th><th>n</th><th>Lean</th><th>Quality</th></tr>
    {rows}
  </table></div>
</div>"""


def game_trend_card(index: int, report, *, expanded: bool = False) -> str:
    game = str(_get(report, "game") or "")
    away = str(_get(report, "away") or "")
    home = str(_get(report, "home") or "")
    away_edge = float(_get(report, "away_edge_score") or 50)
    home_edge = float(_get(report, "home_edge_score") or 50)
    lean = str(_get(report, "edge_lean") or "even")
    trends = [t for t in (_get(report, "trends") or []) if _get(t, "category") != "park"]
    by_lane: dict[str, list] = {key: [] for key, _ in _LANES}
    for trend in trends:
        by_lane[_trend_lane(_get(trend, "category"))].append(trend)
    for lane_trends in by_lane.values():
        lane_trends.sort(key=lambda t: float(_get(t, "trend_score") or 0), reverse=True)
    lanes = "".join(
        _lane_block(game, key, label, by_lane[key]) for key, label in _LANES
    )
    if not lanes:
        lanes = '<div class=mut>No ranked trends for this matchup.</div>'
    lean_cls = "pos" if lean not in ("", "even", "—") else "mut"
    on_cls = " on" if expanded else ""
    counts = " · ".join(
        f'{label.split()[0]} {len(by_lane[key])}'
        for key, label in _LANES
        if by_lane[key]
    )
    return f"""<div class="trend-game-card{on_cls}" id="trend-card-{index}">
  <button type=button class=trend-game-head onclick="toggleTrendCard({index})" aria-expanded="{'true' if expanded else 'false'}">
    <div class=trend-game-id>
      <span class=gcell>{_logo(away, "tlogo sm")}<b>{e(away)}</b><span class=mut>@</span>{_logo(home, "tlogo sm")}<b>{e(home)}</b></span>
      <span class=trend-game-edge>{val_chip_html(away_edge, "osi", digits=0, suffix=f" {away}")} · {val_chip_html(home_edge, "osi", digits=0, suffix=f" {home}")}</span>
    </div>
    <div class=trend-game-summary>
      <span class="pill {lean_cls}">Lean {e(lean)}</span>
      <span class=mut>{e(counts)}</span>
      <span class=trend-game-top>{_top_trend_summary(report)}</span>
    </div>
    <span class=trend-game-chevron aria-hidden=true>▸</span>
  </button>
  <div class=trend-game-body>
    {lanes}
  </div>
</div>"""


def trends_filter_bar() -> str:
    pills = [
        ("all", "All", True),
        ("game", "Game", False),
        ("props", "Props", False),
        ("fantasy", "Fantasy", False),
        ("markets", "Markets", False),
        ("sp", "SP", False),
        ("bullpen", "Bullpen", False),
        ("over", "Overs", False),
        ("under", "Unders", False),
    ]
    body = "".join(
        f'<button type=button class="hub-pill{" active" if active else ""}" '
        f'data-trend-filter="{key}" onclick="filterTrends(\'{key}\')">{label}</button>'
        for key, label, active in pills
    )
    return f'<div class="hub-control-bar trend-filter-bar">{body}</div>'


def trends_section_html(reports) -> str:
    if not reports:
        return "<h2>Situational Trends</h2><div class=empty>No slate loaded.</div>"

    flat = []
    for report in reports:
        game = str(_get(report, "game") or "")
        for trend in _get(report, "trends") or []:
            if _get(trend, "category") == "park":
                continue
            flat.append((game, trend))
    flat.sort(key=lambda item: float(_get(item[1], "trend_score") or 0), reverse=True)

    deck = "".join(
        game_trend_card(index, report, expanded=(index == 0))
        for index, report in enumerate(reports)
    )

    total = len(flat)
    strongest = float(_get(flat[0][1], "effect_size") or 0) if flat else 0.0
    prop_count = sum(1 for _, t in flat if _trend_lane(_get(t, "category")) == "props")
    fantasy_count = sum(1 for _, t in flat if _trend_lane(_get(t, "category")) == "fantasy")
    market_count = sum(1 for _, t in flat if _trend_lane(_get(t, "category")) == "markets")
    top_lean_report = max(
        reports,
        key=lambda r: max(
            float(_get(r, "away_edge_score") or 50),
            float(_get(r, "home_edge_score") or 50),
        ),
    )
    top_lean = str(_get(top_lean_report, "edge_lean") or "—")
    top_game = str(_get(top_lean_report, "game") or "—")

    return f"""<h2>Situational Trends</h2>
 <div class=cards>
   <div class=card><div class=k>Matchups</div><div class=v>{len(reports)}</div></div>
   <div class=card><div class=k>Signals</div><div class=v>{total}</div></div>
   <div class=card><div class=k>Props · Fantasy · Markets</div><div class="v v-sm">{prop_count} · {fantasy_count} · {market_count}</div></div>
   <div class=card><div class=k>Strongest σ</div><div class=v>{mag_chip_html(strongest)}</div></div>
   <div class=card><div class=k>Top lean</div><div class="v v-sm">{e(top_lean)}<span class=mut> · {e(top_game)}</span></div></div>
 </div>
 {trends_filter_bar()}
 <div class=ca-board>{section_head("Trends by matchup", icon="matchups")}<div class=body>
   <div class=trend-game-deck id=trend-game-deck>{deck}</div>
 </div></div>"""
