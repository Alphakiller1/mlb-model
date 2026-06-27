"""Enforces Constitution STD-7 (multiple-hypothesis / selection-bias control).

Checks the Deflated Sharpe Ratio and PBO behave correctly on cases with a KNOWN answer:
a genuinely strong single strategy should pass; a 'best of many noise strategies' should
not; PBO ~0.5 for pure noise and low for a true persistent winner.
"""
import random

from mlbmodel.quant.selection import (
    sharpe, deflated_sharpe_ratio, dsr_gate, probability_of_backtest_overfitting,
)

random.seed(7)


def test_sharpe_basic():
    assert sharpe([1.0, 1.0, 1.0]) == 0.0          # no variance
    assert sharpe([0.1, 0.2, 0.15, 0.05, 0.12]) > 0


def test_dsr_high_for_strong_single_trial():
    # strong, consistent positive returns, only 2 trials -> DSR should be high
    strong = [0.05 + random.gauss(0, 0.02) for _ in range(300)]
    dsr = deflated_sharpe_ratio(strong, n_trials=2, var_sr_across_trials=0.01)
    assert dsr > 0.95, dsr


def test_dsr_low_for_best_of_many_noise():
    # 50 pure-noise segments; pick the luckiest; DSR must NOT credit it
    segs = {f"s{i}": [random.gauss(0, 1) for _ in range(120)] for i in range(50)}
    res = dsr_gate(segs, threshold=0.95)
    assert res["ok"] is False, res
    assert res["dsr"] < 0.95, res


def test_pbo_high_for_noise():
    # T periods x N noise strategies -> PBO near 0.5 (no real skill persists)
    M = [[random.gauss(0, 1) for _ in range(20)] for _ in range(40)]
    pbo = probability_of_backtest_overfitting(M, n_splits=8)
    assert 0.25 < pbo < 0.75, pbo


def test_pbo_low_for_true_winner():
    # strategy 0 has a real positive drift every period -> low overfitting probability
    M = []
    for _ in range(40):
        row = [random.gauss(0, 1) for _ in range(20)]
        row[0] = 1.5 + random.gauss(0, 0.3)      # persistent winner
        M.append(row)
    pbo = probability_of_backtest_overfitting(M, n_splits=8)
    assert pbo < 0.10, pbo
