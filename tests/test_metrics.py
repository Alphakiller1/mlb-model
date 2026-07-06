from mlbmodel.baseball.metrics import (
    offense_depth_factor,
    pitcher_allowed_skill_adjustment,
    trend_run_factor,
)
from mlbmodel.baseball.model import GameData, TeamContext, model_probabilities

ANCHORS = {
    "league_runs": 4.5,
    "margin_sd": 4.4,
    "home_winp": 0.54,
    "away_winp": 0.46,
}


def test_offense_depth_factor_uses_abq_rcv_pals():
    context = TeamContext(
        abq=58,
        rcv=56,
        pals=57,
        obr=52,
        proj_osi=54,
        osi_l7=55,
        osi_l14=50,
    )
    factor, detail = offense_depth_factor(context, slate_osi=50)
    assert detail["composite"] > 50
    assert factor > 1.0


def test_pitcher_allowed_adjusts_for_opponent_and_tiers():
    profile = {
        "OSI_allowed": 54,
        "ABQ_allowed": 53,
        "low_osi_ERA": 2.8,
        "high_osi_ERA": 4.6,
        "OOR_faced": 52,
    }
    weak = pitcher_allowed_skill_adjustment(profile, 46.0)
    strong = pitcher_allowed_skill_adjustment(profile, 56.0)
    assert strong > weak


def test_trend_run_factor_maps_feature_row():
    features = {
        "away_offense_trend_signal": 2.5,
        "home_bullpen_fatigue_signal": 1.0,
        "away_off_vs_home_pen_interaction": 1.5,
    }
    factor = trend_run_factor(features, "away")
    assert factor > 1.0


def test_signal_confidence_modifier():
    from mlbmodel.baseball.metrics import signal_confidence_modifier

    signals = [{"fired": True}] * 4
    assert signal_confidence_modifier(signals, "NYY", "BOS", "medium") == "high"
    assert signal_confidence_modifier([], "NYY", "BOS", "high") == "high"


def test_model_applies_offense_depth_when_metrics_present():
    game = GameData(
        game_pk=1,
        game_date="2026-06-27",
        start_time="7:10 PM ET",
        away="NYY",
        home="BOS",
        away_sp="A",
        home_sp="B",
        away_hand="R",
        home_hand="L",
        away_osi=50,
        home_osi=50,
        away_fip=4.2,
        home_fip=4.2,
        away_hr9=1.1,
        home_hr9=1.1,
        away_k=22,
        home_k=22,
        park_factor=1.0,
        away_context=TeamContext(abq=58, rcv=57, pals=56, osi_l7=54, osi_l14=49),
        home_context=TeamContext(),
    )
    probs = model_probabilities(game, ANCHORS)
    names = {factor.name for factor in probs.factors}
    assert "NYY offense depth (ABQ/RCV/PALS/proj)" in names
