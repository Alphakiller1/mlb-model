"""Dominant Situational Trends — detection, scoring, narration, and model features.

Surfaces the highest-signal, context-matched situational trends for an upcoming MLB game
(bullpen fatigue, recent offense vs the opposing starter's hand, starter-quality × form
interactions, park run environment), grounded only in materialized MLBMA data. Produces a
structured per-trend record, a 0–100 per-team Situational Edge Score, a flat feature row for
the predictive model, and a human-readable narrative.

Primary entry points:
    build_situational_report(repo, away, home) -> SituationalEdge
    build_slate_reports(repo) -> list[SituationalEdge]
    trend_features_for_game(repo, away, home) -> dict[str, float]
"""

from mlbmodel.trends.report import (
    build_situational_report,
    build_slate_reports,
    trend_features_for_game,
)
from mlbmodel.trends.types import SituationalEdge, Trend

__all__ = [
    "build_situational_report",
    "build_slate_reports",
    "trend_features_for_game",
    "SituationalEdge",
    "Trend",
]
