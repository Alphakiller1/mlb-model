"""Situational trends UI — one matchup at a time via page select; Game / Props / Fantasy / Markets lanes."""
from __future__ import annotations

import html
import re

from mlbmodel.report.html_fmt import lean_dir_html, val_chip_html
from mlbmodel.report.game_keys import game_option_label
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
    ("game", "Game"),
    ("props", "Props"),
    ("fantasy", "Fantasy"),
    ("markets", "Markets"),
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


def _sample_chip(sample) -> str:
    if sample is None:
        return '<span class="c-na">—</span>'
    try:
        value = float(sample)
    except (TypeError, ValueError):
        return '<span class="c-na">—</span>'
    return val_chip_html(value, "sample_n", digits=0)


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
        f'<tr class=trend-row>'
        f'{game_cell}'
        f'<td><span class=gcell>{_logo(team, "tlogo sm")}{e(team)}</span></td>'
        f'<td><span class="pill {_CAT_TONE.get(category, "mut")}">'
        f'{e(_CAT_LABEL.get(category, category.replace("_", " ").title()))}</span></td>'
        f'<td class=trend-headline>{e(trend_headline(trend))}</td>'
        f'<td class=num>{mag_chip_html(effect)}</td>'
        f'<td class=num>{_sample_chip(sample)}</td>'
        f'<td>{trend_bet_html(implication)}</td>'
        f'<td class=trend-pills>{pills}</td></tr>{detail_row}'
    )


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


def _matchup_lanes_html(report) -> str:
    game = str(_get(report, "game") or "")
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
        return '<div class=mut>No ranked trends for this matchup.</div>'
    return lanes


def trend_matchup_panel(report, *, active: bool = False) -> str:
    game = str(_get(report, "game") or "")
    if not game:
        away = str(_get(report, "away") or "")
        home = str(_get(report, "home") or "")
        game = f"{away}@{home}" if away and home else ""
    hidden = "" if active else " hidden"
    return (
        f'<div class="trend-matchup-panel" data-game="{e(game)}"{hidden}>'
        f'{_matchup_lanes_html(report)}</div>'
    )


def trends_section_html(reports, *, slate: list[dict] | None = None) -> str:
    if not reports:
        return (
            '<div class=pagehead><div><h2>Trends</h2></div></div>'
            '<div class=empty>No slate loaded.</div>'
        )

    options = []
    panels = []
    for index, report in enumerate(reports):
        game = str(_get(report, "game") or "")
        away = str(_get(report, "away") or "")
        home = str(_get(report, "home") or "")
        if not game and away and home:
            game = f"{away}@{home}"
        label = game
        if slate:
            match = next(
                (g for g in slate if g.get("key") == game),
                None,
            )
            if match:
                label = game_option_label(match, slate)
            elif away and home:
                label = f"{away} @ {home}"
        selected = " selected" if index == 0 else ""
        options.append(
            f'<option value="{e(game)}"{selected}>{e(label)}</option>'
        )
        panels.append(trend_matchup_panel(report, active=(index == 0)))

    return (
        f'<div class=pagehead>'
        f'<div><h2>Trends</h2><p class=pagehead-sub>Signals by matchup</p></div>'
        f'<select id=trendGameSelect aria-label="Matchup" onchange="switchTrendGame(this.value)">'
        f'{"".join(options)}</select></div>'
        f'<div class=trend-matchup-deck id=trend-matchup-deck>{"".join(panels)}</div>'
    )
