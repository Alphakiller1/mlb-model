"""Tests for sharp observation and model lean settlement."""
from __future__ import annotations

from unittest.mock import patch

from mlbmodel.leans.grade import grade_lean, settle_leans
from mlbmodel.market.settle import grade, run, run_all
from mlbmodel.storage.supabase import ReadResult


class MockWriter:
    def __init__(self):
        self.url = "https://example.supabase.co"
        self.key = "secret"
        self.updates: list[tuple[str, str, dict]] = []

    def update(self, table: str, query: str, payload: dict) -> None:
        self.updates.append((table, query, payload))


class MockReader:
    def __init__(self, routes: dict[str, ReadResult]):
        self.routes = routes

    def get(self, path: str) -> ReadResult:
        for prefix, result in self.routes.items():
            if path.startswith(prefix):
                return result
        return ReadResult([], f"no route for {path}")


def test_sharp_grade_moneyline():
    won, push = grade(
        {"market_type": "ml", "selection": "NYY"},
        {"home_team": "BOS"},
        {"winner_team": "NYY", "home_runs": 3, "away_runs": 5, "total_runs": 8, "margin_home": -2},
    )
    assert won is True
    assert push is False


def test_sharp_grade_total_push():
    won, push = grade(
        {"market_type": "total", "selection": "over", "line": 9.0},
        {"home_team": "BOS"},
        {"total_runs": 9, "home_runs": 5, "away_runs": 4, "margin_home": 1, "winner_team": "BOS"},
    )
    assert won is None
    assert push is True


def test_sharp_run_settles_matching_observation():
    reader = MockReader({
        "games?": ReadResult([{"game_pk": 1, "home_team": "BOS", "away_team": "NYY"}]),
        "game_outcomes?": ReadResult([{
            "game_pk": 1,
            "home_runs": 4,
            "away_runs": 3,
            "total_runs": 7,
            "margin_home": 1,
            "winner_team": "BOS",
        }]),
        "sharp_observations?": ReadResult([{
            "obs_id": 9,
            "game_pk": 1,
            "market_type": "ml",
            "selection": "BOS",
            "line": None,
            "side_role": None,
        }]),
    })
    writer = MockWriter()
    with patch("mlbmodel.market.settle.SupabaseReader", return_value=reader), patch(
        "mlbmodel.market.settle.SupabaseWriter", return_value=writer
    ):
        assert run() == 1
    assert writer.updates[0][0] == "sharp_observations"
    assert writer.updates[0][2]["won"] is True


def test_settle_leans_grades_pending_rows():
    reader = MockReader({
        "model_leans?": ReadResult([{
            "lean_id": 1,
            "slate_date": "2026-07-06",
            "game_pk": 1,
            "source": "sharp",
            "market": "total",
            "selection": "over",
            "line": 8.5,
            "pitcher_name": None,
        }]),
        "game_outcomes?": ReadResult([{
            "game_pk": 1,
            "home_runs": 6,
            "away_runs": 5,
            "total_runs": 11,
            "margin_home": 1,
            "winner_team": "BOS",
        }]),
        "games?": ReadResult([{
            "game_pk": 1,
            "home_team": "BOS",
            "away_team": "NYY",
            "game_date": "2026-07-06",
        }]),
    })
    writer = MockWriter()
    with patch("mlbmodel.leans.grade.fetch_pitcher_stats_for_date", return_value={}):
        settled = settle_leans(reader=reader, writer=writer)
    assert settled == 1
    assert writer.updates[0][0] == "model_leans"
    assert writer.updates[0][2]["won"] is True


def test_settle_leans_prop_uses_box_scores():
    reader = MockReader({
        "model_leans?": ReadResult([{
            "lean_id": 2,
            "slate_date": "2026-07-06",
            "game_pk": 1,
            "source": "prizepicks",
            "market": "k",
            "selection": "over",
            "line": 5.5,
            "pitcher_name": "Gerrit Cole",
        }]),
        "game_outcomes?": ReadResult([]),
        "games?": ReadResult([{"game_pk": 1, "home_team": "BOS", "away_team": "NYY", "game_date": "2026-07-06"}]),
    })
    writer = MockWriter()
    box = {"gerrit cole": {"strikeouts": 8, "walks": 1, "earned_runs": 2, "outs": 18}}
    with patch("mlbmodel.leans.grade.fetch_pitcher_stats_for_date", return_value=box):
        settled = settle_leans(reader=reader, writer=writer)
    assert settled == 1
    assert writer.updates[0][2]["won"] is True


def test_grade_lean_skips_without_outcome():
    won, push = grade_lean({"market": "ml", "selection": "NYY"}, outcome=None)
    assert won is None
    assert push is False


def test_run_all_invokes_both_paths():
    with patch("mlbmodel.market.settle.run", return_value=2) as sharp_run, patch(
        "mlbmodel.leans.grade.settle_leans", return_value=5
    ) as lean_settle:
        sharp, leans = run_all()
    assert sharp == 2
    assert leans == 5
    sharp_run.assert_called_once()
    lean_settle.assert_called_once()
