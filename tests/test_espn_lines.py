"""Game lines fall back to DraftKings via ESPN when the Odds API cannot serve."""

import json

from mlbmodel import settings
from mlbmodel.market import espn_lines, quotes

ESPN_EVENT = {
    "id": "espn:1", "sport_key": "baseball_mlb", "commence_time": "2026-09-29T22:08Z",
    "home_team": "Atlanta Braves", "away_team": "Philadelphia Phillies",
    "bookmakers": [{"key": "draftkings", "title": "DraftKings", "last_update": "t", "markets": [
        {"key": "h2h", "outcomes": [{"name": "Atlanta Braves", "price": -204},
                                     {"name": "Philadelphia Phillies", "price": 170}]},
        {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 6.5},
                                        {"name": "Under", "price": -110, "point": 6.5}]}]}],
}


def test_a_spent_key_prices_the_slate_from_espn(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ODDS_API_KEY", "")
    monkeypatch.setattr(settings, "ODDS_BOOKMAKERS", "draftkings")
    monkeypatch.setattr(espn_lines, "events", lambda slate_date=None: [ESPN_EVENT])
    cache = tmp_path / "odds_latest.json"
    events, fetched = quotes.fetch_events(cache_path=cache)
    assert events == [ESPN_EVENT] and fetched
    assert json.loads(cache.read_text())["events"] == [ESPN_EVENT]
    board = quotes.build_board(events, fetched)
    assert board.game_quotes("PHI", "ATL")


def test_another_book_never_takes_espn_lines(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ODDS_API_KEY", "")
    monkeypatch.setattr(settings, "ODDS_BOOKMAKERS", "fanduel")
    monkeypatch.setattr(espn_lines, "events", lambda slate_date=None: [ESPN_EVENT])
    try:
        quotes.fetch_events(cache_path=tmp_path / "odds_latest.json")
    except RuntimeError:
        pass
    else:
        raise AssertionError("a non-DraftKings board must not be priced from ESPN's DraftKings lines")


def test_complete_free_lines_skip_the_paid_call(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ODDS_API_KEY", "live-key")
    monkeypatch.setattr(settings, "ODDS_BOOKMAKERS", "draftkings")
    monkeypatch.setattr(settings, "ODDS_F5_ENABLED", False)
    monkeypatch.setattr(espn_lines, "events", lambda slate_date=None: [ESPN_EVENT])

    def paid(**kwargs):
        raise AssertionError("paid call")

    monkeypatch.setattr(quotes, "_fetch_odds_api_events", paid)
    events, _ = quotes.fetch_events(cache_path=tmp_path / "o.json", needed={("PHI", "ATL")})
    assert events == [ESPN_EVENT]
