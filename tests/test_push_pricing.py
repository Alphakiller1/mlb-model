"""Refunds must not become wins, losses, or artificial paired-market edges."""
from types import SimpleNamespace

import pytest

from mlbmodel.baseball.model import (
    margin_outcome_probabilities,
    market_outcome_probability,
    market_probability,
    negative_binomial_sf,
)
from mlbmodel.market.props import build_prop_board, market_report
from mlbmodel.market.settlement import conditional_win_probability
from mlbmodel.market.value import assess_value
from mlbmodel.report.matchup import _market_row


GAME = SimpleNamespace(home="BOS", away="NYY", game_signals=[])
PROBS = SimpleNamespace(
    exp_home_runs=4.8, exp_away_runs=4.2, exp_total=9.0,
    p_home_win=0.55, p_away_win=0.45,
)
ANCHORS = {"total_sd": 4.7, "team_sd": 3.3}


@pytest.mark.parametrize("market,side,mean,sd,line", [
    ("total", "over", 9.0, 4.7, 9.0),
    ("team_total", "BOS", 4.8, 3.3, 5.0),
])
def test_integer_totals_separate_pushes_and_price_only_decisions(market, side, mean, sd, line):
    over, push, _ = market_outcome_probability(
        market, side, line, GAME, PROBS, ANCHORS, "over"
    )
    under_side = "under" if market == "total" else side
    under, under_push, _ = market_outcome_probability(
        market, under_side, line, GAME, PROBS, ANCHORS, "under"
    )
    assert under == pytest.approx(1 - negative_binomial_sf(line - 1, mean, sd))
    assert push > 0.05
    assert under_push == pytest.approx(push)
    assert over + push + under == pytest.approx(1)
    priced_over, _ = market_probability(market, side, line, GAME, PROBS, ANCHORS, "over")
    priced_under, _ = market_probability(
        market, under_side, line, GAME, PROBS, ANCHORS, "under"
    )
    assert priced_over == pytest.approx(over / (over + under))
    assert priced_over + priced_under == pytest.approx(1)


def test_half_run_total_has_no_refund_and_preserves_previous_probability():
    probability, push, _ = market_outcome_probability(
        "total", "over", 8.5, GAME, PROBS, ANCHORS
    )
    priced, _ = market_probability("total", "over", 8.5, GAME, PROBS, ANCHORS)
    assert push == 0
    assert probability == priced == negative_binomial_sf(8.5, 9.0, 4.7)


@pytest.mark.parametrize("line", [-2, -1.5, 0, 1.5, 2])
def test_runline_convolution_preserves_mass_even_in_high_scoring_games(line):
    win, push = margin_outcome_probabilities(line, 8, 9, 5)
    loss, other_push = margin_outcome_probabilities(-line, 9, 8, 5)
    assert win + loss + push == pytest.approx(1, abs=1e-10)
    assert push == pytest.approx(other_push)
    assert (push > 0) == float(line).is_integer()


def test_refunded_stakes_reduce_ev_without_changing_fair_odds():
    # Win 30%, lose 50%, refund 20%: fair decimal odds 1 + 50/30;
    # at even money the actual net expectation is 0.30 - 0.50 = -0.20.
    probability = conditional_win_probability(0.3, 0.2)
    value = assess_value(
        probability, 100, 0.5, promotion_status="HOLD/ABSTAIN", push_probability=0.2
    )
    assert probability == pytest.approx(0.375)
    assert value.ev_per_unit == pytest.approx(-0.2)
    assert value.fair_odds == 167
    assert value.edge == pytest.approx(-0.125)


def test_matchup_row_passes_refund_mass_into_ev():
    quote = SimpleNamespace(
        best_odds=100, vigfree_probability=0.5, best_book="draftkings",
        hold=0.0, book_count=1, fetched_at="2026-09-06T12:00:00Z",
    )
    row = _market_row("total", "under", 9, None, GAME, PROBS, ANCHORS, quote, "HOLD/ABSTAIN")
    over, push, _ = market_outcome_probability("total", "over", 9, GAME, PROBS, ANCHORS)
    assert row["push_probability"] == pytest.approx(push, abs=1e-6)
    assert row["ev"] == pytest.approx(1 - push - 2 * over, abs=1e-4)


def test_prop_report_compares_like_probabilities_and_preserves_actual_ev():
    board = build_prop_board([{
        "away_team": "New York Yankees", "home_team": "Boston Red Sox",
        "bookmakers": [{"key": "draftkings", "markets": [{
            "key": "pitcher_strikeouts", "outcomes": [
                {"name": side, "description": "Test Pitcher", "price": 100, "point": 5}
                for side in ("Over", "Under")
            ],
        }]}],
    }], "2026-09-06T12:00:00Z")
    pitcher = {"pitcher": "Test Pitcher", "projections": {
        "K": {"mean": 4.8, "sd": 1, "pmf": {"4": 0.5, "5": 0.2, "6": 0.3}}
    }}
    reports = {row["side"]: row for row in market_report(pitcher, board)}
    assert reports["over"]["model_probability"] == pytest.approx(0.375)
    assert reports["under"]["model_probability"] == pytest.approx(0.625)
    assert reports["over"]["ev"] == pytest.approx(-0.2)
    assert reports["under"]["ev"] == pytest.approx(0.2)
    assert reports["under"]["push_probability"] == pytest.approx(0.2)


def test_certain_refund_has_zero_ev_and_no_action():
    probability = conditional_win_probability(0, 1)
    value = assess_value(
        probability, 110, 0.5, promotion_status="PROMOTE", push_probability=1
    )
    assert value.ev_per_unit == 0
    assert value.action != "BET"


@pytest.mark.parametrize("win,push", [(0.5, 0.6), (-0.1, 0), (float("nan"), 0)])
def test_invalid_probabilities_cannot_be_priced(win, push):
    with pytest.raises(ValueError):
        conditional_win_probability(win, push)
