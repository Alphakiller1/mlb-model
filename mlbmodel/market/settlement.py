"""Convert three-outcome contracts into comparable two-way fair prices."""
from __future__ import annotations

import math


def conditional_win_probability(win: float, push: float = 0.0) -> float:
    """P(win | no push); a certain refund has no directional edge (neutral 0.5)."""
    if not all(math.isfinite(value) for value in (win, push)):
        raise ValueError("Win and push probabilities must be finite")
    if win < 0 or push < 0 or win + push > 1 + 1e-9:
        raise ValueError("Win and push probabilities must form a valid outcome distribution")
    if push >= 1.0:
        return 0.5
    return min(1.0, win / (1.0 - push))
