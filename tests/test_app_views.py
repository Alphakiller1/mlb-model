from mlbmodel.market.props import PropOddsBoard
from mlbmodel.report.app import _props


def test_props_view_one_toggle_card_per_pitcher_with_clear_play():
    distribution = {"mean": 5.4, "p10": 3.0, "p50": 5.0, "p90": 8.0, "sd": 1.8}
    rendered = _props(
        [{
            "pitcher": "Away Starter",
            "pitcher_id": 1,
            "team": "NYY",
            "opponent": "BOS",
            "projection_trust": "trusted",
            "projections": {
                "K": distribution,
                "BB": distribution,
                "ER": distribution,
                "Outs": distribution,
                "H": distribution,
            },
            "market_report": [{
                "prop": "K",
                "side": "over",
                "line": 5.5,
                "model_probability": 0.58,
                "edge": 0.04,
                "best_book": "Underdog",
            }],
            "pitch_matchup": {"pitches": []},
        }],
        PropOddsBoard([]),
    )

    assert "pitcher-prop-deck" in rendered
    assert "pitcher-prop-card" in rendered
    # The two channels are named for what their numbers are measured against, and each
    # states its basis, so a pick'em figure can never be read as an edge against a price.
    assert "Priced markets" in rendered
    assert "Pick&#x27;em" in rendered or "Pick'em" in rendered
    assert "de-vigged" in rendered
    assert "breakeven" in rendered
    assert "prop-engine-section" in rendered
    assert "prop-primary-lean" in rendered
    assert "OVER" in rendered
    assert "5.5" in rendered
    assert "props-graded-table" not in rendered
    assert "Pick&apos;em board" not in rendered
    assert "prop-panel" not in rendered


def test_props_view_uses_one_canonical_game_for_both_starters():
    pitchers = [
        {
            "pitcher": "Away Starter",
            "team": "NYY",
            "opponent": "BOS",
            "side": "away",
            "projections": {"K": {"mean": 5.2}},
        },
        {
            "pitcher": "Home Starter",
            "team": "BOS",
            "opponent": "NYY",
            "side": "home",
            "projections": {"K": {"mean": 6.1}},
        },
    ]

    rendered = _props(pitchers, PropOddsBoard([]))

    # The game-filter <select> this test was written against no longer exists in the deck;
    # each starter is now labelled from its own side (NYY @ BOS / BOS @ NYY). What still
    # matters is that both starters of one matchup render exactly once each — the original
    # bug was a starter being dropped or duplicated when the two sides were reconciled.
    assert rendered.count("Away Starter") == 1
    assert rendered.count("Home Starter") == 1
    assert "pitcher-prop-card" in rendered
