from mlbmodel.leans.calibration import calibration_buckets, summarize_record
from mlbmodel.leans.grade import grade_lean
from mlbmodel.leans.record import (
    collect_leans,
    edge_points,
    record_leans,
    _row,
)


def test_collect_leans_dedupes_market_and_prop():
    plays = [{
        "verdict": "BET",
        "pk": 1,
        "mkt_type": "total",
        "sel": "over",
        "market_line": 8.5,
        "entry_odds": -110,
        "price": -110,
        "model_p": 55.0,
        "medge": 3.0,
    }]
    pickem = [{
        "lean": "OVER",
        "book": "prizepicks",
        "prop": "Fantasy",
        "line": 35.5,
        "projection": 38.0,
        "p_over": 0.62,
        "edge_pts": 12.0,
        "game_pk": 1,
        "pitcher": "Gerrit Cole",
    }]
    props = [{
        "state": "BET",
        "prop": "K",
        "side": "over",
        "line": 5.5,
        "edge": 0.04,
        "model_probability": 0.58,
        "model_mean": 6.0,
        "game_pk": 1,
        "pitcher": "Gerrit Cole",
        "best_odds": -115,
    }]
    rows = collect_leans(
        slate_date="2026-07-06",
        market_plays=plays,
        pickem_rows=pickem,
        prop_reports=props,
    )
    assert len(rows) == 3
    assert {r["source"] for r in rows} == {"sharp", "prizepicks", "prop"}
    sharp = next(r for r in rows if r["source"] == "sharp")
    assert sharp["line"] == 8.5
    assert sharp["entry_odds"] == -110
    fantasy = next(r for r in rows if r["source"] == "prizepicks")
    assert fantasy["pitcher_name"] == "Gerrit Cole"
    assert fantasy["market"] == "fantasy_score"
    assert fantasy["lean"] == "OVER"
    keys = set(rows[0].keys())
    assert all(set(r.keys()) == keys for r in rows), "lean batch keys must match for PostgREST upsert"


def test_collect_leans_matchup_and_f5_markets():
    matchup_markets = {
        1: [
            {
                "market": "total",
                "side": "over",
                "line": 8.5,
                "model": 56.0,
                "edge": 2.5,
                "state": "MONITOR",
                "mkt": -105,
            },
            {
                "market": "f5_total",
                "side": "under",
                "line": 4.5,
                "model": 54.0,
                "edge": 1.2,
                "state": "MONITOR",
                "mkt": -110,
            },
            {
                "market": "f5_ml",
                "side": "NYY",
                "line": None,
                "model": 58.0,
                "edge": 3.0,
                "state": "BET",
                "mkt": 120,
            },
        ],
    }
    rows = collect_leans(
        slate_date="2026-07-06",
        market_plays=[],
        pickem_rows=[],
        prop_reports=[],
        matchup_markets_by_pk=matchup_markets,
    )
    assert len(rows) == 3
    assert {r["source"] for r in rows} == {"matchup", "f5"}
    f5_total = next(r for r in rows if r["market"] == "f5_total")
    assert f5_total["source"] == "f5"
    assert f5_total["selection"] == "under"
    assert f5_total["entry_odds"] == -110


def test_collect_leans_pitcher_projections():
    pitchers = [{
        "pitcher": "Gerrit Cole",
        "game_pk": 1,
        "projection_trust": "trusted",
        "projections": {
            "K": {"mean": 6.2, "sd": 1.5},
            "ER": {"mean": 2.1, "sd": 1.0},
            "PP_Fantasy": {"mean": 36.5, "sd": 8.0},
        },
    }]
    rows = collect_leans(
        slate_date="2026-07-06",
        market_plays=[],
        pickem_rows=[],
        prop_reports=[],
        pitchers=pitchers,
    )
    assert len(rows) == 3
    assert all(r["source"] == "projection" for r in rows)
    assert all(r["lean"] == "PROJECTION" for r in rows)
    assert all(r["selection"].startswith("model:") for r in rows)
    fantasy = next(r for r in rows if r["market"] == "fantasy_score")
    assert fantasy["model_value"] == 36.5


def test_collect_leans_records_thin_projections():
    rows = collect_leans(
        slate_date="2026-07-06",
        market_plays=[],
        pickem_rows=[],
        prop_reports=[],
        pitchers=[{
            "pitcher": "Rookie Pitcher",
            "game_pk": 2,
            "projection_trust": "thin",
            "projections": {"K": {"mean": 4.0, "sd": 1.0}},
        }],
    )
    assert len(rows) == 1
    assert rows[0]["lean"] == "PROJECTION_THIN"


def test_collect_leans_records_watch_props():
    rows = collect_leans(
        slate_date="2026-07-06",
        market_plays=[],
        pickem_rows=[],
        prop_reports=[{
            "prop": "K",
            "side": "over",
            "line": 5.5,
            "edge": 0.005,
            "state": "NO EDGE",
            "model_mean": 5.8,
            "game_pk": 1,
            "pitcher": "Gerrit Cole",
        }],
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "prop"
    assert rows[0]["lean"] == "WATCH"


def test_collect_leans_skips_matchup_without_edge():
    rows = collect_leans(
        slate_date="2026-07-06",
        market_plays=[],
        pickem_rows=[],
        prop_reports=[],
        matchup_markets_by_pk={
            1: [{"market": "total", "side": "over", "line": 8.5, "model": 50.0, "edge": None, "state": "NO EDGE"}],
        },
    )
    assert rows == []


def test_edge_points_normalizes_fraction_and_points():
    assert edge_points(0.04) == 4.0
    assert edge_points(4.0) == 4.0


def test_grade_lean_runline_uses_stored_line():
    won, push = grade_lean(
        {"market": "runline", "selection": "NYY", "line": -1.5},
        outcome={"margin_home": -2, "home_team": "BOS", "away_team": "NYY"},
    )
    assert won is True
    assert push is False


def test_record_leans_skips_without_credentials(monkeypatch):
    monkeypatch.setattr("mlbmodel.leans.record.SupabaseWriter", lambda: type("W", (), {"url": "", "key": ""})())
    assert record_leans([_row(
        slate_date="2026-07-06",
        game_pk=1,
        source="sharp",
        market="ml",
        selection="NYY",
        line=None,
        model_value=52.0,
        model_prob=52.0,
        edge=2.0,
        lean="BET",
    )]) == 0


def test_grade_lean_total_over_win():
    won, push = grade_lean(
        {"market": "total", "selection": "over", "line": 8.5},
        outcome={"total_runs": 10, "home_runs": 5, "away_runs": 5},
    )
    assert won is True
    assert push is False


def test_grade_lean_total_push():
    won, push = grade_lean(
        {"market": "total", "selection": "over", "line": 10.0},
        outcome={"total_runs": 10},
    )
    assert won is None
    assert push is True


def test_grade_lean_prop_strikeouts():
    won, push = grade_lean(
        {"market": "k", "selection": "over", "line": 5.5, "source": "prizepicks"},
        pitcher_stats={"strikeouts": 7},
    )
    assert won is True


def test_calibration_buckets():
    rows = [
        {"settled": True, "model_prob": 0.55, "won": True, "push": False},
        {"settled": True, "model_prob": 0.56, "won": False, "push": False},
        {"settled": True, "model_prob": 0.80, "won": True, "push": False},
    ]
    buckets = calibration_buckets(rows, buckets=2)
    assert buckets
    summary = summarize_record(rows)
    assert summary["wins"] == 2
    assert summary["losses"] == 1
