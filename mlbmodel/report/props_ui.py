"""Pitcher prop accordion cards — one collapsible section per starter."""
from __future__ import annotations

import html

from mlbmodel.market import prizepicks
from mlbmodel.market.probability import p_over_line_erf
from mlbmodel.report.html_fmt import (
    display as _display,
    edge_grade as _edge_grade,
    lean_dir_html,
    prob_chip_html,
    val_chip_html,
    val_grade_html,
)
from mlbmodel.report.matchup import _headshot, _logo

e = html.escape

_PICKEM_ORDER = ["PP_Fantasy", "K", "Outs", "ER", "H", "BB"]


def _p_over(line, mean, sd):
    return p_over_line_erf(line, mean, sd or 0)


def _market_report_row(report: dict) -> str:
    prop_label = prizepicks.STAT_LABEL.get(report["prop"], report["prop"])
    side_key = str(report.get("side") or "").upper()
    bet_cell = (
        f'{lean_dir_html(side_key)} {report["line"]:g}'
        if side_key in {"OVER", "UNDER"}
        else f'{e(str(report.get("side") or "").title())} {report["line"]:g}'
    )
    if report.get("best_odds") is not None:
        price_cell = f'{report["best_odds"]:+d}'
    else:
        book_label = str(report.get("best_book") or "pick'em")
        price_cell = f'<span class="pill mut">{e(book_label)}</span>'
    return (
        f'<tr><td>{e(prop_label)}</td>'
        f'<td>{bet_cell}</td>'
        f'<td>{price_cell}</td>'
        f'<td>{prob_chip_html(report["model_probability"])}</td>'
        f'<td><b class={_edge_grade(report.get("edge"))}>'
        f'{(report.get("edge") or 0) * 100:+.1f}pt</b></td></tr>'
    )


def _market_state_badge(state: str, tone: str) -> str:
    key = str(state or "").strip().upper()
    if key in {"OVER", "UNDER"}:
        return lean_dir_html(key)
    return f'<span class="pill {tone}">{e(str(state))}</span>'


def _projection_chip(prop: str, value: dict) -> str:
    if not value:
        return f'<span class="prop-chip prop-chip--sm mut"><b>—</b><i>{e(prop)}</i></span>'
    return (
        f'<span class="prop-chip prop-chip--sm"><b>{value["mean"]:.1f}</b>'
        f'<i>{e(prop)}</i></span>'
    )


def _pickem_rows_for_pitcher(row: dict, sources: list[tuple[str, dict]]) -> str:
    name_key = prizepicks.normalize_name(row.get("pitcher"))
    projections = row.get("projections") or {}
    rows = ""
    for label, board in sources:
        lines = board.get(name_key, {})
        if not lines:
            continue
        for key in _PICKEM_ORDER:
            line, proj = lines.get(key), projections.get(key)
            if not line or not proj:
                continue
            mean, sd = proj.get("mean"), proj.get("sd")
            p_over = _p_over(line["line"], mean, sd or 0)
            lean = "OVER" if p_over >= 0.5 else "UNDER"
            variant = (
                "" if line.get("odds_type") == "standard"
                else f' <span class="mut odds-variant">{e(str(line.get("odds_type")))}</span>'
            )
            rows += (
                f'<tr><td><span class="pill mut">{e(label)}</span></td>'
                f'<td>{prizepicks.STAT_LABEL.get(key, key)}{variant}</td>'
                f'<td><b>{line["line"]:g}</b></td>'
                f'<td>{mean:.1f}</td>'
                f'<td>{prob_chip_html(p_over)}</td>'
                f'<td>{lean_dir_html(lean)}</td></tr>'
            )
    return rows or '<tr><td class=mut colspan=6>No pick&apos;em lines for this pitcher.</td></tr>'


