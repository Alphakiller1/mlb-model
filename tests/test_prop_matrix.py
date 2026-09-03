"""Regression tests for the pitcher-prop matrix rebuild.

Every bug these cover failed *silently*: a factor returned a constant, or a distribution was
refitted to the wrong shape, and the board kept rendering plausible numbers. None of them
raised, so none of them showed up in a run log. These assert on behaviour that would be a
no-op if the bug came back.
"""
from __future__ import annotations

import numpy as np
import pytest

from mlbmodel.baseball.metrics import (
    LEAGUE_LHB_SHARE,
    SPLIT_SHRINK_BF,
    sp_split_skill_adjustment,
)
from mlbmodel.market.probability import p_over_exact, p_over_line_erf
from mlbmodel.props import matrix
from mlbmodel.props.model import _distribution


# --------------------------------------------------------------- exact-distribution pricing
def _skewed_counts(seed: int = 11, size: int = 120_000) -> np.ndarray:
    """A right-skewed count like earned runs: gamma-Poisson, skew ~1."""
    rng = np.random.default_rng(seed)
    return rng.poisson(rng.gamma(4.5, 2.5 / 4.5, size))


def test_distribution_carries_a_pmf_for_integer_markets():
    dist = _distribution(_skewed_counts()).as_dict()
    assert "pmf" in dist, "integer markets must carry the simulated PMF, not just (mean, sd)"
    assert abs(sum(dist["pmf"].values()) - 1.0) < 0.01


def test_distribution_carries_quantiles_for_continuous_markets():
    rng = np.random.default_rng(3)
    dist = _distribution(rng.normal(26.0, 8.0, 50_000)).as_dict()
    assert "q" in dist and len(dist["q"]) == 101
    assert "pmf" not in dist


def test_normal_overstates_over_on_a_skewed_market():
    """The bug this replaces: a symmetric normal priced a right-skewed count."""
    samples = _skewed_counts()
    projection = _distribution(samples).as_dict()
    line = 2.5
    exact, _push = p_over_exact(line, projection)
    normal = p_over_line_erf(line, projection["mean"], projection["sd"])
    truth = float((samples > line).mean())
    assert abs(exact - truth) < 0.005, "exact pricing must match the simulation it came from"
    # The normal is biased HIGH on the over, by several points — this is the whole defect.
    assert normal - truth > 0.03
    assert exact < normal


def test_exact_pricing_reports_push_on_a_whole_number_line():
    projection = _distribution(_skewed_counts()).as_dict()
    _over, push = p_over_exact(3.0, projection)
    assert push > 0.05, "a whole-number line can push; the under must not absorb it"
    _over_half, push_half = p_over_exact(3.5, projection)
    assert push_half == 0.0


def test_pricing_falls_back_to_the_normal_without_a_distribution():
    plain = {"mean": 5.0, "sd": 2.0}
    over, push = p_over_exact(5.5, plain)
    assert push == 0.0
    assert abs(over - p_over_line_erf(5.5, 5.0, 2.0)) < 1e-9


# ------------------------------------------------------------------- handedness platoon term
def _splits(pitcher_id, starts=20, innings=3.4, fip_l=5.2, fip_r=3.4, k_l=20.0, k_r=28.0):
    """Long-form rows shaped exactly like `sp_metric_splits.csv` (float ids included)."""
    return [
        {
            "pitcher_id": float(pitcher_id), "pitcher_name": "Test Arm",
            "split_dimension": "batter_hand", "split_value": "LHH",
            "starts": starts, "avg_IP": innings, "FIP": fip_l, "K_pct": k_l,
        },
        {
            "pitcher_id": float(pitcher_id), "pitcher_name": "Test Arm",
            "split_dimension": "batter_hand", "split_value": "RHH",
            "starts": starts, "avg_IP": innings, "FIP": fip_r, "K_pct": k_r,
        },
        {
            "pitcher_id": float(pitcher_id), "pitcher_name": "Test Arm",
            "split_dimension": "osi_tier", "split_value": "High",
            "starts": starts, "avg_IP": innings, "FIP": 4.0, "K_pct": 24.0,
        },
    ]


def test_platoon_resolves_the_real_long_form_schema():
    """It looked for a `split`/`split_type` column that has never existed in that file."""
    profile = {"pitcher_id": 434378, "pitcher_name": "Test Arm", "FIP": 4.3, "K_pct": 24.0}
    factor = sp_split_skill_adjustment(profile, _splits(434378), LEAGUE_LHB_SHARE)
    assert factor != 1.0, "a resolvable platoon split must move the factor off 1.0"


