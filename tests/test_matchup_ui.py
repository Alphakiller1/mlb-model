import html

from mlbmodel.report.matchup_ui import (
    _short_factor,
    _short_markets,
    advantage_panel_html,
    impact_runs_html,
    league_avg_html,
    matchup_banner_html,
    matchup_context_html,
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
    assert "+0.42 R" in panel
    assert 'class="chip' in panel


def test_impact_runs_html_signed_chip():
    pos = impact_runs_html(0.42)
    neg = impact_runs_html(-0.63)
    assert "chip" in pos and "chip" in neg
    assert "+0.42 R" in pos
    assert "-0.63 R" in neg
    assert "c-good" in pos or "c-elite" in pos
    assert "c-weak" in neg or "c-poor" in neg
    assert "c-mid" not in pos
    assert "c-mid" not in neg


def test_matchup_breakdown_pitcher_rl_populated():
    from mlbmodel.report.matchup_ui import _pitcher_rl_rows, _sp_metric_split

    class Repo:
        def load(self, name):
            import pandas as pd
            if name != "sp_metric_splits.csv":
                return None
            return pd.read_csv("deployment_data/sp_metric_splits.csv")

    splits = _sp_metric_split(Repo(), "Tarik Skubal", "hand")
    assert "LHH" in splits and "RHH" in splits
    rows = _pitcher_rl_rows(splits)
    assert "c-na" not in rows or rows.count("c-na") < 4
    assert "30.3" in rows or "30.5" in rows


def test_matchup_breakdown_symmetric_columns():
    gd = type("GD", (), {
        "away": "NYY", "home": "BOS",
        "away_sp": "Cole", "home_sp": "Bello",
        "away_pen_factor": 1.02, "home_pen_factor": 0.98,
        "away_bullpen_features": {"pitches_1d": 42},
        "home_bullpen_features": {"pitches_1d": 38},
    })()
    report = {"pitchers": []}

    class Repo:
        def load(self, name):
            return None

    panel = matchup_context_html(report, gd, Repo(), html.escape)
    assert "Matchup breakdown" in panel
    assert "matchup-breakdown-sym" in panel
    assert panel.count("matchup-breakdown__lane--away") >= 6
    assert panel.count("matchup-breakdown__lane--home") >= 6
    assert panel.count("matchup-breakdown__spine") >= 6
    assert "vs BOS" in panel
    assert "vs NYY" in panel
    assert "Pitcher R/L splits" not in panel


def test_matchup_banner_symmetric_no_duplicate_fg():
    gd = type("GD", (), {
        "away": "NYY", "home": "BOS",
        "away_sp": "Cole", "home_sp": "Bello",
        "away_k": 28.5, "home_k": 22.0,
        "away_hand": "R", "home_hand": "R",
        "start_time": "7:10 PM ET",
        "live_context": {"weather": {"temp_f": 72, "wind_out_mph": 8}},
    })()
    prob = type("Prob", (), {"exp_away_runs": 4.5, "exp_home_runs": 3.8, "exp_total": 8.3, "exp_margin": 0.7})()
    report = {
        "gd": gd,
        "probs": prob,
        "extras": {"start": "7:10 PM ET", "a_id": 1, "h_id": 2},
        "pitchers": [],
    }
    panel = matchup_banner_html(report, html.escape)
    assert "matchup-banner__hero" in panel
    assert panel.count("Projected score") == 1
    assert ">Full game<" not in panel
    assert "matchup-banner__pitchers" not in panel
    assert "First 5" in panel


def test_advantage_panel_color_coded():
    gd = type("GD", (), {"away": "NYY", "home": "BOS"})()
    rows = [{
        "cat": "Offense (OSI)",
        "a_val": 58.0,
        "h_val": 44.0,
        "base": 50.0,
        "a_pct": 72.0,
        "h_pct": 28.0,
        "edge": "NYY",
        "unit": "",
        "lower_better": False,
    }]
    panel = advantage_panel_html(gd, rows, html.escape)
    assert 'class="chip' in panel
    assert "adv-edge-win" in panel
    assert "NYY" in panel
    assert "league-avg" in panel
