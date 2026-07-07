from unittest.mock import patch

from mlbmodel.baseball.repository import DataRepository


def test_trend_features_are_cached_per_game(tmp_path):
    repo = DataRepository(tmp_path)
    calls = {"n": 0}

    def fake_trends(_repo, away, home):
        calls["n"] += 1
        return {"away_offense_trend_signal": 1.0, "game": f"{away}@{home}"}

    with patch(
        "mlbmodel.trends.report.trend_features_for_game",
        side_effect=fake_trends,
    ):
        first = repo.trend_features("NYY", "BOS")
        second = repo.trend_features("NYY", "BOS")
        third = repo.trend_features("BOS", "NYY")

    assert first == second
    assert third != first
    assert calls["n"] == 2


def test_enrich_trends_attaches_without_reload():
    from mlbmodel.baseball.model import GameData

    repo = DataRepository.__new__(DataRepository)
    repo._trend_cache = {("NYY", "BOS"): {"away_offense_trend_signal": 0.5}}
    gd = GameData(
        game_pk=1,
        game_date="2026-06-27",
        start_time="",
        away="NYY",
        home="BOS",
        away_sp="A",
        home_sp="B",
        away_hand="R",
        home_hand="L",
        away_osi=50,
        home_osi=50,
        away_fip=4.2,
        home_fip=4.2,
        away_hr9=1.0,
        home_hr9=1.0,
        away_k=22,
        home_k=22,
        park_factor=1.0,
    )
    repo.enrich_trends(gd, "NYY", "BOS")
    assert gd.trend_features["away_offense_trend_signal"] == 0.5
