import json
import urllib.parse

from mlbmodel.market.props import (
    build_prop_board,
    fetch_prop_payloads,
    filter_events_for_slate,
    market_report,
)


def _book(key, over, under):
    return {
        "key": key,
        "markets": [{
            "key": "pitcher_strikeouts",
            "outcomes": [
                {
                    "name": "Over",
                    "description": "Test Pitcher",
                    "price": over,
                    "point": 5.5,
                },
                {
                    "name": "Under",
                    "description": "Test Pitcher",
                    "price": under,
                    "point": 5.5,
                },
            ],
        }],
    }


def test_prop_board_pairs_prices_and_generates_market_state():
    board = build_prop_board(
        [{
            "away_team": "New York Yankees",
            "home_team": "Boston Red Sox",
            "bookmakers": [
                _book("pinnacle", 105, -125),
                _book("fanduel", 115, -140),
            ],
        }],
        "2026-06-27T12:00:00+00:00",
    )
    pitcher = {
        "pitcher": "Test Pitcher",
        "projections": {
            "K": {"mean": 6.4, "sd": 1.5},
        },
    }

    reports = market_report(pitcher, board)
    over = next(report for report in reports if report["side"] == "over")
    under = next(report for report in reports if report["side"] == "under")

    assert over["best_odds"] == 115
    assert over["best_book"] == "fanduel"
    assert over["model_probability"] > over["market_probability"]
    # 6.4 projected against a 5.5 line is a ~28pt edge over the de-vigged price. That is
    # far past the plausibility limit, so it must read REVIEW — an edge that size is
    # evidence the projection or the line mapping is wrong, not an opportunity. This
    # previously reported MONITOR because implausibility was only checked on the promoted
    # path, and the gate has never been open.
    assert over["state"] == "REVIEW"
    assert "plausibility limit" in over["reason"]
    assert under["state"] == "AVOID"


def test_modest_edge_still_monitors_while_the_gate_is_shut():
    """The plausibility guard must not swallow ordinary edges."""
    board = build_prop_board(
        [{
            "away_team": "New York Yankees",
            "home_team": "Boston Red Sox",
            "bookmakers": [
                _book("pinnacle", 105, -125),
                _book("fanduel", 115, -140),
            ],
        }],
        "2026-06-27T12:00:00+00:00",
    )
    pitcher = {
        "pitcher": "Test Pitcher",
        # Projecting the line itself: a few points of edge from the price alone.
        "projections": {"K": {"mean": 5.5, "sd": 1.5}},
    }

    over = next(
        report for report in market_report(pitcher, board) if report["side"] == "over"
    )
    assert 0 < over["edge"] < 0.15
    assert over["state"] == "MONITOR"


def test_draftkings_only_pair_produces_a_line_relative_edge():
    board = build_prop_board(
        [{
            "away_team": "New York Yankees",
            "home_team": "Boston Red Sox",
            "bookmakers": [_book("draftkings", 105, -125)],
        }],
        "2026-07-27T12:00:00+00:00",
    )
    pitcher = {
        "pitcher": "Test Pitcher",
        "projections": {"K": {"mean": 5.5, "sd": 1.5}},
    }

    over = next(
        report for report in market_report(pitcher, board) if report["side"] == "over"
    )

    assert over["best_book"] == "draftkings"
    assert over["edge"] is not None and over["edge"] > 0
    assert over["ev"] is not None and over["ev"] > 0
    assert over["state"] == "MONITOR"


def test_prop_events_are_filtered_by_eastern_slate_date():
    events = [
        {"id": "late-previous", "commence_time": "2026-07-27T02:00:00Z"},
        {"id": "active", "commence_time": "2026-07-27T18:00:00Z"},
        {"id": "next", "commence_time": "2026-07-28T18:00:00Z"},
    ]

    filtered = filter_events_for_slate(events, "2026-07-27")

    assert [event["id"] for event in filtered] == ["active"]


def test_paid_prop_calls_are_limited_to_the_active_slate(monkeypatch, tmp_path):
    events = [
        {"id": "active", "commence_time": "2026-07-27T18:00:00Z"},
        {"id": "tomorrow", "commence_time": "2026-07-28T18:00:00Z"},
    ]
    active_payload = {
        "id": "active", "away_team": "New York Yankees",
        "home_team": "Boston Red Sox", "bookmakers": [],
    }
    requested = []

    class Response:
        def __init__(self, payload):
            self.payload = payload
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return json.dumps(self.payload).encode()

    def urlopen(url, timeout):
        requested.append(url)
        if "/events?" in url:
            return Response(events)
        if "/events/active/odds?" in url:
            return Response(active_payload)
        raise AssertionError(f"unexpected paid event request: {url}")

    monkeypatch.setattr("mlbmodel.market.props.settings.ODDS_API_KEY", "test")
    monkeypatch.setattr("mlbmodel.market.props.usage.check_budget", lambda _: None)
    monkeypatch.setattr("mlbmodel.market.props.usage.record", lambda *args: None)
    monkeypatch.setattr("mlbmodel.market.props.urllib.request.urlopen", urlopen)

    payloads, _ = fetch_prop_payloads(
        tmp_path / "props.json", slate_date="2026-07-27"
    )

    assert [payload["id"] for payload in payloads] == ["active"]
    assert any("/events/active/odds?" in url for url in requested)
    assert all("/events/tomorrow/odds?" not in url for url in requested)


def test_prop_fetch_requests_only_the_selected_edge_markets(monkeypatch, tmp_path):
    events = [{"id": "active", "commence_time": "2026-07-27T18:00:00Z"}]
    requested = []

    class Response:
        headers = {}

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return json.dumps(self.payload).encode()

    def urlopen(url, timeout):
        requested.append(url)
        return Response(events if "/events?" in url else {"bookmakers": []})

    monkeypatch.setattr("mlbmodel.market.props.settings.ODDS_API_KEY", "test")
    monkeypatch.setattr("mlbmodel.market.props.usage.check_budget", lambda _: None)
    monkeypatch.setattr("mlbmodel.market.props.usage.record", lambda *args: None)
    monkeypatch.setattr("mlbmodel.market.props.urllib.request.urlopen", urlopen)

    fetch_prop_payloads(
        tmp_path / "props.json",
        slate_date="2026-07-27",
        markets=("pitcher_strikeouts", "pitcher_walks"),
    )

    paid_url = next(url for url in requested if "/events/active/odds?" in url)
    markets = urllib.parse.parse_qs(urllib.parse.urlsplit(paid_url).query)["markets"]
    assert markets == ["pitcher_strikeouts,pitcher_walks"]
    assert "pitcher_outs" not in paid_url