def test_platoon_matches_across_float_and_int_ids():
    """`sp_metric_splits` stores pitcher_id as float64; `sp_profiles` as int64.

    Probed at a lefty-heavy lineup, not 0.5: a symmetric platoon profile facing an exactly
    even lineup blends back to 1.0 by construction, which would mask a failed join.
    """
    profile = {"pitcher_id": 434378, "pitcher_name": "Test Arm", "FIP": 4.3, "K_pct": 24.0}
    assert sp_split_skill_adjustment(profile, _splits(434378), 0.85) != 1.0
    other = {"pitcher_id": 999999, "pitcher_name": "Someone Else", "FIP": 4.3, "K_pct": 24.0}
    assert sp_split_skill_adjustment(other, _splits(434378), 0.85) == 1.0


def test_even_lineup_against_a_symmetric_split_is_neutral():
    """Sanity anchor for the test above: neutrality at 0.5 is correct, not a broken join."""
    profile = {"pitcher_id": 5, "pitcher_name": "Test Arm", "FIP": 4.3, "K_pct": 24.0}
    assert sp_split_skill_adjustment(profile, _splits(5), 0.5) == pytest.approx(1.0, abs=1e-9)


def test_platoon_responds_to_the_lineup_not_the_pitchers_own_hand():
    """A split is a property of the batters faced, so the lineup must change the answer."""
    profile = {"pitcher_id": 1, "pitcher_name": "Test Arm", "FIP": 4.3, "K_pct": 24.0}
    rows = _splits(1)
    lefty_heavy = sp_split_skill_adjustment(profile, rows, 0.80)
    righty_heavy = sp_split_skill_adjustment(profile, rows, 0.10)
    assert lefty_heavy > righty_heavy, "this arm is worse vs LHB, so a lefty stack must raise it"
    assert abs(lefty_heavy - righty_heavy) > 0.005


def test_platoon_shrinks_a_one_start_split_toward_the_season_line():
    """Verlander's vs-LHH row was 1 start / 2.33 IP and pinned the factor at its clip."""
    profile = {"pitcher_id": 2, "pitcher_name": "Test Arm", "FIP": 7.75, "K_pct": 5.3}
    tiny = _splits(2, starts=1, innings=2.33, fip_l=10.4, fip_r=3.11, k_l=7.7, k_r=0.0)
    big = _splits(2, starts=25, innings=5.0, fip_l=10.4, fip_r=3.11, k_l=7.7, k_r=0.0)
    tiny_swing = abs(
        sp_split_skill_adjustment(profile, tiny, 0.8)
        - sp_split_skill_adjustment(profile, tiny, 0.1)
    )
    big_swing = abs(
        sp_split_skill_adjustment(profile, big, 0.8)
        - sp_split_skill_adjustment(profile, big, 0.1)
    )
    assert tiny_swing < big_swing / 2, "a 10-batter split must not move the board like a 500-batter one"


def test_platoon_is_neutral_without_split_rows():
    profile = {"pitcher_id": 3, "pitcher_name": "Test Arm", "FIP": 4.3, "K_pct": 24.0}
    assert sp_split_skill_adjustment(profile, [], 0.5) == 1.0
    assert sp_split_skill_adjustment(None, _splits(3), 0.5) == 1.0


def test_split_shrinkage_constant_is_a_real_sample_size():
    assert 50.0 < SPLIT_SHRINK_BF < 1000.0


# ------------------------------------------------------------------------ fitted matrix terms
def test_opponent_k_rate_spans_the_league_and_moves_strikeouts():
    logs = [
        {"opponent_team": "NYY", "K": 260, "batters_faced": 1000},
        {"opponent_team": "TBR", "K": 180, "batters_faced": 1000},
        {"opponent_team": "TIN", "K": 22, "batters_faced": 100},  # below the sample floor
    ]
    rates, league = matrix.opponent_strikeout_rates(logs)
    assert "NYY" in rates and "TBR" in rates
    assert "TIN" not in rates, "a club under the batters-faced floor must not move a projection"
    high, index_high = matrix.opponent_k_delta("NYY", rates, league)
    low, index_low = matrix.opponent_k_delta("TBR", rates, league)
    assert high > 0 > low
    assert index_high > 1.0 > index_low
    assert matrix.opponent_k_delta("ZZZ", rates, league) == (0.0, None)


