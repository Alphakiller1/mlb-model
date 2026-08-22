"""Tests for Results and Trends view builders."""
from __future__ import annotations

from mlbmodel.report.views import results, trends
from mlbmodel.storage.supabase import ReadResult


class StaticReader:
    def __init__(self, rows=None, error=None, extra=None):
        self.result = ReadResult(rows or [], error)
        self.extra = extra or {}

    def get(self, path):
        if self.result.error:
            return self.result
        for prefix, rows in self.extra.items():
            if path.startswith(prefix):
                return ReadResult(rows)
        return self.result


def test_results_view_renders_calibration_board():
    rows = [
        {
            "slate_date": "2026-07-06",
            "source": "sharp",
            "market": "total",
            "selection": "over",
            "lean": "BET",
            "settled": True,
            "won": True,
            "push": False,
            "model_prob": 0.58,
            "recorded_at": "2026-07-06T12:00:00Z",
        },
        {
            "slate_date": "2026-07-05",
            "source": "prop",
            "market": "k",
            "selection": "over",
            "lean": "BET",
            "settled": True,
            "won": False,
            "push": False,
            "model_prob": 0.55,
            "line": 5.5,
            "recorded_at": "2026-07-05T12:00:00Z",
        },
    ]
    html = results(StaticReader(rows, extra={
        "prediction_market_snapshots": [{
            "market_type": "ml",
            "entry_prob": 0.45,
            "implied_probability": 0.50,
            "won": True,
        }],
    }))
    assert "desk-pagehead" in html and "ca-board" in html
    assert "Calibration" in html
    assert "By source" in html
    assert "Projection error" in html
    assert "1-1-0" in html


def test_results_view_handles_warehouse_error():
    html = results(StaticReader(error="connection refused"))
    assert "Lean warehouse unavailable" in html


def test_results_view_falls_back_to_snapshot(tmp_path):
    from mlbmodel.leans.record import write_lean_snapshot

    snapshot = tmp_path / "model_leans_latest.json"
    write_lean_snapshot([{
        "slate_date": "2026-08-01",
        "game_pk": 1,
        "source": "matchup",
        "market": "ml",
        "selection": "TOR",
        "line": None,
        "model_prob": 0.55,
        "edge": None,
        "lean": "PROJECTION",
        "settled": True,
        "won": True,
        "push": False,
        "recorded_at": "2026-08-01T12:00:00Z",
    }], snapshot)
    html = results(
        StaticReader(error="connection refused"),
        snapshot_path=snapshot,
    )
    assert "Lean warehouse unavailable" not in html or "showing the local lean snapshot" in html
    assert "No leans recorded yet" not in html
    assert ">W<" in html
    assert "1-0-0" in html
    assert "showing the local lean snapshot" in html


def test_results_recent_prefers_settled_over_projections():
    projection_flood = [
        {
            "slate_date": "2026-08-22",
            "game_pk": 9,
            "source": "projection",
            "market": "k",
            "selection": f"model:pitcher_{i}",
            "lean": "PROJECTION",
            "settled": False,
            "recorded_at": f"2026-08-22T20:00:{i:02d}Z",
        }
        for i in range(50)
    ]
    settled = {
        "slate_date": "2026-08-01",
        "game_pk": 1,
        "source": "matchup",
        "market": "ml",
        "selection": "TOR",
        "lean": "PROJECTION",
        "settled": True,
        "won": True,
        "push": False,
        "recorded_at": "2026-08-01T12:00:00Z",
    }
    html = results(StaticReader([settled, *projection_flood]))
    table = html.split("id=results-recent-table")[1].split("</table>")[0]
    assert table.find(">W<") < table.find("projection")
    assert "No leans recorded yet" not in html
    assert "1-0-0" in html


def test_results_empty_warehouse_with_snapshot_and_finals_shows_wl(tmp_path):
    from mlbmodel.baseball.repository import canonical_game_pk
    from mlbmodel.leans.record import write_lean_snapshot

    pk = canonical_game_pk("2026-08-01", "STL", "TOR")
    snapshot = tmp_path / "model_leans_latest.json"
    write_lean_snapshot([{
        "slate_date": "2026-08-01",
        "game_pk": pk,
        "source": "matchup",
        "market": "ml",
        "selection": "TOR",
        "line": None,
        "model_prob": 0.53,
        "edge": None,
        "lean": "PROJECTION",
        "settled": False,
        "recorded_at": "2026-08-01T12:00:00Z",
    }], snapshot)
    finals = tmp_path / "game_results.csv"
    finals.write_text(
        "game_date,home_away,team,opp,team_runs,opp_runs,result\n"
        "2026-08-01,home,TOR,STL,5,1,W\n"
        "2026-08-01,away,STL,TOR,1,5,L\n",
        encoding="utf-8",
    )
    html = results(
        StaticReader([]),
        snapshot_path=snapshot,
        game_results_path=finals,
    )
    assert "No leans recorded yet" not in html
    assert ">W<" in html
    assert "1-0-0" in html
    assert "Tracked record" in html


def test_trends_view_empty_slate():
    html = trends([])
    assert "No slate loaded" in html


def test_trends_view_renders_board():
    from types import SimpleNamespace

    trend = SimpleNamespace(
        team="NYY",
        category="starter_quality",
        trend_description="Away SP elite vs lineup",
        effect_size=1.2,
        trend_score=1.5,
        sample_size=40,
        confidence="high",
        significance="strong",
        direction="run_suppression",
        betting_implications=["NYY team total UNDER"],
        mechanistic_explanation="pitching edge",
    )
    report = SimpleNamespace(
        game="NYY@BOS",
        away="NYY",
        home="BOS",
        away_edge_score=62.0,
        home_edge_score=48.0,
        edge_lean="NYY",
        trends=[trend],
    )
    html_out = trends([report])
    assert "trendGameSelect" in html_out
    assert "Game" in html_out
    assert 'data-lane="game"' in html_out
    assert "NYY@BOS" in html_out
