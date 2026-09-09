import json
import math

from mlbmodel.market.quotes import build_board, filter_events_for_slate


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


def test_empty_fetch_does_not_blank_a_good_odds_cache(tmp_path, monkeypatch):
    """A 200 with zero events must not overwrite a populated cache.

    A bookmaker filter the key cannot serve returns 200 with `bookmakers: []`
    on every event - a Fanatics-only pull on this key returns 26 MLB events and
    zero prices. Writing that blanks the published board while reporting a
    fresh timestamp, which is the opposite of the README safety invariant that
    failed data reads produce visible no-action states.
    """
    from mlbmodel.market import quotes

    cache = tmp_path / "odds_latest.json"
    cache.write_text(
        json.dumps({"fetched_at": "2026-09-08T00:00:00+00:00",
                    "events": [{"id": "abc", "bookmakers": [{"key": "draftkings"}]}]}),
        encoding="utf-8",
    )

    class _Resp:
        headers = {}
        def read(self):
            return b"[]"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(quotes.urllib.request, "urlopen", lambda *a, **k: _Resp())
    monkeypatch.setattr(quotes.usage, "record", lambda *a, **k: None)
    monkeypatch.setattr(quotes.settings, "ODDS_F5_ENABLED", False, raising=False)
    monkeypatch.setattr(quotes.settings, "ODDS_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(quotes.usage, "check_budget", lambda *a, **k: None, raising=False)

    events, fetched = quotes.fetch_events(cache_path=cache)

    assert len(events) == 1, "cached events were discarded by an empty fetch"
    assert fetched == "2026-09-08T00:00:00+00:00", "cache age was reset, hiding staleness"
    assert json.loads(cache.read_text(encoding="utf-8"))["events"], "cache file was blanked"
