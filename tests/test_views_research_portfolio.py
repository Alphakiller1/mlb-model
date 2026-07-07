"""Tests for Research view builder."""
from __future__ import annotations

from mlbmodel.report.views import research
from mlbmodel.storage.supabase import ReadResult


class StaticReader:
    def __init__(self, routes: dict[str, ReadResult] | None = None, default=None):
        self.routes = routes or {}
        self.default = default or ReadResult([], None)

    def get(self, path: str) -> ReadResult:
        for prefix, result in self.routes.items():
            if path.startswith(prefix):
                return result
        return self.default


def test_research_view_renders_gate_and_f5():
    reader = StaticReader({
        "v_pm_calibration?": ReadResult([
            {
                "price_bucket": "40-50",
                "n": 12,
                "avg_price": 0.45,
                "actual_win_rate": 0.42,
                "gap": -0.03,
            }
        ]),
    })
    f5_board = [
        ("NYY@BOS", {
            "market": "f5_total",
            "side": "Over",
            "model": 54,
            "mkt": -110,
            "edge": 2.5,
            "tone": "pos",
            "state": "MONITOR",
        }),
    ]
    html = research(reader, {"verdict": "HOLD", "reasons": ["thin sample"]}, f5_board)
    assert "Research" in html
    assert "Promotion gate" in html
    assert "ca-section-head" in html
    assert "ca-neon-icon" in html
    assert "First 5 (F5) edges" in html
    assert "NYY@BOS" in html
