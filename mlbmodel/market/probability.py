"""Shared probability helpers for props and pick'em lines."""
from __future__ import annotations

import math

from mlbmodel.baseball.model import normal_cdf


def p_over_line_erf(line: float, mean: float, sd: float) -> float:
    """P(stat > line) via normal CDF — matches half-point DFS lines."""
    if sd is None or sd <= 0:
        return 1.0 if mean > line else (0.0 if mean < line else 0.5)
    return 1.0 - 0.5 * (1.0 + math.erf((line - mean) / (sd * math.sqrt(2))))


def p_over_line_normal(line: float, mean: float, sd: float) -> float:
    """P(stat > line) using z = (mean - line) / sd."""
    if sd is None or sd <= 0:
        sd = max(abs(mean) * 0.2, 0.5)
    return normal_cdf((mean - line) / sd)
