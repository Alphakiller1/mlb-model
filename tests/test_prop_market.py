from mlbmodel.market.props import build_prop_board, market_report


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
    assert over["state"] == "MONITOR"
    assert under["state"] == "AVOID"