def test_regression_signal_actually_changes_the_outs_projection():
    """It used to be computed, labelled on the board, and then discarded."""
    lucky = matrix.regression_outs_delta(0.240)     # BABIP well below league -> due to regress
    unlucky = matrix.regression_outs_delta(0.350)
    assert lucky < 0 < unlucky, "a lucky pitcher must project SHORTER, not identically"
    assert matrix.regression_outs_delta(matrix.LEAGUE_BABIP) == pytest.approx(0.0)
    assert matrix.regression_outs_delta(None) == 0.0


def test_regression_term_is_clipped_against_a_wild_babip():
    extreme = matrix.regression_outs_delta(0.050)
    bounded = matrix.regression_outs_delta(matrix.LEAGUE_BABIP - matrix.BABIP_LUCK_CLIP)
    assert extreme == pytest.approx(bounded), "an unclipped BABIP would invent a full inning"


def test_rest_term_is_centred_and_bounded():
    assert matrix.rest_outs_delta(5.0) == pytest.approx(0.0)
    assert matrix.rest_outs_delta(4.0) > 0 > matrix.rest_outs_delta(6.0)
    assert matrix.rest_outs_delta(40.0) == pytest.approx(matrix.rest_outs_delta(10.0))
    assert matrix.rest_outs_delta(None) == 0.0


def test_days_rest_parsing():
    assert matrix.days_rest("2026-08-25", "2026-08-31") == 6.0
    assert matrix.days_rest(None, "2026-08-31") is None
    assert matrix.days_rest("2026-08-31", "2026-08-31") is None, "a same-day repeat is not rest"
    assert matrix.days_rest("garbage", "2026-08-31") is None


def test_earned_runs_have_no_matrix_term():
    """Measured: every factor tested scored negative on ER. Adding one back needs evidence."""
    exported = {name for name in dir(matrix) if name.isupper()}
    assert not any("ER_" in name or name.endswith("_ER_WEIGHT") for name in exported), (
        "ER is not predictable beyond self-history — see docs/PROP-MATRIX-FINDINGS.md"
    )


# ------------------------------------------------------------------- pitch-mix matchup term
class _StubRepo:
    """Minimal repo: only the tables PitcherProjectionEngine reads at construction."""

    def __init__(self, tables):
        self._tables = tables

    def load(self, filename):
        import pandas as pd
        rows = self._tables.get(filename)
        return pd.DataFrame(rows) if rows else None

    def slate(self):
        return None


def _mix(source, name, **over):
    base = {
        "pitch_type": "SL", "pitch_name": "Slider", "pitches": 400,
        "pitch_pct": 100.0, "whiff_rate": 25.0, "xwoba": 0.300, "chase_rate": 28.0,
    }
    base.update(over)
    if source == "pitcher":
        base["full_name"] = name
    elif source == "batter":
        base["full_name"] = name
        base["player_id"] = 1
    else:
        base["team_abbr"] = name
    return base


def _engine(pitcher_whiff=25.0, team_whiff=25.0):
    from mlbmodel.props.model import PitcherProjectionEngine
    tables = {
        "pitch_mix_pitcher.csv": [_mix("pitcher", "Ace Arm", whiff_rate=pitcher_whiff)],
        "pitch_mix_team_batting.csv": [
            _mix("team", "AAA", whiff_rate=team_whiff),
            _mix("team", "BBB", whiff_rate=25.0),
        ],
        "pitch_mix_batter.csv": [_mix("batter", "Some Hitter")],
    }
    return PitcherProjectionEngine(_StubRepo(tables))


def test_pitch_mix_adjustment_ignores_the_pitchers_own_arsenal():
    """The engine already applies his season K rate; adding his stuff again double-counts.

    Measured on 3,790 starts: the pitcher half correlates +0.708 with his own season K rate
    and, once that is controlled for, +0.0027 with the outcome. Including it dropped the
    combined signal from +0.0858 to +0.0375.
    """
    weak, strong = _engine(pitcher_whiff=15.0), _engine(pitcher_whiff=40.0)
    lineup = {"players": []}
    weak_delta = weak._pitch_matchup("Ace Arm", "AAA", lineup)["k_rate_delta"]
    strong_delta = strong._pitch_matchup("Ace Arm", "AAA", lineup)["k_rate_delta"]
    assert weak_delta == strong_delta, (
        "the pitcher's own stuff must not move the pitch-mix adjustment"
    )


