"""Tests for the situational-trends module — hermetic (synthetic tables, no live data)."""

from __future__ import annotations

import pandas as pd

from mlbmodel.trends.context import SituationalContext, TeamSituation
from mlbmodel.trends.detectors import (
    detect_bullpen_fatigue,
    detect_form_vs_hand,
    run_detectors,
)
from mlbmodel.trends.features import trend_features
from mlbmodel.trends.narrative import build_narrative
from mlbmodel.trends.scoring import (
    rank_and_score,
    score_trend,
    team_edge_scores,
)
from mlbmodel.trends.types import RUN_BOOST, RUN_SUPPRESSION, SituationalEdge, Trend


def _ctx(tables: dict[str, pd.DataFrame], away="NYY", home="BOS", away_hand="R", home_hand="L"):
    """Build a context directly with injected tables (bypassing repo I/O)."""
    away_sit = TeamSituation(away, "away", "Away SP", away_hand, home, "Home SP", home_hand)
    home_sit = TeamSituation(home, "home", "Home SP", home_hand, away, "Away SP", away_hand)
    return SituationalContext(
        repo=None, slate_date="2026-06-27", away=away, home=home,
        away_situation=away_sit, home_situation=home_sit,
        park_factor=1.12, stadium="Fenway Park", _cache=dict(tables),
    )


def _trend(**kw) -> Trend:
    base = dict(
        trend_id="t", team="NYY", side="away", category="form_vs_hand",
        trend_description="d", situation_key="k", direction=RUN_BOOST,
        sample_size=10, effect_size=1.2, z_score=1.2, significance="strong",
        confidence="high", relevance=0.9,
    )
    base.update(kw)
    return Trend(**base)


# ── scoring ────────────────────────────────────────────────────────────────────
def test_score_trend_bounded_and_monotonic():
    weak = _trend(effect_size=0.3, sample_size=3, relevance=0.4)
    strong = _trend(effect_size=2.0, sample_size=12, relevance=1.0)
    assert 0.0 <= score_trend(weak) <= 1.0
    assert 0.0 <= score_trend(strong) <= 1.0
    assert score_trend(strong) > score_trend(weak)


def test_edge_scores_in_range_and_lean():
    trends = rank_and_score([
        _trend(team="NYY", direction=RUN_BOOST, effect_size=1.8, category="form_vs_hand"),
        _trend(team="BOS", direction=RUN_SUPPRESSION, effect_size=1.5, category="form_vs_hand"),
    ])
    away, home, lean = team_edge_scores("NYY", "BOS", trends)
    assert 0 <= away <= 100 and 0 <= home <= 100
    assert away > home and lean == "NYY"


def test_bullpen_fatigue_hurts_its_own_team():
    trends = rank_and_score([
        _trend(team="NYY", category="bullpen_fatigue", direction=RUN_BOOST, effect_size=1.6),
    ])
    away, home, lean = team_edge_scores("NYY", "BOS", trends)
    assert away < 50  # fatigue is a negative for the team that owns the pen


# ── features ─────────────────────────────────────────────────────────────────
def test_trend_features_shape_and_interactions():
    trends = rank_and_score([
        _trend(team="NYY", category="form_vs_hand", direction=RUN_BOOST, effect_size=1.5,
               suggested_model_feature={"NYY_l10_wrcplus_vs_Lhp_z": 1.5}),
        _trend(team="BOS", category="bullpen_fatigue", direction=RUN_BOOST, effect_size=1.2,
               suggested_model_feature={"BOS_bullpen_recent_load_z": 1.2}),
    ])
    away, home, _ = team_edge_scores("NYY", "BOS", trends)
    feats = trend_features("NYY", "BOS", trends, away, home)
    assert feats["situational_edge_away"] == away
    assert "NYY_l10_wrcplus_vs_Lhp_z" in feats
    assert "BOS_bullpen_recent_load_z" in feats
    # NYY hot offense vs BOS tired pen should be a positive interaction.
    assert feats["away_off_vs_home_pen_interaction"] > 0


# ── detectors (synthetic) ──────────────────────────────────────────────────────
def test_bullpen_fatigue_detector_fires_on_heavy_load():
    # NYY pen heavily used over recent dates vs light league.
    rows = []
    for d in ("2026-06-23", "2026-06-24", "2026-06-25"):
        for _ in range(4):
            rows.append({"date": d, "pitcher_team": "NYY", "pitches": 22, "pitcher_id": 1,
                         "leverage_situation": "High", "inherited_runners": 1, "inherited_scored": 1})
        rows.append({"date": d, "pitcher_team": "BOS", "pitches": 10, "pitcher_id": 2,
                     "leverage_situation": "Low", "inherited_runners": 0, "inherited_scored": 0})
        for t in ("TBR", "TOR", "BAL"):
            rows.append({"date": d, "pitcher_team": t, "pitches": 12, "pitcher_id": 3,
                         "leverage_situation": "Low", "inherited_runners": 0, "inherited_scored": 0})
    ctx = _ctx({"reliever_log": pd.DataFrame(rows)})
    t = detect_bullpen_fatigue(ctx, ctx.away_situation)
    assert t is not None and t.category == "bullpen_fatigue"
    assert t.z_score > 0.6 and t.direction == RUN_BOOST
    assert "NYY_bullpen_recent_load_z" in t.suggested_model_feature


def test_form_vs_hand_detector_directional():
    # NYY mashing LHP (high wRC+), league spread normal.
    rows = [
        {"team": "NYY", "opp_starter_hand": "L", "games": 10, "wins": 8, "wrc_plus": 135,
         "ops": 0.85, "qs_against_pct": 0.2},
        {"team": "BOS", "opp_starter_hand": "R", "games": 10, "wins": 4, "wrc_plus": 95,
         "ops": 0.70, "qs_against_pct": 0.5},
        {"team": "TBR", "opp_starter_hand": "L", "games": 10, "wins": 5, "wrc_plus": 98,
         "ops": 0.72, "qs_against_pct": 0.5},
        {"team": "TOR", "opp_starter_hand": "L", "games": 10, "wins": 5, "wrc_plus": 100,
         "ops": 0.73, "qs_against_pct": 0.5},
        {"team": "BAL", "opp_starter_hand": "L", "games": 10, "wins": 5, "wrc_plus": 92,
         "ops": 0.70, "qs_against_pct": 0.5},
    ]
    ctx = _ctx({"team_l10_sp_hand": pd.DataFrame(rows)})
    t = detect_form_vs_hand(ctx, ctx.away_situation)  # NYY faces LHP
    assert t is not None and t.direction == RUN_BOOST
    assert t.historical_record == "8-2"


# ── graceful empties + narrative ───────────────────────────────────────────────
def test_empty_tables_no_crash_even_edge():
    ctx = _ctx({})
    ctx.park_factor = None
    trends = run_detectors(ctx)
    away, home, lean = team_edge_scores(ctx.away, ctx.home, trends)
    assert away == 50.0 and home == 50.0 and lean == "even"


def test_narrative_flags_small_sample():
    edge = SituationalEdge(
        game="NYY@BOS", slate_date="2026-06-27", away="NYY", home="BOS",
        away_edge_score=55, home_edge_score=45, edge_lean="NYY",
        trends=[_trend(significance="small-sample", sample_size=3)],
    )
    lines = build_narrative(edge)
    assert any("small sample" in line for line in lines)
