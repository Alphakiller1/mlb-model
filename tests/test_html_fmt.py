"""Tests for neon section icons and static asset publishing."""
from __future__ import annotations

from mlbmodel.report.html_fmt import section_head, section_icon_html
from mlbmodel.report.static_assets import publish_assets


def test_section_icon_inlines_neon_svg():
    html = section_icon_html("markets")
    assert "ca-neon-icon" in html
    assert "<svg" in html


def test_section_head_wraps_title():
    html = section_head("Decision board", icon="markets", purpose="Sharp + model fusion")
    assert "ca-section-head" in html
    assert "Decision board" in html
    assert "Sharp + model fusion" in html


def test_publish_assets_copies_icons(tmp_path):
    count = publish_assets(tmp_path)
    assert count >= 8
    assert (tmp_path / "assets" / "icons" / "neon-trend-up.svg").is_file()
