import math

from mlbmodel.market.quotes import build_board


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
