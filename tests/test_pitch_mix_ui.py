from mlbmodel.report.pitch_mix_ui import (
    pitch_k_delta_html,
    pitch_mix_board_html,
    pitch_mix_net_html,
    pitch_run_pct_html,
)


def test_pitch_k_delta_colors_positive_and_negative():
    assert "c-good" in pitch_k_delta_html(0.55)
    assert "c-poor" in pitch_k_delta_html(-0.55)


def test_pitch_run_pct_negative_is_pitcher_favorable():
    assert "c-good" in pitch_run_pct_html(-1.0)
    assert "c-poor" in pitch_run_pct_html(1.2)


def test_pitch_mix_board_shows_net_drivers_and_legend():
    html = pitch_mix_board_html({
        "k_rate_delta": 1.1,
        "er_factor": 0.94,
        "verdict": "pitcher edge",
        "coverage_pct": 72,
        "lineup_batters_matched": 8,
        "response_source": "posted lineup, batting-order weighted",
        "pitches": [{
            "pitch": "Slider",
            "usage_pct": 31.0,
            "lineup_xwoba": 0.300,
            "lineup_whiff_pct": 29.0,
            "k_delta": 0.62,
            "er_factor_delta": -0.04,
            "edge": "pitcher edge",
        }],
    })
    assert "Net vs lineup" in html
    assert "Pitch-type drivers" in html
    assert "Δ K%" in html
    assert "Δ runs" in html
    assert "pitcher edge" not in html.lower() or "Pitcher" in html
    assert pitch_mix_net_html({}) == ""
