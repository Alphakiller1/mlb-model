"""
Selection-bias controls for strategy/segment scans (Constitution STD-7).

`market_edge` already applies Benjamini-Hochberg FDR for *discovery*. This module adds
the missing *selection* controls for choosing a strategy out of many trials:

  * Probabilistic Sharpe Ratio (PSR) and the **Deflated Sharpe Ratio (DSR)** —
    Bailey & Lopez de Prado (2014). DSR is the probability the true Sharpe > 0 after
    correcting for (a) the number of trials and (b) non-normal (skewed/fat-tailed) returns.
  * **Probability of Backtest Overfitting (PBO)** via Combinatorial Symmetric
    Cross-Validation (CSCV) — the fraction of train/test splits where the in-sample-best
    strategy lands below the median out-of-sample.

Pure stdlib (uses statistics.NormalDist for the normal CDF / inverse-CDF). No network.
These are the functions the promotion gate calls before any segment may be called tradeable.
"""
from __future__ import annotations

import math
from itertools import combinations
from statistics import NormalDist

_N = NormalDist()
EULER = 0.5772156649015329  # Euler-Mascheroni gamma


# ── Sharpe + moments (per-observation, not annualized) ───────────────────────
def sharpe(returns: list[float]) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    m = sum(returns) / n
    var = sum((x - m) ** 2 for x in returns) / (n - 1)
    sd = math.sqrt(var)
    return m / sd if sd > 0 else 0.0


def _skew_kurt(returns: list[float]) -> tuple[float, float]:
    """Return (skew, kurtosis) with kurtosis NON-excess (normal == 3.0)."""
    n = len(returns)
    m = sum(returns) / n
    var = sum((x - m) ** 2 for x in returns) / n
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0, 3.0
    skew = sum(((x - m) / sd) ** 3 for x in returns) / n
    kurt = sum(((x - m) / sd) ** 4 for x in returns) / n
    return skew, kurt


# ── Probabilistic & Deflated Sharpe Ratio ────────────────────────────────────
def probabilistic_sharpe_ratio(sr_hat: float, sr_benchmark: float, T: int,
                               skew: float, kurt: float) -> float:
    """P(true SR > sr_benchmark) given observed SR, sample size T, skew, kurtosis
    (non-excess). Bailey & Lopez de Prado (2012)."""
    if T < 2:
        return 0.0
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr_hat + (kurt - 1.0) / 4.0 * sr_hat ** 2))
    z = (sr_hat - sr_benchmark) * math.sqrt(T - 1) / denom
    return _N.cdf(z)


def expected_max_sharpe(n_trials: int, var_sr_across_trials: float) -> float:
    """E[max Sharpe] under the null of n independent trials with cross-trial
    Sharpe variance V — the deflation benchmark SR0."""
    if n_trials < 2 or var_sr_across_trials <= 0:
        return 0.0
    a = _N.inv_cdf(1.0 - 1.0 / n_trials)
    b = _N.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(var_sr_across_trials) * ((1.0 - EULER) * a + EULER * b)


def deflated_sharpe_ratio(returns: list[float], n_trials: int,
                          var_sr_across_trials: float) -> float:
    """DSR = PSR evaluated at the deflated benchmark SR0. Probability (0..1) that the
    selected strategy's true Sharpe > 0 after multiple-testing + non-normality."""
    sr = sharpe(returns)
    skew, kurt = _skew_kurt(returns)
    sr0 = expected_max_sharpe(n_trials, var_sr_across_trials)
    return probabilistic_sharpe_ratio(sr, sr0, len(returns), skew, kurt)


def dsr_gate(segment_returns: dict[str, list[float]], threshold: float = 0.95) -> dict:
    """Apply DSR to the BEST segment selected out of all tested segments.

    segment_returns: {label: per-bet ROI series}. Returns the selected segment, its DSR,
    and pass/fail vs threshold. This is what the promotion gate calls on market_edge's
    per-segment ROI series before a segment may be called tradeable (Constitution STD-7)."""
    usable = {k: v for k, v in segment_returns.items() if len(v) >= 2}
    if len(usable) < 2:
        return {"ok": False, "reason": "need >=2 segments with >=2 obs", "dsr": None}
    sharpes = {k: sharpe(v) for k, v in usable.items()}
    best = max(sharpes, key=sharpes.get)
    mean_sr = sum(sharpes.values()) / len(sharpes)
    var_sr = sum((s - mean_sr) ** 2 for s in sharpes.values()) / (len(sharpes) - 1)
    dsr = deflated_sharpe_ratio(usable[best], n_trials=len(usable), var_sr_across_trials=var_sr)
    return {"ok": dsr >= threshold, "selected": best, "dsr": round(dsr, 4),
            "n_trials": len(usable), "threshold": threshold,
            "observed_sharpe": round(sharpes[best], 4)}


# ── Probability of Backtest Overfitting (CSCV) ───────────────────────────────
def probability_of_backtest_overfitting(matrix: list[list[float]], n_splits: int = 8) -> float:
    """PBO via Combinatorial Symmetric Cross-Validation (Bailey et al. 2017).

    matrix: T periods x N strategies of per-period returns. Partition the T rows into
    n_splits (even) contiguous blocks; for every way to choose half as IS and the rest
    OOS, pick the IS-best strategy and check whether it lands below the OOS median.
    PBO = fraction of splits where it does (i.e., in-sample winner overfits)."""
    T = len(matrix)
    if T < n_splits or not matrix:
        return float("nan")
    N = len(matrix[0])
    if N < 2:
        return float("nan")
    if n_splits % 2:
        n_splits -= 1
    block = T // n_splits
    blocks = [list(range(i * block, (i + 1) * block)) for i in range(n_splits)]

    def perf(rows: list[int]) -> list[float]:
        return [sum(matrix[r][s] for r in rows) / len(rows) for s in range(N)]

    overfit = 0
    total = 0
    for is_blocks in combinations(range(n_splits), n_splits // 2):
        is_rows = [r for b in is_blocks for r in blocks[b]]
        oos_rows = [r for b in range(n_splits) if b not in is_blocks for r in blocks[b]]
        is_perf = perf(is_rows)
        oos_perf = perf(oos_rows)
        best = max(range(N), key=lambda s: is_perf[s])
        # OOS rank of the IS-best (relative rank in (0,1)); below median => overfit
        rank = sum(1 for s in range(N) if oos_perf[s] <= oos_perf[best]) / N
        w = min(max(rank, 1e-6), 1 - 1e-6)
        if math.log(w / (1 - w)) < 0:
            overfit += 1
        total += 1
    return overfit / total if total else float("nan")
