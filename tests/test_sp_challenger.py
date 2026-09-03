"""Tests for the walk-forward SP harness and the challenger projection engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mlbmodel.backtest.sp_backtest import (
    add_opponent_priors,
    add_pitcher_priors,
    innings_to_outs,
    league_rates,
    score,
    shrunk_rate,
)
from mlbmodel.props.challenger import (
    FITTED,
    LEAGUE_PRIORS,
    OUTS_BOUNDS,
    OpponentForm,
    StarterForm,
    expected_earned_runs,
    expected_outs,
    project_start,
)


def _log(rows):
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["outs"] = frame["IP"].map(innings_to_outs)
    frame["bf"] = frame["batters_faced"]
    return frame


SAMPLE = _log([
    {"pitcher_id": 1, "opponent_team": "AAA", "date": "2026-04-01", "game_pk": 1,
     "IP": 6.0, "batters_faced": 24, "K": 8, "BB": 2, "H": 4, "HR": 1, "ER": 2},
    {"pitcher_id": 1, "opponent_team": "BBB", "date": "2026-04-08", "game_pk": 2,
     "IP": 5.0, "batters_faced": 22, "K": 4, "BB": 3, "H": 7, "HR": 0, "ER": 5},
    {"pitcher_id": 2, "opponent_team": "AAA", "date": "2026-04-02", "game_pk": 3,
     "IP": 7.0, "batters_faced": 26, "K": 10, "BB": 1, "H": 3, "HR": 0, "ER": 0},
])


# ---------- harness ----------

def test_innings_notation_converts_thirds_not_tenths():
    assert innings_to_outs(6.0) == 18
    assert innings_to_outs(6.1) == 19
    assert innings_to_outs(6.2) == 20
    # 6.3 is not valid innings notation and must not silently become 6.3 innings
    assert innings_to_outs(6.3) == 18


def test_pitcher_priors_never_include_the_current_start():
    """Constitution STD-5: rolling stats for game i use only games < i."""
    frame = add_pitcher_priors(SAMPLE)
    first = frame[(frame["pitcher_id"] == 1) & (frame["game_pk"] == 1)].iloc[0]
    assert first["p_starts"] == 0
    assert pd.isna(first["p_bf"])  # nothing known before a pitcher's first start
    second = frame[(frame["pitcher_id"] == 1) & (frame["game_pk"] == 2)].iloc[0]
    assert second["p_starts"] == 1
    assert second["p_bf"] == 24  # only the first start
    assert second["p_k_num"] == 8


def test_opponent_priors_never_include_the_current_start():
    frame = add_opponent_priors(SAMPLE)
    # AAA's second appearance (game 3) may only see game 1.
    row = frame[(frame["opponent_team"] == "AAA") & (frame["game_pk"] == 3)].iloc[0]
    assert row["o_games"] == 1
    assert row["o_bf"] == 24
    assert row["o_k_num"] == 8


def test_league_rates_are_pooled_not_averaged_per_start():
    rates = league_rates(SAMPLE)
    assert rates["k"] == pytest.approx((8 + 4 + 10) / (24 + 22 + 26))


def test_shrunk_rate_pulls_thin_samples_toward_the_prior():
    # One strikeout in four batters, shrunk hard, must land near the league prior.
    assert shrunk_rate([1], [4], 0.22, 100.0)[0] == pytest.approx(
        (1 + 100 * 0.22) / (4 + 100)
    )
    # With no shrinkage the observed rate survives intact.
    assert shrunk_rate([1], [4], 0.22, 0.0)[0] == pytest.approx(0.25)


def test_score_reports_negative_r2_when_worse_than_the_mean():
    actual = np.array([1.0, 2.0, 3.0, 4.0])
    card = score("x", np.full(4, 10.0), actual)
    assert card.r2_vs_league < 0
    assert card.bias == pytest.approx(10 - 2.5)


# ---------- challenger engine ----------

def _starter(**kwargs):
    base = {
        "starts": 20, "batters_faced": 500.0, "outs_total": 360.0,
        "outs_mean": 18.0, "outs_last3": 18.0, "strikeouts": 125.0,
        "walks": 40.0, "hits": 105.0, "homers": 15.0, "earned_runs": 55.0,
    }
    return StarterForm(**{**base, **kwargs})


def _opponent(**kwargs):
    base = {
        "games": 120, "batters_faced": 2600.0, "outs": 1840.0, "strikeouts": 570.0,
        "walks": 215.0, "hits": 575.0, "homers": 85.0, "earned_runs": 290.0,
    }
    return OpponentForm(**{**base, **kwargs})


def test_thin_history_is_pulled_toward_league_not_trusted():
    """A one-start pitcher must not project his one-start rate."""
    elite_once = _starter(starts=1, batters_faced=20.0, strikeouts=14.0, outs_total=18.0,
                          outs_mean=18.0, outs_last3=18.0)
    established = _starter()
    thin = project_start(elite_once, _opponent(), iterations=2000)
    known = project_start(established, _opponent(), iterations=2000)
    # 70% strikeout rate over 20 batters must regress far below itself...
    assert thin.rates["k"] < 0.40
    # ...and land nearer the league prior than the established 25% arm's projection.
    assert abs(thin.rates["k"] - LEAGUE_PRIORS["k"]) < abs(thin.rates["k"] - 0.70)
    assert known.rates["k"] > LEAGUE_PRIORS["k"]


def test_opponent_has_no_effect_on_hits_or_earned_runs():
    """Fitted opponent weight is zero for both; the engine must honour that."""
    assert FITTED["h"]["opponent_weight"] == 0.0
    assert FITTED["er"]["opponent_weight"] == 0.0
    pitcher = _starter()
    weak = _opponent(hits=400.0, earned_runs=180.0)
    strong = _opponent(hits=750.0, earned_runs=420.0)
    assert project_start(pitcher, weak, iterations=1500).rates["h"] == pytest.approx(
        project_start(pitcher, strong, iterations=1500).rates["h"]
    )
    outs = expected_outs(pitcher)
    assert expected_earned_runs(pitcher, weak, outs) == pytest.approx(
        expected_earned_runs(pitcher, strong, outs)
    )


def test_opponent_does_move_strikeouts():
    """Strikeouts is the one market where the opponent term earned full weight."""
    pitcher = _starter()
    whiffy = _opponent(strikeouts=800.0)
    contact = _opponent(strikeouts=380.0)
    assert (
        project_start(pitcher, whiffy, iterations=1500).rates["k"]
        > project_start(pitcher, contact, iterations=1500).rates["k"]
    )


def test_outs_projection_stays_inside_a_realistic_start():
    absurd = _starter(starts=2, outs_mean=27.0, outs_last3=27.0)
    assert OUTS_BOUNDS[0] <= expected_outs(absurd) <= OUTS_BOUNDS[1]
    empty = StarterForm()
    assert expected_outs(empty) == pytest.approx(LEAGUE_PRIORS["outs"])


def test_hits_is_flagged_low_confidence_regardless_of_sample():
    result = project_start(_starter(starts=30), _opponent(), iterations=1500)
    assert result.confidence["H"] == "low"
    assert result.confidence["K"] == "high"


def test_run_environment_moves_earned_runs_but_not_strikeouts():
    pitcher, opponent = _starter(), _opponent()
    neutral = project_start(pitcher, opponent, run_environment=1.0, iterations=4000)
    hot = project_start(pitcher, opponent, run_environment=1.15, iterations=4000)
    assert hot.means["ER"] > neutral.means["ER"]
    assert hot.means["K"] == pytest.approx(neutral.means["K"])


def test_projection_is_deterministic_for_a_seed():
    """Constitution STD-3: re-running yields identical numbers."""
    args = dict(iterations=2000, seed=99)
    first = project_start(_starter(), _opponent(), **args)
    second = project_start(_starter(), _opponent(), **args)
    assert first.distributions == second.distributions
