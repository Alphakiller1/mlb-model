"""Smoke tests for the unified report shell."""
from __future__ import annotations

from pathlib import Path

from mlbmodel.report.app import _NAV, build_app
from mlbmodel.report.matchup import build_report, matchup_summary_html

DATA = Path(__file__).resolve().parents[1] / "deployment_data"


def test_matchup_summary_html_compact():
    report = build_report("NYY", "TBR", fetch=False, data_dir=DATA)
    html = matchup_summary_html(report)
    assert "matchup-summary" in html
    assert "NYY" in html and "TBR" in html


def test_build_app_renders_all_views():
    html = build_app("NYY@TBR", fetch=False, data_dir=DATA)
    for key, _label in _NAV:
        assert f'id="v-{key}"' in html
    assert "desk-frame" in html
    assert "sidebar" in html
    assert 'data-v="today"' in html
    assert "sortable" in html
    assert "function show(k)" in html
    assert "location.hash" in html
    assert "pitcher-prop-deck" in html.split("v-props")[1].split("</section>")[0]
    assert "prop-engine-table" in html
    # Edge command strip removed from Today
    assert "edge-command" not in html
    assert "Where we have edge today" not in html
    assert "model_ui.css" not in html  # inlined in shell
    assert "sym-metric-board" in html
    assert "matchup-process" in html
    assert "desk-process" in html
    assert 'id="m-decision"' in html
    assert 'id="m-splits"' in html
    assert 'id="m-risks"' in html
    assert "desk-verdict" in html


def test_build_app_matchup_switch_hybrid_terminals():
    """Featured game is full; others ship compact + deferred full terminal in <template>."""
    import re

    html = build_app("NYY@TBR", fetch=False, data_dir=DATA)
    assert html.count('class="matchup-report"') >= 2
    panels = re.findall(r'<div class="matchup-report" data-game="([^"]+)"([^>]*)>', html)
    visible = [key for key, attrs in panels if "hidden" not in attrs]
    assert visible == ["NYY@TBR"]
    assert "matchup-full-src" in html
    assert "matchup-summary" in html
    assert "matchup-body" in html


def test_build_app_single_font_import_and_typography_tokens():
    html = build_app("NYY@TBR", fetch=False, data_dir=DATA)
    assert html.count("fonts.googleapis.com") == 1
    assert "--mm-text-base" in html or "--font-ui" in html
    assert "IBM Plex Sans" in html
