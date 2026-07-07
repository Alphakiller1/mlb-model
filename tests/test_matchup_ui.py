import html

from mlbmodel.report.matchup_ui import (
    _short_factor,
    _short_markets,
    league_avg_html,
    run_impacts_html,
)


def test_league_avg_html_yellow_class():
    assert 'class="league-avg"' in league_avg_html(4.25)
    assert "4.25" in league_avg_html(4.25)


def test_short_factor_trims_team_prefix():
    text = "NYY season offense"
    assert "season offense" in _short_factor(text).lower()


def test_short_markets_readable():
    assert "·" in _short_markets("Away runs / Total / ML")


def test_run_impacts_no_trust_column():
    panel = run_impacts_html(
        [{"name": "NYY season offense", "runs": 0.42, "side": "NYY", "market": "Total · ML"}],
        html.escape,
    )
    assert "Trust" not in panel
    assert "Impact" in panel
    assert "+0.42" in panel