def pitcher_prop_card(
    index: int,
    row: dict,
    *,
    pickem_sources: list[tuple[str, dict]],
    expanded: bool = False,
) -> str:
    reports = row.get("market_report") or []
    trusted = row.get("projection_trust") == "trusted"
    projections = row.get("projections") or {}
    best = reports[0] if reports else None
    market_state = best.get("state") if best else row.get("market_state", "NO MARKET")
    market_tone = (
        "pos"
        if market_state in {"BET", "MONITOR", "OVER", "UNDER"}
        else "warnc" if market_state == "WATCH" else "mut"
    )
    if not trusted:
        market_state = "THIN DATA"
        market_tone = "warnc"

    chips = "".join(
        _projection_chip(prop, projections.get(prop) or {})
        for prop in ("K", "BB", "ER", "Outs", "H", "Fantasy")
    )
    best_edge = ""
    if best and trusted and best.get("edge") is not None:
        side_label = str(best.get("side") or "").upper()
        if side_label in {"OVER", "UNDER"}:
            side_html = lean_dir_html(side_label, as_pill=False)
        else:
            side_html = e(side_label[:1] or "?")
        best_edge = (
            f'<span class="pill side">'
            f'{side_html} {e(str(best["prop"]))} {best["line"]:g} '
            f'<b class={_edge_grade(best.get("edge"))}>'
            f'{(best.get("edge") or 0) * 100:+.1f}pt</b></span>'
        )

    pickem_rows = _pickem_rows_for_pitcher(row, pickem_sources)
    pitch_matchup = row.get("pitch_matchup") or {}
    pitch_rows = "".join(
        f'<tr><td><b>{e(str(pitch.get("pitch") or ""))}</b>'
        f'<span class="mut pitch-name-meta">{_display(pitch.get("usage_pct"), "%")}</span></td>'
        f'<td>{val_chip_html(pitch.get("lineup_xwoba"), "woba", digits=3)}</td>'
        f'<td>{val_grade_html(pitch.get("k_delta"), "margin", digits=2, suffix=" K%")}</td></tr>'
        for pitch in pitch_matchup.get("pitches", [])[:5]
    ) or '<tr><td class=mut colspan=3>No pitch overlap.</td></tr>'

    market_rows = "".join(
        _market_report_row(report) for report in reports
    ) or '<tr><td class=mut colspan=5>No priced line for this pitcher.</td></tr>'

    has_markets = bool(reports)
    has_pickem = "No pick" not in pickem_rows
    has_arsenal = bool(pitch_matchup.get("pitches"))
    market_open = " open" if has_markets else ""
    pickem_open = " open" if has_pickem else ""
    arsenal_open = " open" if has_arsenal else ""
    on_cls = " on" if expanded else ""
    k_mean = projections.get("K", {}).get("mean", 0)
    er_mean = projections.get("ER", {}).get("mean", 0)
    bb_mean = projections.get("BB", {}).get("mean", 0)
    outs_mean = projections.get("Outs", {}).get("mean", 0)

    return f"""<div class="pitcher-prop-card{on_cls}" id="prop-card-{index}">
  <button type=button class=pitcher-prop-head onclick="togglePitcherCard({index})" aria-expanded="{'true' if expanded else 'false'}">
    <div class=pitcher-prop-id>{_headshot(row.get("pitcher_id"))}
      <div><b>{e(str(row.get("pitcher") or "TBD"))}</b>
        <span class=pitcher-prop-meta>{_logo(row.get("team"), "tlogo sm")}{e(str(row.get("team") or ""))}
        <span class=mut>@</span> {_logo(row.get("opponent"), "tlogo sm")}{e(str(row.get("opponent") or ""))}</span>
      </div>
    </div>
    <div class=pitcher-prop-summary>
      <span><b>{k_mean:.1f}</b>K · <b>{bb_mean:.1f}</b>BB · <b>{outs_mean:.1f}</b>Out · <b>{er_mean:.1f}</b>ER</span>
      {best_edge}
      {_market_state_badge(market_state, market_tone)}
    </div>
    <span class=pitcher-prop-chevron aria-hidden=true>▸</span>
  </button>
  <div class=pitcher-prop-body>
    <div class=prop-proj-strip>{chips}</div>
    <details class="prop-panel"{market_open}>
      <summary>Lines</summary>
      <div class=table-scroll><table><tr><th>Prop</th><th>Bet</th><th>Price</th><th>Model</th><th>Edge</th></tr>{market_rows}</table></div>
    </details>
    <details class="prop-panel"{pickem_open}>
      <summary>Pick&apos;em</summary>
      <div class=table-scroll><table><tr><th>Book</th><th>Stat</th><th>Line</th><th>Model</th><th>P(over)</th><th>Lean</th></tr>{pickem_rows}</table></div>
    </details>
    <details class="prop-panel"{arsenal_open}>
      <summary>Pitch mix</summary>
      <div class=table-scroll><table><tr><th>Pitch</th><th>Opp contact</th><th>K effect</th></tr>{pitch_rows}</table></div>
    </details>
  </div>
</div>"""


def pitcher_prop_deck(
    pitchers: list[dict],
    pickem_sources: list[tuple[str, dict]],
) -> str:
    if not pitchers:
        return '<div class=empty>No pitcher inputs loaded.</div>'
    cards = []
    expanded_count = 0
    for index, row in enumerate(pitchers):
        has_lines = bool(row.get("market_report"))
        expanded = has_lines and expanded_count < 4
        if expanded:
            expanded_count += 1
        cards.append(
            pitcher_prop_card(
                index, row, pickem_sources=pickem_sources, expanded=expanded
            )
        )
    return f'<div class=pitcher-prop-deck>{"".join(cards)}</div>'
