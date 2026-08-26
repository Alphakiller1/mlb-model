"""Smoke tests for the unified report shell."""
from __future__ import annotations

from pathlib import Path

from mlbmodel.baseball.repository import DataRepository
from mlbmodel.report.app import _NAV, build_app
from mlbmodel.report.matchup import build_report, matchup_summary_html

DATA = Path(__file__).resolve().parents[1] / "deployment_data"


def _featured_game() -> tuple[str, str]:
    """First matchup on the committed snapshot.

    These tests used to hardcode "NYY@TBR". `deployment_data/` is a ROLLING snapshot that
    gets re-pushed from a local refresh, so the hardcoded pair fell off the slate and the
    whole suite went red — which is how a separate lint failure sat unnoticed on main.
    Reading the slate keeps the tests true whatever day the snapshot was taken.
    """
    frame = DataRepository(DATA).slate()
    assert frame is not None and len(frame), "deployment_data has no slate to smoke-test"
    row = frame.iloc[0]
    return str(row["Away"]).upper().strip(), str(row["Home"]).upper().strip()


AWAY, HOME = _featured_game()
GAME = f"{AWAY}@{HOME}"


def test_matchup_summary_html_compact():
    report = build_report(AWAY, HOME, fetch=False, data_dir=DATA)
    html = matchup_summary_html(report)
    assert "matchup-summary" in html
    assert AWAY in html and HOME in html


def test_build_app_renders_all_views():
    html = build_app(GAME, fetch=False, data_dir=DATA)
    for key, _label in _NAV:
        assert f'id="v-{key}"' in html
    assert "desk-frame" in html
    assert "sidebar" in html
    assert 'data-v="matchups"' in html
    assert "sortable" in html
    assert "function show(k)" in html
    assert "location.hash" in html
    assert "pitcher-prop-deck" in html.split("v-props")[1].split("</section>")[0]
    assert "prop-engine-table" in html
    # Edge command strip removed from Today
    assert '<div class="edge-command' not in html
    assert "Where we have edge today" not in html
    # No external stylesheet links: the page must be self-contained for Pages. Asserted on
    # the link tag rather than the bare filename, so a CSS comment naming a file cannot
    # fail this.
    assert "<link" not in html.lower() or 'rel="stylesheet"' not in html.lower()
    assert "sym-metric-board" in html
    assert "matchup-process" in html
    assert "desk-process" in html
    assert 'data-step="m-decision"' in html
    assert 'data-step="m-splits"' in html
    assert 'data-step="m-risks"' in html
    assert "jumpMatchupStep" in html
    assert "desk-verdict" in html


def test_build_app_matchup_switch_hybrid_terminals():
    """Featured game is full; others ship compact + deferred full terminal in <template>."""
    import re

    html = build_app(GAME, fetch=False, data_dir=DATA)
    assert html.count('class="matchup-report"') >= 2
    panels = re.findall(r'<div class="matchup-report" data-game="([^"]+)"([^>]*)>', html)
    visible = [key for key, attrs in panels if "hidden" not in attrs]
    assert visible == [GAME]
    assert "matchup-full-src" in html
    assert "matchup-summary" in html
    assert "matchup-body" in html


def test_build_app_single_font_import_and_typography_tokens():
    html = build_app(GAME, fetch=False, data_dir=DATA)
    assert html.count("fonts.googleapis.com") == 1
    assert "--mm-text-base" in html or "--font-ui" in html
    # The Chase Analytics typefaces, shared with wnba-edge-model and nfl-model. This
    # previously asserted "IBM Plex Sans" — the desk redesign's private font stack — which
    # is precisely how this product drifted off-brand without a test noticing.
    assert "DM Sans" in html
    assert "Roboto Condensed" in html


def test_build_app_does_not_redefine_brand_tokens():
    """chase_tokens.css must win: no later sheet may reassign a token to a literal value."""
    html = build_app(GAME, fetch=False, data_dir=DATA)
    assert "#08090F" in html          # canonical deep-navy page ground
    assert "#9A6BFF" in html          # canonical violet brand
    assert "#B794FF" not in html      # the forked graphite violet
    assert "IBM Plex" not in html     # the forked type stack
