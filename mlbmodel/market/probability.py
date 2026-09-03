"""Shared probability helpers for props and pick'em lines."""
from __future__ import annotations

import math

from mlbmodel.baseball.model import normal_cdf


def p_over_line_erf(line: float, mean: float, sd: float) -> float:
    """P(stat > line) via normal CDF — matches half-point DFS lines."""
    if sd is None or sd <= 0:
        return 1.0 if mean > line else (0.0 if mean < line else 0.5)
    return 1.0 - 0.5 * (1.0 + math.erf((line - mean) / (sd * math.sqrt(2))))


def p_over_exact(line: float, projection: dict | None) -> tuple[float, float]:
    """``(P(stat > line), P(stat == line))`` from the simulation's own distribution.

    Pitcher counting stats are right-skewed — earned runs carry a skew of ~1.07, walks
    ~0.77, strikeouts and hits ~0.42 — so a symmetric normal fitted to ``(mean, sd)``
    systematically overstates P(Over): measured against the engine's own 30,000 draws it is
    +7.3pts too high on ER at the central line, +5.2 on BB, +2.9 on K, +2.7 on H, and
    ±0.1 on Outs (whose skew is ~0). That bias is larger than any real edge, and it matches
    the settled ledger exactly — k-over graded 37.6% against 54.1% predicted, er-over 39.6%
    against 55.6%, while Outs, the one symmetric market, came in unbiased.

    The engine already draws the exact distribution and then threw it away, keeping only
    four summary numbers. ``pmf`` (integer markets) and ``q`` (a percentile grid, for
    continuous ones like fantasy score) carry it through instead, so the board prices what
    it actually simulated. Falls back to the normal only when neither is present.
    """
    projection = projection or {}
    pmf = projection.get("pmf")
    if pmf:
        over = 0.0
        push = 0.0
        for raw, probability in pmf.items():
            value, probability = float(raw), float(probability)
            if value > line:
                over += probability
            elif value == line:
                push += probability
        total = over + push + sum(
            float(p) for raw, p in pmf.items() if float(raw) < line
        )
        if total > 0:
            return over / total, push / total
        return over, push
    grid = projection.get("q")
    if grid:
        values = [float(value) for value in grid]
        above = sum(1 for value in values if value > line)
        return above / len(values), 0.0
    mean = float(projection.get("mean") or 0.0)
    sd = float(projection.get("sd") or 0.0)
    return p_over_line_erf(line, mean, max(0.2, sd)), 0.0


def p_over_line_normal(line: float, mean: float, sd: float) -> float:
    """P(stat > line) using z = (mean - line) / sd."""
    if sd is None or sd <= 0:
        sd = max(abs(mean) * 0.2, 0.5)
    return normal_cdf((mean - line) / sd)
