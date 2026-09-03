"""Totals pricing must respect the right skew of MLB run distributions."""
from __future__ import annotations

import pytest

from mlbmodel.baseball.metrics import combined_offense_factor
from mlbmodel.baseball.model import (
    TeamContext,
    margin_cover_probability,
    negative_binomial_sf,
    normal_cdf,
)

# Empirical P(total > line) over 1,830 completed 2026 games, mean 9.005 / sd 4.690.
LEAGUE_TOTAL_MEAN = 9.005
LEAGUE_TOTAL_SD = 4.690
EMPIRICAL_OVER = {6.5: 0.6798, 7.5: 0.5678, 8.5: 0.4831, 9.5: 0.3962, 10.5: 0.3366}
# Empirical P(team runs > line) over the same games, mean 4.502 / sd 3.276.
LEAGUE_TEAM_MEAN = 4.502
LEAGUE_TEAM_SD = 3.276
EMPIRICAL_TEAM_OVER = {2.5: 0.6847, 3.5: 0.5530, 4.5: 0.4342, 5.5: 0.3303}


def _normal_over(line, mean, sd):
    return 1 - normal_cdf((line - mean) / sd)


@pytest.mark.parametrize("line,empirical", sorted(EMPIRICAL_OVER.items()))
def test_total_pricing_tracks_the_real_distribution(line, empirical):
    assert negative_binomial_sf(line, LEAGUE_TOTAL_MEAN, LEAGUE_TOTAL_SD) == pytest.approx(
        empirical, abs=0.015
    )


@pytest.mark.parametrize("line,empirical", sorted(EMPIRICAL_TEAM_OVER.items()))
def test_team_total_pricing_tracks_the_real_distribution(line, empirical):
    assert negative_binomial_sf(line, LEAGUE_TEAM_MEAN, LEAGUE_TEAM_SD) == pytest.approx(
        empirical, abs=0.015
    )


def test_skewed_pricing_beats_the_normal_it_replaced():
    """The normal overstated the Over at every line; that is why it was replaced."""
    normal_error = 0.0
    skewed_error = 0.0
    for line, empirical in EMPIRICAL_OVER.items():
        normal_value = _normal_over(line, LEAGUE_TOTAL_MEAN, LEAGUE_TOTAL_SD)
        assert normal_value > empirical, "the normal's Over bias is the documented defect"
        normal_error += abs(normal_value - empirical)
        skewed_error += abs(
            negative_binomial_sf(line, LEAGUE_TOTAL_MEAN, LEAGUE_TOTAL_SD) - empirical
        )
    assert skewed_error < normal_error / 3


def test_a_run_total_is_priced_below_its_own_mean():
    """Right skew means the median sits below the mean, so P(over the mean) < 0.5."""
    at_mean = negative_binomial_sf(LEAGUE_TOTAL_MEAN, LEAGUE_TOTAL_MEAN, LEAGUE_TOTAL_SD)
    assert at_mean < 0.47


def test_survival_is_monotonic_and_bounded():
    previous = 1.1
    for line in range(0, 25):
        value = negative_binomial_sf(line + 0.5, LEAGUE_TOTAL_MEAN, LEAGUE_TOTAL_SD)
        assert 0.0 <= value <= 1.0
        assert value < previous
        previous = value


# ---------- run line ----------

# 2026 league: home 4.593 / away 4.412 runs, team sd 3.276, over 1,830 games.
HOME_RUNS, AWAY_RUNS, TEAM_SD = 4.593, 4.412, 3.276


def test_runline_cover_matches_observed_frequency():
    """Home -1.5 covered 37.7% and home +1.5 covered 65.1% across 1,830 games."""
    assert margin_cover_probability(-1.5, HOME_RUNS, AWAY_RUNS, TEAM_SD) == pytest.approx(
        0.3770, abs=0.02
    )
    assert margin_cover_probability(1.5, HOME_RUNS, AWAY_RUNS, TEAM_SD) == pytest.approx(
        0.6508, abs=0.02
    )


def test_runline_sides_are_complementary_across_the_zero_margin():
    """Taking -1.5 and giving +1.5 partition the outcome space at the same threshold."""
    favourite = margin_cover_probability(-1.5, HOME_RUNS, AWAY_RUNS, TEAM_SD)
    underdog = margin_cover_probability(1.5, AWAY_RUNS, HOME_RUNS, TEAM_SD)
    assert favourite + underdog == pytest.approx(1.0, abs=0.01)


def test_runline_models_the_one_run_pileup_better_than_a_normal():
    """One-run games are 26.6% of real games; a normal on the margin says 17.0%."""
    one_run = (
        margin_cover_probability(-0.5, HOME_RUNS, AWAY_RUNS, TEAM_SD)
        - margin_cover_probability(-1.5, HOME_RUNS, AWAY_RUNS, TEAM_SD)
    ) + (
        margin_cover_probability(1.5, HOME_RUNS, AWAY_RUNS, TEAM_SD)
        - margin_cover_probability(0.5, HOME_RUNS, AWAY_RUNS, TEAM_SD)
    )
    assert one_run > 0.18


# ---------- offense consolidation ----------

def _context(**kwargs):
    base = {"osi": 55.0, "abq": 55.0, "rcv": 55.0, "obr": 55.0}
    return TeamContext(**{**base, **kwargs})


def test_correlated_offense_inputs_do_not_compound():
    """Six views of the same lineup must not multiply into six independent edges."""
    context = _context()
    single, _ = combined_offense_factor(context, 60.0, "R")
    stacked, _ = combined_offense_factor(
        context, 60.0, "R", lineup_factor=1.03, trend_factor=1.03
    )
    # Adding two more correlated readings may move the factor, but nowhere near the
    # 1.03 * 1.03 = 1.0609 that multiplying them would have produced.
    assert stacked > single
    assert stacked / single < 1.045


def test_offense_attribution_names_its_contributors():
    _, parts = combined_offense_factor(_context(), 60.0, "R", lineup_factor=1.02)
    names = [name for name, _ in parts]
    assert "season offense" in names
    assert "posted lineup" in names


def test_league_average_offense_is_neutral():
    factor, _ = combined_offense_factor(TeamContext(), 50.0, "R")
    assert factor == pytest.approx(1.0, abs=1e-9)
