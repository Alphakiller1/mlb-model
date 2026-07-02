from mlbmodel.portfolio.risk import fractional_kelly, summarize_positions


def test_unpromoted_strategy_has_zero_sizing():
    assert fractional_kelly(0.60, -110, promoted=False) == 0


def test_promoted_sizing_is_capped():
    assert fractional_kelly(0.70, 120, promoted=True) == 0.02


def test_summary_flags_game_concentration():
    summary = summarize_positions([
        {"game_pk": 1, "stake_units": 1.5},
        {"game_pk": 1, "stake_units": 1.0},
        {"game_pk": 2, "stake_units": 0.5},
    ])
    assert summary.total_units_at_risk == 3
    assert summary.games_exposed == 2
    assert summary.concentrated_games == (1,)
