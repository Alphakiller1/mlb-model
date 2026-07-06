"""Tests for Markets decision fusion."""
from __future__ import annotations

from mlbmodel.report.decision import collect_market_plays, decide


def test_decide_bet_when_sharp_and_model_align():
    signal = {
        "divergence": 0.02,
        "sharp_novig_prob": 0.55,
        "soft_novig_prob": 0.50,
        "market_type": "moneyline",
        "selection": "DET",
        "n_sharp_books": 3,
        "n_soft_books": 5,
        "steam_flag": False,
    }
    model_rows = [
        {
            "market": "moneyline",
            "side": "DET",
            "model": 58,
            "edge": 3.0,
            "ev": 0.04,
            "mkt": -110,
            "fair": -125,
            "book": "draftkings",
            "line": None,
        }
    ]
    play = decide(signal, model_rows)
    assert play["verdict"] in ("STRONG", "BET")
    assert play["stake"] > 0


def test_collect_market_plays_attaches_game_label():
    slate = [{"pk": 1, "away": "HOU", "home": "DET"}]
    sharp_by_pk = {
        1: [{
            "divergence": 0.01,
            "sharp_novig_prob": 0.52,
            "soft_novig_prob": 0.50,
            "market_type": "total",
            "selection": "Over",
        }]
    }
    plays = collect_market_plays(slate, sharp_by_pk, {})
    assert len(plays) == 1
    assert plays[0]["game"] == "HOU@DET"
