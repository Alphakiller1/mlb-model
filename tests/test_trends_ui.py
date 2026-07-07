from mlbmodel.report.trends_ui import (
    _sample_chip,
    mag_chip_html,
    trend_bet_html,
    trend_headline,
    trends_section_html,
)
from mlbmodel.trends.prop_detectors import detect_pitcher_prop_trends


def test_trend_bet_html_structured_under():
    out = trend_bet_html("ATL team total UNDER")
    assert "UNDER" in out
    assert "ATL" in out
    assert "team total" in out.lower()


def test_trend_bet_html_prop_over():
    out = trend_bet_html("Gerrit Cole Strikeouts OVER")
    assert "OVER" in out
    assert "Strikeouts" in out


def test_mag_chip_html_color_coded():
    out = mag_chip_html(1.6)
    assert "chip" in out
    assert "σ" in out


def test_trend_headline_truncates():
    long = "A" * 100
    assert len(trend_headline(type("T", (), {"trend_description": long})())) <= 78


def test_prop_detector_fantasy_trend():
    pitcher = {
        "pitcher": "Test Arm",
        "team": "NYY",
        "state": "STABLE",
        "projection_trust": "trusted",
        "sample": {"season_starts": 12},
        "projections": {
            "Fantasy": {"mean": 28.0, "p10": 20.0, "p90": 36.0},
            "K": {"mean": 7.5, "p10": 4.0, "p90": 10.0},
        },
    }
    trends = detect_pitcher_prop_trends(pitcher)
    cats = {t.category for t in trends}
    assert "fantasy_dk" in cats
    assert "prop_strikeouts" in cats


def test_sample_chip_color_coded():
    out = _sample_chip(18)
    assert "chip" in out
    assert "18" in out


def test_trends_section_matchup_first():
    trend = type(
        "Trend",
        (),
        {
            "team": "NYY",
            "category": "fantasy_dk",
            "trend_description": "Cole projects 28 DK fantasy vs 18 starter prior (1.7σ).",
            "effect_size": 1.4,
            "trend_score": 0.8,
            "sample_size": 18,
            "confidence": "high",
            "significance": "strong",
            "direction": "run_boost",
            "betting_implications": ["Cole DK fantasy OVER"],
            "mechanistic_explanation": "Simulation blends skill and lineup.",
        },
    )()
    report = type(
        "Report",
        (),
        {
            "game": "NYY@BOS",
            "away": "NYY",
            "home": "BOS",
            "away_edge_score": 44.0,
            "home_edge_score": 58.0,
            "edge_lean": "BOS",
            "trends": [trend],
        },
    )()
    panel = trends_section_html([report])
    assert "trendGameSelect" in panel
    assert "trend-matchup-panel" in panel
    assert 'trend-matchup-panel" data-game="NYY@BOS">' in panel
    assert "data-trend-filter" not in panel
    assert "Props · Fantasy · Markets" not in panel
    assert "Fantasy" in panel
    assert 'data-lane="fantasy"' in panel