def test_pitch_mix_adjustment_still_responds_to_the_opponent():
    whiffy = _engine(team_whiff=40.0)._pitch_matchup("Ace Arm", "AAA", {"players": []})
    contact = _engine(team_whiff=15.0)._pitch_matchup("Ace Arm", "AAA", {"players": []})
    assert whiffy["k_rate_delta"] > contact["k_rate_delta"], (
        "a lineup that whiffs more must raise the strikeout adjustment"
    )


def test_pitcher_arsenal_is_still_reported_as_context():
    result = _engine(pitcher_whiff=40.0)._pitch_matchup("Ace Arm", "AAA", {"players": []})
    assert "pitcher_arsenal_score" in result and "opponent_response_score" in result
    assert result["score"] == result["opponent_response_score"]


def test_pitch_mix_reports_which_baseline_it_used():
    result = _engine()._pitch_matchup("Ace Arm", "AAA", {"players": []})
    assert result["baseline_source"] == "team"


def test_pitch_detail_has_no_fabricated_ops():
    """`lineup_ops` was the opponent's xwOBA under an OPS label, duplicating the next column."""
    result = _engine()._pitch_matchup("Ace Arm", "AAA", {"players": []})
    for pitch in result["pitches"]:
        assert "lineup_ops" not in pitch
        assert "er_factor_delta" in pitch, "the UI renders this per-pitch run delta"


# ----------------------------------------------------------------- per-market rate shrinkage
def test_rate_shrinkage_strengths_differ_by_an_order_of_magnitude():
    """One shared constant cannot express these: K stabilises ~4x faster than hits."""
    strengths = matrix.RATE_SHRINK_BF
    assert strengths["k"] < strengths["bb"] < strengths["h"]
    assert strengths["h"] / strengths["k"] > 3


def test_thin_sample_regresses_almost_fully_to_league():
    """A pitcher with no history must not project his own rate. This was the whole defect."""
    league = 0.214
    shrunk = matrix.shrink_rate(40.0, "k", batters_faced=0.0, league_rate=league)
    assert shrunk == pytest.approx(league * 100)


def test_large_sample_keeps_most_of_its_own_rate():
    league = 0.214
    shrunk = matrix.shrink_rate(30.0, "k", batters_faced=1000.0, league_rate=league)
    assert 27.0 < shrunk < 30.0, "a 1000-batter sample should keep most of its own signal"


def test_shrinkage_is_monotone_in_sample_size():
    league = 0.214
    values = [
        matrix.shrink_rate(32.0, "k", batters_faced=bf, league_rate=league)
        for bf in (0, 50, 150, 400, 1200)
    ]
    assert values == sorted(values), "more batters faced must mean less regression"


def test_hits_shrink_harder_than_strikeouts_at_equal_sample():
    league = 0.22
    k = matrix.shrink_rate(30.0, "k", 300.0, league)
    h = matrix.shrink_rate(30.0, "h", 300.0, league)
    assert abs(h - league * 100) < abs(k - league * 100)


def test_unknown_market_is_left_alone():
    assert matrix.shrink_rate(25.0, "er", 100.0, 0.2) == 25.0


def test_league_rates_come_from_the_log():
    logs = [
        {"K": 200, "BB": 80, "H": 220, "batters_faced": 1000},
        {"K": 0, "BB": 0, "H": 0, "batters_faced": 0},        # ignored
    ]
    rates = matrix.league_rates(logs)
    assert rates["k"] == pytest.approx(0.20)
    assert rates["bb"] == pytest.approx(0.08)
    assert rates["h"] == pytest.approx(0.22)
    fallback = matrix.league_rates([])
    assert 0.15 < fallback["k"] < 0.30


# ------------------------------------------------------------------ ER opponent-stack damping
def test_opponent_er_damping_is_between_zero_and_one():
    from mlbmodel.props.model import OPPONENT_ER_DAMPING
    assert 0.0 <= OPPONENT_ER_DAMPING < 1.0, (
        "opponent quality measured ~zero against per-start ER; it must not pass through whole"
    )


# ------------------------------------------------------------------- lineup vs its own baseline
def test_lineup_and_baseline_use_the_same_formula():
    """They used different formulas, so every posted lineup scored below its own club."""
    from mlbmodel.props.model import PitcherProjectionEngine as Engine
    rich = {"projOSI": 60.0, "ABQ": 55.0, "RCV": 50.0}
    assert Engine._batter_score(rich) == pytest.approx(0.55 * 60 + 0.25 * 55 + 0.20 * 50)
    # Falls back to OSI alone when the components are missing, rather than dropping the hitter.
    assert Engine._batter_score({"OSI": 47.0}) == 47.0
    assert Engine._batter_score({}) is None
