"""Structural golden checks for the unified report shell."""
from __future__ import annotations

from pathlib import Path

from mlbmodel.report.app import build_app

DATA = Path(__file__).resolve().parents[1] / "deployment_data"


def test_build_app_structure_markers():
    html = build_app("HOU@DET", fetch=False, data_dir=DATA)
    assert html.count("ca-board") >= 12
    assert html.count("ca-section-head") >= 5
    assert html.count("ca-neon-icon") >= 3
    assert 'id="v-trends"' in html
    assert "sortable" in html
    assert "function switchGame" in html
    assert "matchup-full-src" in html
