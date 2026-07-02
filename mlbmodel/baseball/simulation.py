"""Deterministic overdispersed run simulation used as an unpromoted challenger."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mlbmodel.baseball.model import Probabilities


@dataclass(frozen=True)
class SimulationResult:
    iterations: int
    home_win_probability: float
    away_win_probability: float
    total_mean: float
    total_p10: float
    total_p50: float
    total_p90: float
    margin_p10: float
    margin_p50: float
    margin_p90: float


def _negative_binomial_params(mean: float, variance: float) -> tuple[float, float]:
    variance = max(variance, mean + 0.05)
    shape = mean * mean / (variance - mean)
    probability = shape / (shape + mean)
    return shape, probability


def simulate_game(
    probabilities: Probabilities,
    *,
    team_runs_sd: float,
    iterations: int = 25000,
    seed: int = 7,
) -> SimulationResult:
    """Simulate team runs with variance anchored to settled MLB results."""
    rng = np.random.default_rng(seed)
    variance = team_runs_sd * team_runs_sd
    away_shape, away_probability = _negative_binomial_params(
        probabilities.exp_away_runs, variance
    )
    home_shape, home_probability = _negative_binomial_params(
        probabilities.exp_home_runs, variance
    )
    away_runs = rng.negative_binomial(
        away_shape, away_probability, size=iterations
    )
    home_runs = rng.negative_binomial(
        home_shape, home_probability, size=iterations
    )
    ties = home_runs == away_runs
    home_wins = home_runs > away_runs
    tie_breaks = rng.random(iterations) < 0.5
    resolved_home_wins = home_wins | (ties & tie_breaks)
    totals = home_runs + away_runs
    margins = home_runs - away_runs
    return SimulationResult(
        iterations=iterations,
        home_win_probability=round(float(resolved_home_wins.mean()), 4),
        away_win_probability=round(float(1 - resolved_home_wins.mean()), 4),
        total_mean=round(float(totals.mean()), 2),
        total_p10=round(float(np.quantile(totals, 0.10)), 1),
        total_p50=round(float(np.quantile(totals, 0.50)), 1),
        total_p90=round(float(np.quantile(totals, 0.90)), 1),
        margin_p10=round(float(np.quantile(margins, 0.10)), 1),
        margin_p50=round(float(np.quantile(margins, 0.50)), 1),
        margin_p90=round(float(np.quantile(margins, 0.90)), 1),
    )
