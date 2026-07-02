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
    else:
        rain = gd.weather.get("precipitation_probability_pct")
        wind_out = gd.weather.get("wind_out_mph")
        if isinstance(rain, (int, float)) and rain >= 40:
            risks.append(
                RiskSignal(
                    f"Rain probability {rain:.0f}%",
                    "Weather",
                    "high",
                    "Delay risk can shorten starter outings and weaken outs/K projections",
                )
            )
        if isinstance(wind_out, (int, float)) and abs(wind_out) >= 10:
            direction = "out" if wind_out > 0 else "in"
            risks.append(
                RiskSignal(
                    f"Wind {direction} at {abs(wind_out):.0f} mph",
                    "Run environment",
                    "medium",
                    "Meaningfully changes home-run and total-run conditions",
                )
            )
    lineups = gd.live_context.get("lineups") or {}
    if any(
        (lineups.get(side) or {}).get("status") not in {"confirmed", "projected"}
        for side in ("away", "home")
    ):
        risks.append(
            RiskSignal(
                "Starting lineups not posted",
                "Lineup",
                "high",
                "Totals and pitcher props remain provisional until batting orders load",
            )
        )
    if (gd.live_context.get("umpire") or {}).get("status") != "announced":
        risks.append(
            RiskSignal(
                "Plate umpire not announced",
                "Umpire",
                "medium",
                "No umpire run adjustment is applied yet",
            )
        )
    for team, bullpen in (
        (gd.away, gd.away_bullpen_features),
        (gd.home, gd.home_bullpen_features),
    ):
        if (bullpen.get("workload_factor") or 1.0) >= 1.02:
            risks.append(
                RiskSignal(
                    f"{team} bullpen worked {bullpen.get('pitches_2d', 0):.0f} pitches in 2 days",
                    "Bullpen workload",
                    "medium",
                    "Raises late-inning run allowance and weakens full-game unders",
                )
            )
    return risks
