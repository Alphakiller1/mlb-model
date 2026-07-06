"""Tests for neon section icons, metric grading, and static asset publishing."""
from __future__ import annotations

from mlbmodel.report.html_fmt import (
    edge_grade,
    lean_dir_html,
    metric_grade,
    pct_chip_html,
    prob_chip_html,
    section_head,
    section_icon_html,
    val_chip_html,
)
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


def test_metric_grade_osi_scale():
    assert metric_grade(62, "osi") == "c-good"
    assert metric_grade(38, "osi") == "c-weak"
    assert metric_grade(None, "osi") == "c-na"


def test_metric_grade_inverted_era():
    assert metric_grade(3.2, "era") == "c-good"
    assert metric_grade(5.5, "era") == "c-poor"


def test_val_chip_html_wraps_graded_value():
    html = val_chip_html(55, "osi", digits=0)
    assert 'class="chip c-good"' in html
    assert "55" in html


def test_prob_chip_html_scales_probability():
    html = prob_chip_html(0.62, digits=0)
    assert "62%" in html
    assert "chip" in html


def test_pct_chip_html_accepts_percent_display():
    html = pct_chip_html(58, digits=0)
    assert "58%" in html


def test_edge_grade_tiers():
    assert edge_grade(0.07) == "c-elite"
    assert edge_grade(0.04) == "c-good"
    assert edge_grade(0.02) == "c-mid"
    assert edge_grade(-0.02) == "c-poor"


def test_lean_dir_html_arrows():
    over = lean_dir_html("OVER")
    under = lean_dir_html("UNDER")
    assert "lean-dir--over" in over
    assert "▲" in over
    assert "lean-dir--under" in under
    assert "▼" in under
