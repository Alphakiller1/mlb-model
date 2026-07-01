from mlbmodel.baseball.model import GameData, arsenal_factor, model_probabilities

ANCHORS = {"league_runs": 4.5, "margin_sd": 4.4, "home_winp": 0.54, "away_winp": 0.46}


def _game(**overrides):
    base = dict(
        game_pk=1,
        game_date="2026-06-27",
        start_time="7:10 PM ET",
        away="NYY",
        home="BOS",
        away_sp="Cole",
        home_sp="Bello",
        away_hand="R",
        home_hand="R",
        away_osi=50,
        home_osi=50,
        away_fip=4.2,
        home_fip=4.2,
        away_hr9=1.1,
        home_hr9=1.1,
        away_k=22,
        home_k=22,
        park_factor=1.0,
    )
    base.update(overrides)
    return GameData(**base)


def test_arsenal_factor_regresses_and_clips():
    # er_factor below the clip floor is bounded to it, then regressed 25% toward 1.0.
    assert arsenal_factor({"er_factor": 0.90}) == 1 + (0.95 - 1) * 0.75
    # A neutral/absent response is a no-op.
    assert arsenal_factor({}) == 1.0
    assert arsenal_factor({"er_factor": None}) == 1.0


def test_arsenal_suppresses_opposing_runs_and_is_attributed():
    baseline = model_probabilities(_game(), ANCHORS)
    # Home starter (Bello) has a strong arsenal vs the away (NYY) lineup -> fewer NYY runs.
    with_arsenal = model_probabilities(
        _game(away_arsenal_features={"er_factor": 0.94, "coverage_pct": 80}), ANCHORS
    )
    assert with_arsenal.exp_away_runs < baseline.exp_away_runs
    assert with_arsenal.exp_home_runs == baseline.exp_home_runs
    names = {f.name for f in with_arsenal.factors}
    assert "Bello arsenal vs NYY lineup" in names


def test_arsenal_absent_leaves_lineage_unchanged():
    names = {f.name for f in model_probabilities(_game(), ANCHORS).factors}
    assert not any("arsenal" in name for name in names)
