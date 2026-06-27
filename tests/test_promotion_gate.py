"""Enforces the promotion gate (STD-7/10/12): strong+persistent → PROMOTE; noise → HOLD."""
import random

from mlbmodel.quant.promotion_gate import promotion_verdict

random.seed(11)


def _row(t_iso, delta, open_prob, won, vol=150000):
    return {"snapshot_time": t_iso, "delta": delta, "open_prob": open_prob,
            "won": won, "implied_probability": open_prob + 0.05, "volume": vol}


def test_noise_does_not_promote():
    rows = [_row(f"2026-06-{(i % 28) + 1:02d}T00:00:00Z", random.choice([0.05, -0.05]),
                 0.5, random.random() < 0.5) for i in range(400)]
    v = promotion_verdict(rows, min_oos_n=20)
    assert v["verdict"] == "HOLD/ABSTAIN"
    assert v["reasons"] != ["all gates passed"]


def test_strong_persistent_edge_can_promote():
    # steamed-up sides (delta>0) win ~72% every period, entered cheap at 0.45 -> real OOS edge
    rows = []
    for i in range(500):
        day = (i % 28) + 1
        up = i % 2 == 0
        delta = 0.05 if up else -0.05
        won = (random.random() < 0.72) if up else (random.random() < 0.40)
        rows.append(_row(f"2026-06-{day:02d}T{i % 24:02d}:00:00Z", delta, 0.45, won))
    v = promotion_verdict(rows, min_oos_n=20, dsr_threshold=0.95)
    # a genuinely persistent, well-powered edge should clear all gates
    assert v["verdict"] == "PROMOTE", v
