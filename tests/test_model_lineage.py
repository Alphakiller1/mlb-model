from mlbmodel.baseball.model import GameData, model_probabilities


def test_probability_reports_only_actual_model_factors():
    game = GameData(
        game_pk=1,
        game_date="2026-06-27",
        start_time="7:10 PM ET",
        away="NYY",
        home="BOS",
        away_sp="A",
        home_sp="B",
        away_hand="R",
        home_hand="L",
        away_osi=55,
        home_osi=50,
        away_fip=3.8,
        home_fip=4.2,
        away_hr9=1.0,
        home_hr9=1.1,
        away_k=25,
        home_k=22,
        park_factor=1.12,
    )
    probabilities = model_probabilities(
        game,
        {
            "league_runs": 4.5,
            "margin_sd": 4.4,
            "home_winp": 0.54,
            "away_winp": 0.46,
        },
    )
    names = {factor.name for factor in probabilities.factors}
    assert names == {
        "NYY season offense",
        "BOS season offense",
        "BOS starter and bullpen",
        "NYY starter and bullpen",
        "Ballpark run environment",
        "Home field",
    }
    assert not any(
        term in name
        for name in names
        for term in ("lineup", "weather", "umpire", "travel")
    )
