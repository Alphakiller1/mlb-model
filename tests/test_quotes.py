import math

import pytest

from mlbmodel import settings
from mlbmodel.market.quotes import (
    build_board,
    filter_events_for_slate,
    odds_request_params,
)


def _event():
    return {
        "away_team": "New York Yankees",
        "home_team": "Boston Red Sox",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "New York Yankees", "price": -120},
                        {"name": "Boston Red Sox", "price": 110},
                    ],
                }],
            },
            {
                "key": "fanduel",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "New York Yankees", "price": -130},
                        {"name": "Boston Red Sox", "price": 105},
                    ],
                }],
            },
        ],
    }


def test_filter_events_for_slate_uses_eastern_date():
    events = [
        {
            "commence_time": "2026-07-07T01:30:00Z",  # Jul 6 ET evening
            "away_team": "New York Yankees",
            "home_team": "Tampa Bay Rays",
        },
        {
            "commence_time": "2026-07-07T23:05:00Z",  # Jul 7 ET evening
            "away_team": "New York Yankees",
            "home_team": "Tampa Bay Rays",
        },
    ]
    kept = filter_events_for_slate(events, "2026-07-07")
    assert len(kept) == 1
    assert kept[0]["commence_time"].startswith("2026-07-07T23")


def test_board_pairs_books_before_devigging():
    board = build_board([_event()], "2026-06-27T12:00:00Z")
    yankees = board.quote("NYY", "BOS", "ml", "NYY")
    red_sox = board.quote("NYY", "BOS", "ml", "BOS")
    assert yankees is not None and red_sox is not None
    assert yankees.book_count == 2
    assert yankees.best_odds == -120
    assert red_sox.best_odds == 110
    assert math.isclose(
        yankees.vigfree_probability + red_sox.vigfree_probability,
        1.0,
        abs_tol=1e-6,
    )
    assert yankees.sharp_book_count == 1
    assert yankees.soft_book_count == 1


def test_odds_request_params_omits_bookmakers_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "ODDS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ODDS_REGIONS", "us,eu")
    monkeypatch.setattr(settings, "ODDS_BOOKS", "")
    params = odds_request_params(markets=settings.ODDS_GAME_MARKETS)
    assert "bookmakers" not in params
    assert params["regions"] == "us,eu"
    assert params["markets"] == "h2h,spreads,totals"
    assert params["oddsFormat"] == "american"


def test_odds_request_params_passes_official_bookmakers_filter(monkeypatch):
    monkeypatch.setattr(settings, "ODDS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ODDS_REGIONS", "us")
    monkeypatch.setattr(settings, "ODDS_BOOKS", "fanatics")
    params = odds_request_params(markets="h2h,spreads,totals")
    assert params["bookmakers"] == "fanatics"
    assert params["regions"] == "us"
    assert params["markets"] == "h2h,spreads,totals"


def test_odds_request_params_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ODDS_API_KEY", "")
    with pytest.raises(RuntimeError, match="ODDS_API_KEY"):
        odds_request_params(markets="h2h")
