"""Smoke tests for the unified report shell."""
from __future__ import annotations

from pathlib import Path

from mlbmodel.report.app import _NAV, build_app
from mlbmodel.report.matchup import build_report, matchup_summary_html

DATA = Path(__file__).resolve().parents[1] / "deployment_data"


def test_matchup_summary_html_compact():
    report = build_report("HOU", "DET", fetch=False, data_dir=DATA)
    html = matchup_summary_html(report)
    assert "matchup-summary" in html
    assert "HOU" in html and "DET" in html


def test_build_app_renders_all_views():
    html = build_app("HOU@DET", fetch=False, data_dir=DATA)
    for key, _label in _NAV:
        assert f'id="v-{key}"' in html
    assert "chase-nav-link" in html
    assert "sortable" in html
    assert "function show(k)" in html
    assert "location.hash" in html
    assert "pitcher-prop-deck" in html
    assert "Matchup context" in html
    assert "edge-command" in html
    assert "Where we have edge today" in html
    assert "model_ui.css" not in html  # inlined in shell
    assert ".edge-hero-stat::before" in html or "edge-hero-stat" in html
    assert "ca-neon-icon" in html


def test_build_app_matchup_switch_hybrid_terminals():
    """Featured game is full; others ship compact + deferred full terminal in <template>."""
    html = build_app("NYY@BOS", fetch=False, data_dir=DATA)
    assert html.count('class="matchup-report') >= 2
    assert "matchup-full-src" in html
    assert "matchup-summary" in html
    assert "matchup-body" in html
