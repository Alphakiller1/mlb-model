"""Smoke tests for the unified report shell."""
from __future__ import annotations

from pathlib import Path

from mlbmodel.report.app import _NAV, build_app

DATA = Path(__file__).resolve().parents[1] / "deployment_data"


def test_build_app_renders_all_views():
    html = build_app("HOU@DET", fetch=False, data_dir=DATA)
    for key, _label in _NAV:
        assert f'id="v-{key}"' in html
    assert "chase-nav-link" in html
    assert "sortable" in html
    assert "function show(k)" in html
    assert "location.hash" in html
