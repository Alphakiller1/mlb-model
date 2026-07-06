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
    assert "prop-board" in html


def test_build_app_matchup_switch_includes_full_terminals():
    """Every slate game gets the full matchup terminal (not compact-only summaries)."""
    html = build_app("NYY@BOS", fetch=False, data_dir=DATA)
    assert html.count('class="matchup-report') >= 2
    assert html.count("rtabs") >= 2
