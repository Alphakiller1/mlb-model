from mlbmodel.market.props import PropOddsBoard
from mlbmodel.report.app import _props
from mlbmodel.report.views import prediction_audit_html


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


def test_prediction_audit_reports_all_game_f5_and_prop_rows():
    rows = [
        {
            "slate_date": "2026-08-24", "recorded_at": "2026-08-24T16:00:00Z",
            "game_pk": 1, "source": "matchup", "market": "runline",
            "selection": "NYY", "line": -1.5, "model_prob": 0.58,
            "entry_odds": 140, "realized_value": 3, "settled": True,
            "won": True, "run_id": "game-run",
        },
        {
            "slate_date": "2026-08-24", "recorded_at": "2026-08-24T16:01:00Z",
            "game_pk": 1, "source": "f5", "market": "f5_total",
            "selection": "under", "line": 4.5, "model_prob": 0.55,
            "entry_odds": -110, "settled": False,
            "ungraded_reason": "awaiting linescore", "run_id": "f5-run",
        },
        {
            "slate_date": "2026-08-24", "recorded_at": "2026-08-24T16:02:00Z",
            "game_pk": 1, "source": "projection", "market": "k",
            "selection": "model:cole", "model_value": 7.2, "realized_value": 8,
            "pitcher_name": "Gerrit Cole", "settled": True, "won": None,
            "run_id": "prop-run",
        },
    ]

    rendered = prediction_audit_html(rows)
    assert "All game and F5 prediction runs (2)" in rendered
    assert "All player-prop prediction runs (1)" in rendered
    assert "runline NYY -1.5" in rendered
    assert "f5_total under 4.5" in rendered
    assert "Gerrit Cole" in rendered
    assert "GRADED" in rendered
    assert "AWAITING" in rendered

    lazy = prediction_audit_html(rows, external_asset_url="assets/prediction-audit.json")
    assert "Load complete history" in lazy
    assert "prediction-audit.json" in lazy
    assert "renderPredictionAudit" in lazy
    assert "results-game-audit-body" in lazy
    assert "results-prop-audit-body" in lazy
