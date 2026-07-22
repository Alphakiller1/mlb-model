from mlbmodel.market.props import PropOddsBoard
from mlbmodel.report.app import _markets, _portfolio, _props
from mlbmodel.storage.supabase import ReadResult


class StaticReader:
    def __init__(self, rows=None, error=None):
        self.result = ReadResult(rows or [], error)

    def get(self, _path):
        return self.result


def test_props_board_has_distributions_pitch_context_and_market_state():
    distribution = {"mean": 5.4, "p10": 3.0, "p50": 5.0, "p90": 8.0, "sd": 1.8}
    rendered = _props(
        [
            {
                "pitcher": "Away Starter",
                "pitcher_id": 1,
                "team": "NYY",
                "opponent": "BOS",
                "state": "STABLE",
                "market_state": "NO MARKET",
                "confidence": "medium",
                "luck_runs": 0.1,
                "expected_ip": 5.7,
                "skill_era": 3.55,
                "lineup_status": "confirmed",
                "lineup": {"score": 55.0},
                "pitch_matchup": {
                    "response_source": "posted lineup, batting-order weighted",
                    "coverage_pct": 84,
                    "lineup_batters_matched": 9,
                    "pitches": [
                        {
                            "pitch": "Slider",
                            "usage_pct": 31.0,
                            "pitcher_whiff_pct": 36.0,
                            "lineup_whiff_pct": 29.0,
                            "pitcher_xwoba": 0.270,
                            "lineup_xwoba": 0.300,
                            "k_delta": 0.4,
                            "er_factor_delta": -0.02,
                            "edge": "pitcher edge",
                        }
                    ],
                },
                "projections": {
                    "K": distribution,
                    "BB": distribution,
                    "ER": distribution,
                    "Outs": distribution,
                },
                "market_report": [],
            }
        ],
        PropOddsBoard([]),
    )

    assert "Prop market report" in rendered
    assert "NO MARKET" in rendered
    assert "5.4" in rendered
    assert "3–8" in rendered
    assert "Arsenal vs opponent production" in rendered
    assert "posted lineup, batting-order weighted" in rendered


def test_markets_view_renders_live_decision_cards():
    slate = [{"pk": 1, "away": "NYY", "home": "BOS"}]
    sharp_by_pk = {
        1: [
            {
                "market_type": "ml",
                "selection": "BOS",
                "divergence": 0.03,
                "sharp_novig_prob": 0.57,
                "soft_novig_prob": 0.52,
                "n_sharp_books": 2,
                "n_soft_books": 4,
                "steam_flag": True,
            }
        ]
    }
    model_by_pk = {
        1: [
            {
                "market": "ml",
                "side": "BOS",
                "model": 57.5,
                "edge": 3.2,
                "ev": 0.041,
                "mkt": -110,
                "fair": -135,
                "book": "pinnacle",
            }
        ]
    }

    rendered = _markets(slate, sharp_by_pk, model_by_pk)

    assert "market-card" in rendered
    assert "STRONG BET" in rendered
    assert "pinnacle" in rendered
    assert "+4.1% EV" in rendered
    assert "STEAM" in rendered


def test_props_board_renders_live_prop_market_state():
    distribution = {"mean": 5.4, "p10": 3.0, "p50": 5.0, "p90": 8.0, "sd": 1.8}
    rendered = _props(
        [
            {
                "pitcher": "Away Starter",
                "pitcher_id": 1,
                "team": "NYY",
                "opponent": "BOS",
                "state": "STABLE",
                "market_state": "MONITOR",
                "confidence": "high",
                "luck_runs": 0.0,
                "expected_ip": 5.7,
                "skill_era": 3.55,
                "lineup_status": "confirmed",
                "projection_trust": "trusted",
                "lineup": {"score": 55.0},
                "pitch_matchup": {"pitches": []},
                "projections": {
                    "K": distribution,
                    "BB": distribution,
                    "ER": distribution,
                    "Outs": distribution,
                },
                "market_report": [
                    {
                        "prop": "K",
                        "side": "over",
                        "line": 5.5,
                        "best_odds": 115,
                        "best_book": "pinnacle",
                        "model_probability": 0.61,
                        "market_probability": 0.54,
                        "edge": 0.07,
                        "ev": 0.08,
                        "state": "MONITOR",
                    }
                ],
            }
        ],
        PropOddsBoard([]),
    )

    assert "Priced prop sides" in rendered
    assert "pinnacle" in rendered
    assert "MONITOR" in rendered
    assert "+7.0pt" in rendered


def test_portfolio_view_flags_concentration_and_respects_gate():
    positions = [
        {
            "game_pk": 1,
            "market_type": "h2h",
            "selection": "NYY",
            "line": None,
            "entry_odds": 110,
            "model_probability": 0.52,
            "market_probability": 0.48,
            "stake_units": 2.5,
            "entry_time": "2026-06-27T12:00:00Z",
            "strategy_version": "test",
        }
    ]
    slate = [{"pk": 1, "away": "NYY", "home": "BOS"}]
    rendered = _portfolio(StaticReader(positions), {"verdict": "HOLD"}, slate)

    assert "Concentration warning" in rendered
    assert "Sizing is disabled until" in rendered
    assert "2.50u" in rendered
