"""Feature engineering for the main predictive model.

Flattens the detected trends into a single numeric feature row the core model (XGBoost /
ensemble / NN) can ingest directly, plus a small set of derived interaction/aggregate terms.
Feature names are stable and namespaced so they can be joined per game_pk and weighted
dynamically downstream.
"""

from __future__ import annotations

from mlbmodel.trends.types import RUN_BOOST, RUN_SUPPRESSION, Trend


def trend_features(
    away: str,
    home: str,
    trends: list[Trend],
    away_edge: float,
    home_edge: float,
) -> dict[str, float]:
    """Return a flat {feature_name: value} row for the model."""
    feats: dict[str, float] = {
        "situational_edge_away": away_edge,
        "situational_edge_home": home_edge,
        "situational_edge_diff": round(away_edge - home_edge, 2),
    }

    # Pass through each trend's suggested feature (already namespaced by team).
    for t in trends:
        for name, value in (t.suggested_model_feature or {}).items():
            feats[name] = value

    # Aggregate, model-friendly summaries per side.
    for team, prefix in ((away, "away"), (home, "home")):
        team_trends = [t for t in trends if t.team == team and t.category != "park"]
        run_boost = sum(
            t.trend_score * t.effect_size
            for t in team_trends
            if t.direction == RUN_BOOST and t.category != "bullpen_fatigue"
        )
        run_supp = sum(
            t.trend_score * t.effect_size
            for t in team_trends
            if t.direction == RUN_SUPPRESSION
        )
        pen_fatigue = sum(
            t.trend_score * t.effect_size
            for t in team_trends
            if t.category == "bullpen_fatigue"
        )
        feats[f"{prefix}_offense_trend_signal"] = round(run_boost - run_supp, 3)
        feats[f"{prefix}_bullpen_fatigue_signal"] = round(pen_fatigue, 3)
        feats[f"{prefix}_dominant_trend_score"] = round(
            max((t.trend_score for t in team_trends), default=0.0), 3
        )

    # Interaction term the brief asks for: my fatigued pen × your hot offense.
    feats["away_off_vs_home_pen_interaction"] = round(
        feats.get("away_offense_trend_signal", 0.0) + feats.get("home_bullpen_fatigue_signal", 0.0),
        3,
    )
    feats["home_off_vs_away_pen_interaction"] = round(
        feats.get("home_offense_trend_signal", 0.0) + feats.get("away_bullpen_fatigue_signal", 0.0),
        3,
    )

    # Game-total leaning park signal (one entry; 0 if neutral).
    park = next((t for t in trends if t.category == "park"), None)
    if park is not None:
        feats["park_total_signal"] = round(
            park.effect_size * (1 if park.direction == RUN_BOOST else -1), 3
        )
    return feats
