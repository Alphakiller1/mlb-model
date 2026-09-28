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


def test_the_board_export_carries_each_games_book_line():
    from mlbmodel.report.export import _book_line

    odds = quotes.build_board([ESPN_EVENT], "t")
    line = _book_line(odds, "PHI", "ATL")
    assert line == {"name": "DraftKings", "total": 6.5, "home_moneyline": -204, "away_moneyline": 170}
    assert _book_line(None, "PHI", "ATL") is None


def test_the_board_export_carries_starter_prop_projections():
    from mlbmodel.report.export import _player_projection

    dist = {"mean": 5.8, "p10": 3.0, "p50": 6.0, "p90": 9.0, "sd": 2.1, "pmf": {"5": 0.2, "6": 0.3}}
    row = _player_projection({
        "pitcher": "Zack Wheeler", "pitcher_id": 554430, "team": "PHI", "opponent": "ATL",
        "side": "away", "hand": "R", "projection_trust": "trusted", "expected_ip": 6.1,
        "projections": {"K": dist, "Fantasy": dist},
        "market_report": [{"prop": "K", "side": "Over", "line": 6.5, "best_odds": -115,
                           "best_book": "draftkings", "model_probability": 0.41,
                           "market_probability": 0.52, "edge": -0.11, "state": "NO EDGE"}],
    })
    assert row["player_name"] == "Zack Wheeler" and set(row["stats"]) == {"K"}
    assert row["stats"]["K"]["pmf"]["6"] == 0.3 and row["lines"][0]["line"] == 6.5
    assert _player_projection({"pitcher": "X", "projections": {}}) is None
