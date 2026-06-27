"""Structured, user-facing risk signals for a matchup."""
from __future__ import annotations

from dataclasses import dataclass

from mlbmodel.baseball.model import GameData


@dataclass(frozen=True)
class RiskSignal:
    label: str
    category: str
    severity: str
    implication: str


def risk_signals(gd: GameData) -> list[RiskSignal]:
    risks: list[RiskSignal] = []
    for team, hr9 in ((gd.away, gd.away_hr9), (gd.home, gd.home_hr9)):
        if hr9 is not None and hr9 >= 1.5:
            risks.append(
                RiskSignal(
                    f"{team} starter allows {hr9:.2f} HR/9",
                    "Home-run volatility",
                    "high",
                    "Raises total and moneyline tail risk",
                )
            )
    for team, context in ((gd.away, gd.away_context), (gd.home, gd.home_context)):
        if context.bullpen_high_lev_era is not None and context.bullpen_high_lev_era >= 5:
            risks.append(
                RiskSignal(
                    f"{team} high-leverage bullpen ERA {context.bullpen_high_lev_era:.2f}",
                    "Late innings",
                    "high",
                    "Weakens full-game positions; F5 may isolate the starter edge",
                )
            )
        if context.window_direction in {"rising", "falling"}:
            direction = "improving" if context.window_direction == "rising" else "declining"
            risks.append(
                RiskSignal(
                    f"{team} recent MLBMA window is {direction}",
                    "Recent form",
                    "medium",
                    "Context only until its incremental value passes validation",
                )
            )
    if not gd.weather:
        risks.append(
            RiskSignal(
                "Weather unavailable",
                "Data quality",
                "medium",
                "Totals remain provisional until weather is loaded",
            )
        )
    return risks
