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
    assert "Book &amp; prediction market" in rendered
    assert "Fantasy" in rendered
    assert "prop-engine-section" in rendered
    assert "prop-primary-lean" in rendered
    assert "OVER" in rendered
    assert "5.5" in rendered
    assert "props-graded-table" not in rendered
    assert "Pick&apos;em board" not in rendered
    assert "prop-panel" not in rendered
