from mlbmodel.baseball.model import Probabilities
from mlbmodel.baseball.simulation import simulate_game


def test_simulation_is_deterministic_and_ordered():
    probabilities = Probabilities(
        exp_away_runs=4.2,
        exp_home_runs=4.8,
        exp_total=9.0,
        exp_margin=0.6,
        p_home_win=0.55,
        p_away_win=0.45,
        factors=[],
    )
    first = simulate_game(probabilities, team_runs_sd=3.2, iterations=5000, seed=19)
    second = simulate_game(probabilities, team_runs_sd=3.2, iterations=5000, seed=19)
    assert first == second
    assert first.total_p10 <= first.total_p50 <= first.total_p90
    assert first.margin_p10 <= first.margin_p50 <= first.margin_p90
    assert 0 < first.home_win_probability < 1
