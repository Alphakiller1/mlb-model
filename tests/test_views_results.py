"""Tests for Results and Trends view builders."""
from __future__ import annotations

from mlbmodel.report.views import results, trends
from mlbmodel.storage.supabase import ReadResult


class StaticReader:
    def __init__(self, rows=None, error=None):
        self.result = ReadResult(rows or [], error)

    def get(self, _path):
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
            "recorded_at": "2026-07-05T12:00:00Z",
        },
    ]
    html = results(StaticReader(rows))
    assert "Results" in html
    assert "ca-section-head" in html
    assert "Calibration" in html
    assert "1-1-0" in html


def test_results_view_handles_warehouse_error():
    html = results(StaticReader(error="connection refused"))
    assert "Lean warehouse unavailable" in html


def test_trends_view_empty_slate():
    html = trends([])
    assert "No games to analyze" in html


def test_trends_view_renders_board():
    from types import SimpleNamespace

    trend = SimpleNamespace(
        team="NYY",
        category="starter_quality",
        trend_description="Away SP elite vs lineup",
        effect_size=1.2,
        trend_score=1.5,
        sample_size=40,
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
    html = trends([report])
    assert "Dominant trend board" in html
    assert "ca-section-head" in html
    assert "NYY@BOS" in html
