from mlbmodel.report.props_ui import play_lean_html


def test_play_lean_html_names_stat_and_direction():
    html = play_lean_html("over", "K", 5.5, edge=0.04, source="Underdog")
    assert "OVER" in html
    assert "5.5" in html
    assert "Strikeouts" in html or "K" in html
    assert "+4.0pt" in html
    assert "Underdog" in html
