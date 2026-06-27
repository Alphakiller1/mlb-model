from mlbmodel.report.app import _portfolio, _props
from mlbmodel.storage.supabase import ReadResult


class StaticReader:
    def __init__(self, rows=None, error=None):
        self.result = ReadResult(rows or [], error)

    def get(self, _path):
        return self.result


def test_props_board_is_explicitly_research_only():
    rendered = _props([{
        "away": "NYY",
        "home": "BOS",
        "asp": "Away Starter",
        "hsp": "Home Starter",
        "ak": 25.0,
        "hk": 20.0,
        "afip": 3.25,
        "hfip": 4.10,
        "ahr9": 0.8,
        "hhr9": 1.2,
    }])

    assert "Research only" in rendered
    assert "not prop projections" in rendered
    assert "No play can be issued" in rendered


def test_portfolio_view_flags_concentration_and_respects_gate():
    positions = [
        {
            "game_pk": 1,
            "market_type": "h2h",
            "selection": "NYY",
            "line": None,
            "entry_odds": 110,
            "model_probability": 0.52,
            "market_probability": 0.48,
            "stake_units": 2.5,
            "entry_time": "2026-06-27T12:00:00Z",
            "strategy_version": "test",
        }
    ]
    slate = [{"pk": 1, "away": "NYY", "home": "BOS"}]
    rendered = _portfolio(StaticReader(positions), {"verdict": "HOLD"}, slate)

    assert "Concentration warning" in rendered
    assert "Sizing is disabled until" in rendered
    assert "2.50u" in rendered
