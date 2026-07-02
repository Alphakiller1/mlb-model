"""Trend ranking and the per-team Situational Edge Score.

``trend_score`` blends four ingredients the brief calls for — magnitude (effect size),
sample adequacy, recency/relevance, and a data-backed bonus — into a 0..1 rank used to pick
the "dominant" trends. ``situational_edge_score`` turns each team's signed contributions into
a 0..100 score where 50 is neutral, so the main model and a human read the same lean.
"""

from __future__ import annotations

import math

from mlbmodel.trends.types import RUN_BOOST, RUN_SUPPRESSION, Trend


# How much each ingredient moves the rank score.
_W_MAGNITUDE = 0.45
_W_SAMPLE = 0.20
_W_RELEVANCE = 0.25
_W_DATA = 0.10

# Category weights into the team edge score (a tired pen hurts run prevention; offense
# trends move scoring; park is game-level and excluded from one-sided edge).
_EDGE_WEIGHT = {
    "form_vs_hand": 1.0,
    "starter_quality": 0.85,
    "bullpen_fatigue": 0.9,
    "platoon": 0.7,
    "park": 0.0,
}


def _sample_adequacy(sample: int) -> float:
    # Saturating curve: 0 at n=0, ~0.6 at n=6, ~0.8 at n=10, →1.
    if sample <= 0:
        return 0.35  # structural signals (e.g. park) still carry some weight
    return min(1.0, 1 - math.exp(-sample / 7.0))


def score_trend(trend: Trend) -> float:
    magnitude = min(1.0, trend.effect_size / 2.0)         # 2 SD ≈ max
    sample = _sample_adequacy(trend.sample_size)
    relevance = max(0.0, min(1.0, trend.relevance))
    data = 1.0 if trend.data_backed else 0.4
    score = (
        _W_MAGNITUDE * magnitude
        + _W_SAMPLE * sample
        + _W_RELEVANCE * relevance
        + _W_DATA * data
    )
    return round(min(1.0, score), 4)


def signed_team_contribution(trend: Trend) -> tuple[str, float]:
    """Return (team, signed contribution) toward that team's edge score.

    Positive helps the team. Offensive trends sign by run direction; a fatigued bullpen is
    always a negative for the team that owns it (its run prevention is compromised).
    """
    weight = _EDGE_WEIGHT.get(trend.category, 0.5)
    if weight == 0.0:
        return trend.team, 0.0
    base = trend.trend_score * trend.effect_size * weight
    if trend.category == "bullpen_fatigue":
        return trend.team, -abs(base)
    if trend.direction == RUN_BOOST:
        return trend.team, abs(base)
    if trend.direction == RUN_SUPPRESSION:
        return trend.team, -abs(base)
    return trend.team, 0.0


def _to_edge_score(net: float) -> float:
    # Squash net signed contribution (~[-3, 3]) to 0..100 around 50.
    return round(50.0 + 50.0 * math.tanh(net / 2.5), 1)


def rank_and_score(trends: list[Trend]) -> list[Trend]:
    for t in trends:
        t.trend_score = score_trend(t)
    return sorted(trends, key=lambda t: t.trend_score, reverse=True)


def team_edge_scores(away: str, home: str, trends: list[Trend]) -> tuple[float, float, str]:
    nets = {away: 0.0, home: 0.0}
    for t in trends:
        team, contrib = signed_team_contribution(t)
        if team in nets:
            nets[team] += contrib
    away_score = _to_edge_score(nets[away])
    home_score = _to_edge_score(nets[home])
    spread = away_score - home_score
    lean = away if spread > 4 else home if spread < -4 else "even"
    return away_score, home_score, lean
