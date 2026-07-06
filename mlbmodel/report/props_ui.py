"""Pitcher prop accordion cards — one collapsible section per starter."""
from __future__ import annotations

import html

from mlbmodel.market import prizepicks
from mlbmodel.market.probability import p_over_line_erf
from mlbmodel.report.html_fmt import display as _display, edge_grade as _edge_grade
from mlbmodel.report.matchup import _headshot, _logo

e = html.escape

_PICKEM_ORDER = ["PP_Fantasy", "K", "Outs", "ER", "H", "BB"]


def _p_over(line, mean, sd):
    return p_over_line_erf(line, mean, sd or 0)


def _projection_chip(prop: str, value: dict, report: dict | None, trusted: bool) -> str:
    if not value:
        return f'<span class="prop-chip mut"><b>—</b><i>{e(prop)}</i></span>'
    edge_cls = _edge_grade(report.get("edge")) if (trusted and report) else "mut"
    market = (
        f'{report["side"][0].upper()} {report["line"]:g} {report["best_odds"]:+d} · '
        f'<b class="{edge_cls}">{(report.get("edge") or 0) * 100:+.1f}pt</b>'
        if report
        else '<span class=mut>no line</span>'
    )
    return (
        f'<span class=prop-chip><b>{value["mean"]:.1f}</b>'
        f'<i>{e(prop)}</i>'
        f'<span class=prop-range>{value["p10"]:.0f}–{value["p90"]:.0f}</span>'
        f'<span class=prop-mkt>{market}</span></span>'
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
            tone = "pos" if abs(p_over - 0.5) >= 0.08 else "mut"
            variant = (
                "" if line.get("odds_type") == "standard"
                else f' <span class="mut" style="font-size:9px">{e(str(line.get("odds_type")))}</span>'
            )
            rows += (
                f'<tr><td><span class="pill mut">{e(label)}</span></td>'
                f'<td>{prizepicks.STAT_LABEL.get(key, key)}{variant}</td>'
                f'<td><b>{line["line"]:g}</b></td>'
                f'<td>{mean:.1f}</td>'
                f'<td>{p_over * 100:.0f}%</td>'
                f'<td><span class="pill {tone}">{lean}</span></td></tr>'
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
    state = row.get("state", "DATA GAP")
    state_tone = "neg" if state == "REGRESSION" else (
        "pos" if state == "PROGRESSION" else "side" if state == "STABLE" else "warnc"
    )
    best = reports[0] if reports else None
    market_state = best.get("state") if best else row.get("market_state", "NO MARKET")
    market_tone = "pos" if market_state in {"BET", "MONITOR"} else "mut"
    if not trusted:
        market_state = "THIN DATA"
        market_tone = "warnc"

    def report_for(prop: str):
        return next((item for item in reports if item["prop"] == prop), None)

    chips = "".join(
        _projection_chip(prop, projections.get(prop) or {}, report_for(prop), trusted)
        for prop in ("K", "BB", "ER", "Outs", "H", "Fantasy")
    )

    pitch_rows = "".join(
        f'<tr><td><b>{e(str(pitch.get("pitch") or ""))}</b>'
        f'<span class="mut pitch-name-meta">{_display(pitch.get("usage_pct"), "%")} usage</span></td>'
        f'<td>{_display(pitch.get("pitcher_whiff_pct"), "%")}</td>'
        f'<td>{_display(pitch.get("lineup_whiff_pct"), "%")}</td>'
        f'<td>{_display(pitch.get("pitcher_xwoba"), digits=3)}</td>'
        f'<td>{_display(pitch.get("lineup_xwoba"), digits=3)}</td>'
        f'<td class={"pos" if (pitch.get("k_delta") or 0) > 0 else "neg"}>'
        f'{float(pitch.get("k_delta") or 0):+.2f} K%</td>'
        f'<td class={"pos" if (pitch.get("er_factor_delta") or 0) < 0 else "neg"}>'
        f'{float(pitch.get("er_factor_delta") or 0) * 100:+.1f}% runs</td>'
        f'<td>{e(str(pitch.get("edge") or "neutral"))}</td></tr>'
        for pitch in (row.get("pitch_matchup") or {}).get("pitches", [])[:6]
    ) or '<tr><td class=mut colspan=8>No reliable pitch-overlap sample.</td></tr>'

    market_rows = "".join(
        f'<tr><td>{e(report["prop"])}</td><td>{e(report["side"].title())} {report["line"]:g}</td>'
        f'<td>{report["best_odds"]:+d} · {e(report["best_book"])}</td>'
        f'<td>{report["model_probability"] * 100:.1f}%</td>'
        f'<td>{report["market_probability"] * 100:.1f}%</td>'
        f'<td><b class={_edge_grade(report.get("edge"))}>'
        f'{(report.get("edge") or 0) * 100:+.1f}pt</b></td>'
        f'<td class={"pos" if (report.get("ev") or 0) > 0 else "neg"}>'
        f'{(report.get("ev") or 0) * 100:+.1f}%</td>'
        f'<td><span class="pill {"pos" if report["state"] == "MONITOR" else "mut"}">{e(report["state"])}</span></td></tr>'
        for report in reports
    ) or '<tr><td class=mut colspan=8>No paired prop price for this pitcher.</td></tr>'

    pickem_rows = _pickem_rows_for_pitcher(row, pickem_sources)
    pitch_matchup = row.get("pitch_matchup") or {}
    lineup = row.get("lineup") or {}
    on_cls = " on" if expanded else ""

    return f"""<div class="pitcher-prop-card{on_cls}" id="prop-card-{index}">
  <button type=button class=pitcher-prop-head onclick="togglePitcherCard({index})" aria-expanded="{'true' if expanded else 'false'}">
    <div class=pitcher-prop-id>{_headshot(row.get("pitcher_id"))}
      <div><b>{e(str(row.get("pitcher") or "TBD"))}</b>
        <span class=pitcher-prop-meta>{_logo(row.get("team"), "tlogo sm")}{e(str(row.get("team") or ""))}
        <span class=mut>vs</span> {_logo(row.get("opponent"), "tlogo sm")}{e(str(row.get("opponent") or ""))}</span>
      </div>
    </div>
    <div class=pitcher-prop-summary>
      <span class="pill {state_tone}">{e(state)}</span>
      <span><b>{_display(row.get("expected_ip"), digits=1)}</b> IP · {_display(row.get("skill_era"), digits=2)} r9</span>
      <span><b>{projections.get("K", {}).get("mean", 0):.1f}</b> K · <b>{projections.get("ER", {}).get("mean", 0):.1f}</b> ER</span>
      <span class="pill {market_tone}">{e(str(market_state))}</span>
    </div>
    <span class=pitcher-prop-chevron aria-hidden=true>▸</span>
  </button>
  <div class=pitcher-prop-body>
    <div class=prop-proj-strip>{chips}</div>
    <div class=detail-strip>
      <span>Lineup <b>{e(str(row.get("lineup_status") or "unavailable"))}</b></span>
      <span>Luck <b>{float(row.get("luck_runs") or 0):+.2f}</b> runs</span>
      <span>Confidence <b>{e(str(row.get("confidence") or "low"))}</b></span>
      <span>Coverage <b>{row.get("data_coverage_pct", 0)}%</b></span>
    </div>
    <div class=ca-board><h2>Market lines</h2><div class=body>
      <div class=table-scroll><table><tr><th>Prop</th><th>Bet</th><th>Best price</th>
        <th>Model</th><th>Market</th><th>Edge</th><th>EV</th><th>State</th></tr>{market_rows}</table></div>
    </div></div>
    <div class=ca-board><h2>Pick&apos;em lines</h2><div class=body>
      <div class=table-scroll><table><tr><th>Book</th><th>Market</th><th>Line</th><th>Model</th><th>P(over)</th><th>Lean</th></tr>{pickem_rows}</table></div>
    </div></div>
    <div class=ca-board><h2>Arsenal vs opponent</h2><div class=body>
      <div class=detail-strip>
        <span>{e(str(pitch_matchup.get("response_source") or "no response source"))}</span>
        <span>{pitch_matchup.get("coverage_pct", 0)}% arsenal covered</span>
        <span>{pitch_matchup.get("lineup_batters_matched", 0)}/9 batters matched</span>
        <span>Lineup score <b>{_display(lineup.get("score"), digits=1)}</b></span>
      </div>
      <div class=table-scroll><table><tr><th>Pitch</th><th>Pitcher whiff</th><th>Opponent whiff</th>
        <th>Pitcher contact</th><th>Opponent contact</th><th>K effect</th><th>Run effect</th><th>Edge</th></tr>{pitch_rows}</table></div>
      <div class=note>Opponent values switch from team results to batting-order-weighted player results when at least six posted hitters match.</div>
    </div></div>
  </div>
</div>"""


def pitcher_prop_deck(
    pitchers: list[dict],
    pickem_sources: list[tuple[str, dict]],
) -> str:
    if not pitchers:
        return '<div class=empty>No pitcher inputs loaded.</div>'
    cards = "".join(
        pitcher_prop_card(index, row, pickem_sources=pickem_sources, expanded=(index == 0))
        for index, row in enumerate(pitchers)
    )
    return f'<div class=pitcher-prop-deck>{cards}</div>'
