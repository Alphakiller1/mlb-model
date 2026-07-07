"""Tests for slate game key disambiguation (doubleheaders)."""
from __future__ import annotations

from mlbmodel.report.game_keys import (
    assign_slate_keys,
    parse_game_key,
    resolve_featured_game,
)


def test_assign_slate_keys_doubleheader():
    slate = [
        {"away": "MIL", "home": "STL", "time": "2:15 PM ET"},
        {"away": "MIL", "home": "STL", "time": "7:45 PM ET"},
        {"away": "NYY", "home": "BOS", "time": "7:10 PM ET"},
    ]
    assign_slate_keys(slate)
    assert slate[0]["key"] == "MIL@STL"
    assert slate[1]["key"] == "MIL@STL#2"
    assert slate[2]["key"] == "NYY@BOS"


def test_parse_game_key():
    assert parse_game_key("MIL@STL") == ("MIL", "STL", 1)
    assert parse_game_key("MIL@STL#2") == ("MIL", "STL", 2)


def test_resolve_featured_game_first_of_doubleheader():
    slate = [
        {"away": "MIL", "home": "STL", "key": "MIL@STL"},
        {"away": "MIL", "home": "STL", "key": "MIL@STL#2"},
    ]
    assert resolve_featured_game("MIL@STL", slate) == "MIL@STL"
    assert resolve_featured_game("MIL@STL#2", slate) == "MIL@STL#2"


def test_build_app_single_active_matchup_per_key():
    from pathlib import Path

    from mlbmodel.report.app import build_app

    data = Path(__file__).resolve().parents[1] / "deployment_data"
    html = build_app("MIL@STL", fetch=False, data_dir=data)
    import re

    panels = re.findall(r'<div class="matchup-report" data-game="([^"]+)"([^>]*)>', html)
    assert len(panels) == len({key for key, _ in panels})
    assert 'data-game="MIL@STL"' in html
    assert 'data-game="MIL@STL#2"' in html
    visible = [key for key, attrs in panels if "hidden" not in attrs]
    assert visible == ["MIL@STL"]
