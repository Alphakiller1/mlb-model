"""Tests for edge intelligence aggregations."""
from mlbmodel.analytics.edge_intel import (
    clv_from_snapshots,
    collect_slate_opportunities,
    market_type_record,
    team_prediction_record,
)


def test_collect_slate_opportunities_ranks_game_and_f5():
    ops = collect_slate_opportunities(
        pkmap={1: "NYY@BOS"},
        market_plays=[{
            "verdict": "BET",
            "pk": 1,
            "game": "NYY@BOS",
            "mkt_type": "total",
            "sel": "over",
            "market_line": 8.5,
            "price": -110,
            "model_p": 56.0,
            "medge": 4.0,
            "score": 4000,
        }],
        model_by_pk={
            1: [{
                "market": "f5_total",
                "side": "under",
                "line": 4.5,
                "model": 54.0,
                "edge": 2.0,
                "state": "MONITOR",
                "mkt": -105,
            }],
        },
        prop_reports=[],
        pickem_rows=[],
    )
    assert len(ops) == 2
    assert ops[0]["category"] == "sharp"
    f5 = next(row for row in ops if row["category"] == "f5")
    assert f5["market"] == "f5_total"
    assert f5["price"] == "-105"


def test_pickem_opportunity_uses_lean_probability_not_projection_mean():
    ops = collect_slate_opportunities(
        pkmap={},
        market_plays=[],
        model_by_pk={},
        prop_reports=[],
        pickem_rows=[{
            "pitcher": "Starter One",
            "book": "PrizePicks",
            "prop": "Walks",
            "line": 4.5,
            "lean": "UNDER",
            "p_over": 0.14,
            "edge_pts": 36.0,
            "projection": 3.2,
        }],
    )

    assert len(ops) == 1
    assert ops[0]["model_pct"] == 86.0


def test_clv_from_snapshots():
    summary = clv_from_snapshots([
        {"market_type": "ml", "entry_prob": 0.45, "implied_probability": 0.50, "won": True},
        {"market_type": "ml", "entry_prob": 0.52, "implied_probability": 0.49, "won": False},
    ])
    assert summary is not None
    assert summary["n"] == 2
    assert summary["clv_pts"] == 1.0
    assert "ml" in summary["by_market"]


def test_team_prediction_record_ml_only():
    teams = team_prediction_record([
        {"settled": True, "market": "ml", "selection": "NYY", "won": True, "push": False},
        {"settled": True, "market": "ml", "selection": "NYY", "won": True, "push": False},
        {"settled": True, "market": "ml", "selection": "NYY", "won": False, "push": False},
        {"settled": True, "market": "total", "selection": "over", "won": True, "push": False},
    ], min_samples=3)
    assert len(teams) == 1
    assert teams[0]["team"] == "NYY"
    assert abs(teams[0]["hit_rate"] - 200 / 3) < 0.01


def test_market_type_record_groups_source_and_market():
    rows = market_type_record([
        {"settled": True, "source": "prop", "market": "k", "won": True, "push": False, "edge": 3.0},
        {"settled": True, "source": "prop", "market": "k", "won": False, "push": False, "edge": 2.0},
        {"settled": True, "source": "f5", "market": "f5_total", "won": True, "push": False, "edge": 1.5},
        {"settled": True, "source": "f5", "market": "f5_total", "won": True, "push": False, "edge": 2.5},
    ], min_samples=2)
    assert len(rows) == 2
    prop = next(r for r in rows if r["market"] == "k")
    assert prop["hit_rate"] == 50.0
