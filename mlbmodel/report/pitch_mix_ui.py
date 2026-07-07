"""Pitch-mix vs lineup — clear K/run drivers with signed delta color coding."""
from __future__ import annotations

import html

from mlbmodel.report.html_fmt import val_chip_html

e = html.escape


def _fmt_signed(value: float, digits: int, suffix: str) -> str:
    text = f"{value:+.{digits}f}{suffix}"
    return text


def _k_delta_class(delta: float) -> str:
    if delta >= 1.0:
        return "c-elite"
    if delta >= 0.45:
        return "c-good"
    if delta >= 0.12:
        return "c-mid"
    if delta > -0.12:
        return "c-mid"
    if delta > -0.45:
        return "c-weak"
    return "c-poor"


def _run_pct_class(run_pct: float) -> str:
    """run_pct = change in run scoring; negative suppresses runs (pitcher-favorable)."""
    if run_pct <= -1.8:
        return "c-elite"
    if run_pct <= -0.8:
        return "c-good"
    if run_pct <= -0.2:
        return "c-mid"
    if run_pct < 0.2:
        return "c-mid"
    if run_pct < 0.8:
        return "c-weak"
    return "c-poor"


def pitch_k_delta_html(value, *, digits: int = 2) -> str:
    if value is None:
        return '<span class="c-na">—</span>'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return '<span class="c-na">—</span>'
    cls = _k_delta_class(number)
    return f'<b class="{cls}">{e(_fmt_signed(number, digits, " K%"))}</b>'


def pitch_run_pct_html(value, *, digits: int = 1, suffix: str = "% runs") -> str:
    if value is None:
        return '<span class="c-na">—</span>'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return '<span class="c-na">—</span>'
    cls = _run_pct_class(number)
    return f'<b class="{cls}">{e(_fmt_signed(number, digits, f" {suffix}"))}</b>'


def pitch_mix_verdict_html(label: str | None) -> str:
    key = str(label or "").strip().lower()
    if "pitcher" in key:
        return '<span class="pill pos">Pitcher</span>'
    if "lineup" in key:
        return '<span class="pill neg">Lineup</span>'
    return '<span class="pill mut">Neutral</span>'


def pitch_mix_net_html(pitch_matchup: dict) -> str:
    """One-line net K + run impact vs the opposing lineup."""
    if not pitch_matchup:
        return ""
    k = pitch_matchup.get("k_rate_delta")
    er = pitch_matchup.get("er_factor")
    runs = (float(er) - 1.0) * 100 if isinstance(er, (int, float)) else None
    coverage = pitch_matchup.get("coverage_pct")
    matched = pitch_matchup.get("lineup_batters_matched")
    parts = ['<div class="pitch-mix-net">']
    parts.append('<span class="pitch-mix-net__label">Net vs lineup</span>')
    parts.append(pitch_k_delta_html(k) if k is not None else '<span class="c-na">— K%</span>')
    parts.append('<span class="pitch-mix-net__sep">·</span>')
    parts.append(
        pitch_run_pct_html(runs) if runs is not None else '<span class="c-na">— runs</span>'
    )
    parts.append(pitch_mix_verdict_html(pitch_matchup.get("verdict")))
    meta = []
    if coverage is not None:
        meta.append(f"{float(coverage):.0f}% pitch coverage")
    if matched is not None:
        meta.append(f"{matched} batters")
    if meta:
        parts.append(f'<span class="mut pitch-mix-net__meta">{e(" · ".join(meta))}</span>')
    parts.append("</div>")
    return "".join(parts)


def _pitch_row(pitch: dict, *, compact: bool) -> str:
    run_pct = float(pitch.get("er_factor_delta") or 0) * 100
    whiff_cell = (
        val_chip_html(pitch.get("lineup_whiff_pct"), "rate", digits=1, suffix="%")
        if not compact
        else ""
    )
    whiff_col = f"<td>{whiff_cell}</td>" if not compact else ""
    ba_ops_cols = ""
    if not compact:
        ba_ops_cols = (
            f'<td>{val_chip_html(pitch.get("lineup_ba"), "rate", digits=3)}</td>'
            f'<td>{val_chip_html(pitch.get("lineup_ops"), "woba", digits=3)}</td>'
        )
    return (
        f'<tr><td><b>{e(str(pitch.get("pitch") or ""))}</b>'
        f'<span class="mut pitch-name-meta">{float(pitch.get("usage_pct") or 0):.0f}% usage</span></td>'
        f"{ba_ops_cols}"
        f'<td>{val_chip_html(pitch.get("lineup_xwoba"), "woba", digits=3)}</td>'
        f"{whiff_col}"
        f'<td class=num>{pitch_k_delta_html(pitch.get("k_delta"))}</td>'
        f'<td class=num>{pitch_run_pct_html(run_pct)}</td>'
        f'<td>{pitch_mix_verdict_html(pitch.get("edge"))}</td></tr>'
    )


def pitch_mix_board_html(
    pitch_matchup: dict,
    *,
    compact: bool = False,
    show_title: bool = True,
    show_legend: bool = True,
) -> str:
    """Summary strip + table explaining how each pitch type moves K% and runs."""
    pm = pitch_matchup or {}
    pitches = pm.get("pitches") or []
    if not pitches:
        cols = 7 if compact else 9
        body = f'<tr><td class=mut colspan={cols}>No reliable pitch-type overlap with this lineup.</td></tr>'
    else:
        body = "".join(_pitch_row(pitch, compact=compact) for pitch in pitches[:5])
    source = e(str(pm.get("response_source") or "No lineup match"))
    legend = (
        '<p class="pitch-mix-legend">'
        "<b>Δ K%</b> = whiff/chase edge · "
        "<b>Δ runs</b> = contact shift (green = fewer runs allowed) · "
        "Opp BA/OPS = how the lineup hits this pitch type.</p>"
        if show_legend else ""
    )
    board_cls = "pitch-mix-board pitch-mix-board--compact" if compact else "pitch-mix-board"
    xwoba_head = "xwOBA" if compact else "Opp xwOBA"
    whiff_head = "" if compact else "<th>Whiff</th>"
    ba_ops_head = "" if compact else "<th>BA</th><th>OPS</th>"
    title_block = (
        '<div class="ca-subhead">Pitch mix vs opposing lineup</div>'
        if show_title else ""
    )
    return (
        f"{pitch_mix_net_html(pm)}"
        f"{title_block}"
        f'<p class="pitch-mix-source">{source}</p>'
        f'<div class="{board_cls}"><table class="pitch-mix-table">'
        f"<tr><th>Pitch</th>{ba_ops_head}<th>{xwoba_head}</th>{whiff_head}"
        f"<th>Δ K%</th><th>Δ runs</th><th>Lean</th></tr>{body}</table></div>"
        f"{legend}"
    )


def pitch_mix_runs_chip(er_factor) -> str:
    """Compact graded chip for team-level pitch-mix run impact."""
    if not isinstance(er_factor, (int, float)):
        return '<span class="c-na">—</span>'
    return pitch_run_pct_html((float(er_factor) - 1.0) * 100, suffix="%")
