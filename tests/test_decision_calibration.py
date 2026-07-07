"""Tests for decision threshold calibration."""
from __future__ import annotations

from mlbmodel.leans.decision_calibration import (
    DecisionThresholds,
    thresholds_from_leans,
)
from mlbmodel.report.decision import decide


def _sharp_row(*, edge: float, won: bool) -> dict:
    return {
        "settled": True,
        "push": False,
        "source": "sharp",
        "edge": edge,
        "won": won,
    }


def test_thresholds_default_with_small_sample():
    thresholds = thresholds_from_leans([_sharp_row(edge=3.0, won=True)] * 5)
    assert thresholds.calibrated is False
    assert thresholds.strong_edge == 2.0


def test_thresholds_calibrate_from_winners():
    rows = [_sharp_row(edge=edge, won=edge >= 2.0) for edge in [1.0, 1.5, 2.0, 2.5, 3.0] * 6]
    thresholds = thresholds_from_leans(rows, min_sample=20)
    assert thresholds.calibrated is True
    assert 1.0 <= thresholds.strong_edge <= 3.5
    assert thresholds.sample_n >= 20


def test_decide_uses_calibrated_strong_floor():
    strict = DecisionThresholds(strong_edge=3.0, strong_div=1.5, bet_edge=1.0, calibrated=True)
    signal = {
        "divergence": 0.02,
        "sharp_novig_prob": 0.55,
        "soft_novig_prob": 0.50,
        "market_type": "moneyline",
        "selection": "DET",
    }
    model_rows = [{
        "market": "moneyline",
        "side": "DET",
        "model": 58,
        "edge": 2.2,
        "ev": 0.04,
        "mkt": -110,
    }]
    assert decide(signal, model_rows, strict)["verdict"] == "BET"
    assert decide(signal, model_rows, DecisionThresholds(strong_edge=2.0))["verdict"] in ("STRONG", "BET")
