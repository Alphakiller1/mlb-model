from mlbmodel.market.props import (
    build_prop_board,
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


def test_prop_events_are_filtered_by_eastern_slate_date():
    events = [
        {"id": "late-previous", "commence_time": "2026-07-27T02:00:00Z"},
        {"id": "active", "commence_time": "2026-07-27T18:00:00Z"},
        {"id": "next", "commence_time": "2026-07-28T18:00:00Z"},
    ]

    filtered = filter_events_for_slate(events, "2026-07-27")

    assert [event["id"] for event in filtered] == ["active"]

