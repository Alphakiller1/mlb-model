from mlbmodel.market.props import PropOddsBoard
from mlbmodel.report.app import _props


def test_props_view_uses_flat_tables_not_accordion():
    distribution = {"mean": 5.4, "p10": 3.0, "p50": 5.0, "p90": 8.0, "sd": 1.8}
    rendered = _props(
        [{
            "pitcher": "Away Starter",
            "pitcher_id": 1,
            "team": "NYY",
            "opponent": "BOS",
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
        }],
        PropOddsBoard([]),
    )

    assert "Projections" in rendered
    assert "Graded lines" in rendered
    assert "props-graded-table" in rendered
    assert "5.4" in rendered
    assert "pitcher-prop-deck" not in rendered
    assert "pitcher-prop-card" not in rendered
