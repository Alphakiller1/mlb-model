"""Pitch-mix arsenal features for expected-runs model."""
from __future__ import annotations

from mlbmodel.baseball.model import GameData


def arsenal_for(team: str, pitcher_rows: list[dict] | None) -> dict:
    """Opposing starter's bounded pitch-mix er_factor for the team that bats."""
    for row in pitcher_rows or []:
        if str(row.get("opponent") or "").upper() == str(team).upper():
            matchup = row.get("pitch_matchup") or {}
            if isinstance(matchup.get("er_factor"), (int, float)):
                return {
                    "er_factor": matchup.get("er_factor"),
                    "coverage_pct": matchup.get("coverage_pct"),
                    "batters_matched": matchup.get("lineup_batters_matched"),
                    "pitcher": row.get("pitcher"),
                }
    return {}


def attach_arsenal(gd: GameData, pitcher_rows: list[dict] | None) -> None:
    """Mutate GameData with arsenal-vs-lineup factors from the pitcher board."""
    gd.away_arsenal_features = arsenal_for(gd.away, pitcher_rows)
    gd.home_arsenal_features = arsenal_for(gd.home, pitcher_rows)
