from pathlib import Path

from mlbmodel.market import prizepicks
from mlbmodel.market.pickem import load_pickem_lines, pickem_market_reports
from mlbmodel.report.props_ui import pitcher_prop_deck

DATA = Path(__file__).resolve().parents[1] / "deployment_data"


def test_load_pickem_lines_uses_bundled_snapshot_when_cache_missing(tmp_path):
    lines = load_pickem_lines(
        prizepicks,
        tmp_path / "prizepicks_lines.json",
        fetch=False,
        fallback_path=DATA / "prizepicks_lines.json",
    )
    assert lines
    assert any(line.get("proj_key") == "K" for line in lines)


def test_load_pickem_lines_prefers_cache_over_fallback(tmp_path):
    cache_path = tmp_path / "prizepicks_lines.json"
    cache_path.write_text('[{"player_key": "cached only", "proj_key": "K", "line": 1.0}]')
    lines = load_pickem_lines(
        prizepicks,
        cache_path,
        fetch=False,
        fallback_path=DATA / "prizepicks_lines.json",
    )
    assert len(lines) == 1
    assert lines[0]["player_key"] == "cached only"


def test_pickem_market_reports_grades_model_lean():
    board = prizepicks.board_by_player(
        load_pickem_lines(
            prizepicks,
            DATA / "prizepicks_lines.json",
            fetch=False,
        )
    )
    pitcher = {
        "pitcher": "Freddy Peralta",
        "projections": {
            "K": {"mean": 6.0, "sd": 1.5},
            "PP_Fantasy": {"mean": 28.0, "sd": 6.0},
            "Outs": {"mean": 16.0, "sd": 2.0},
            "ER": {"mean": 2.5, "sd": 1.2},
            "H": {"mean": 5.0, "sd": 1.5},
            "BB": {"mean": 2.0, "sd": 0.8},
        },
    }
    reports = pickem_market_reports(pitcher, [("PrizePicks", board)])
    assert reports
    assert reports[0]["state"] in {"OVER", "UNDER", "WATCH"}
    assert reports[0]["source"] == "pickem"


def test_props_card_uses_pickem_market_state():
    board = prizepicks.board_by_player(
        load_pickem_lines(
            prizepicks,
            DATA / "prizepicks_lines.json",
            fetch=False,
        )
    )
    projections = {
        "K": {"mean": 6.0, "sd": 1.5},
        "PP_Fantasy": {"mean": 28.0, "sd": 6.0},
        "Outs": {"mean": 16.0, "sd": 2.0},
        "ER": {"mean": 2.5, "sd": 1.2},
        "H": {"mean": 5.0, "sd": 1.5},
        "BB": {"mean": 2.0, "sd": 0.8},
    }
    pitcher = {
        "pitcher": "Freddy Peralta",
        "pitcher_id": 1,
        "team": "NYM",
        "opponent": "ATL",
        "projection_trust": "trusted",
        "projections": projections,
        "market_report": pickem_market_reports(
            {"pitcher": "Freddy Peralta", "projections": projections},
            [("PrizePicks", board)],
        ),
        "pitch_matchup": {"pitches": []},
    }
    rendered = pitcher_prop_deck([pitcher], [("PrizePicks", board)])
    assert "NO MARKET" not in rendered
    assert "lean-dir--" in rendered
