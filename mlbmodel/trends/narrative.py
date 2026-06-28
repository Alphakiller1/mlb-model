"""Human-readable narrative generation from scored trends.

Template-driven (deterministic, no model call) so the same trend always reads the same way.
Each bullet leads with the dominant fact, states magnitude/sample honestly, appends the
mechanistic "why", and ends with the bettable implication — and flags small samples.
"""

from __future__ import annotations

from mlbmodel.trends.types import SituationalEdge, Trend

_CAVEAT = {
    "strong": "",
    "moderate": "",
    "weak": " (modest signal)",
    "small-sample": " ⚠ small sample — treat as a lean, not a conclusion",
}


def trend_bullet(trend: Trend) -> str:
    rec = f" [{trend.historical_record}]" if trend.historical_record else ""
    bet = trend.betting_implications[0] if trend.betting_implications else ""
    caveat = _CAVEAT.get(trend.significance, "")
    return (
        f"{trend.trend_description}{rec} — {trend.mechanistic_explanation} "
        f"→ {bet}.{caveat}"
    )


def build_narrative(edge: SituationalEdge, top_n: int = 6) -> list[str]:
    lines: list[str] = []
    lean_txt = (
        f"Situational edge: {edge.edge_lean} "
        f"({edge.away}={edge.away_edge_score:.0f} / {edge.home}={edge.home_edge_score:.0f} on a 0–100 scale)."
        if edge.edge_lean != "even"
        else f"Situational edge: even ({edge.away}={edge.away_edge_score:.0f} / {edge.home}={edge.home_edge_score:.0f})."
    )
    lines.append(lean_txt)
    for t in edge.trends[:top_n]:
        lines.append(trend_bullet(t))
    if not edge.trends:
        lines.append("No dominant situational trends cleared the magnitude/sample threshold for this game.")
    for note in edge.notes:
        lines.append(f"Note: {note}")
    return lines
