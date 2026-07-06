"""Tests for Markets decision fusion."""
from __future__ import annotations

from mlbmodel.report.decision import (
    collect_market_plays,
    collect_model_market_plays,
    decide,
)


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
            "market": "ml",
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


def test_decide_matches_ml_alias():
    signal = {
        "divergence": 0.01,
        "sharp_novig_prob": 0.54,
        "soft_novig_prob": 0.50,
        "market_type": "moneyline",
        "selection": "DET",
        "n_sharp_books": 2,
        "n_soft_books": 4,
        "steam_flag": False,
    }
    model_rows = [{"market": "ml", "side": "DET", "model": 56, "edge": 2.0, "ev": 0.02, "mkt": -105}]
    play = decide(signal, model_rows)
    assert play["model_p"] == 56


def test_collect_model_market_plays_without_live_odds():
    slate = [{"pk": 1, "away": "HOU", "home": "DET"}]
    model_by_pk = {
        1: [
            {"market": "ml", "side": "DET", "model": 53.5, "fair": -115, "mkt": None, "state": "NO EDGE"},
            {"market": "ml", "side": "HOU", "model": 46.5, "fair": 115, "mkt": None, "state": "NO EDGE"},
            {"market": "total", "side": "over", "model": 50.4, "fair": -102, "line": 8.5, "mkt": None, "state": "NO EDGE"},
        ]
    }
    plays = collect_model_market_plays(slate, model_by_pk)
    assert plays
    assert any(play["verdict"] == "MODEL" for play in plays)
    assert plays[0]["game"] == "HOU@DET"


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


def test_collect_market_plays_falls_back_to_model_fairs():
    slate = [{"pk": 1, "away": "HOU", "home": "DET"}]
    model_by_pk = {
        1: [
            {"market": "ml", "side": "DET", "model": 55.0, "fair": -122, "mkt": None, "state": "NO EDGE"},
        ]
    }
    plays = collect_market_plays(slate, {}, model_by_pk)
    assert len(plays) == 1
    assert plays[0]["verdict"] == "MODEL"
