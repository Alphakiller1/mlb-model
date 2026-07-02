from mlbmodel.baseball.model import GameData, model_probabilities
from mlbmodel.sources import live_context


ANCHORS = {
    "league_runs": 4.5,
    "margin_sd": 4.4,
    "home_winp": 0.54,
    "away_winp": 0.46,
}


def test_context_inputs_are_actual_run_factors():
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
        park_factor=1.02,
        weather={
            "status": "forecast",
            "temp_f": 88.0,
            "wind_out_mph": 12.0,
            "humidity_pct": 60.0,
            "pressure_hpa": 1008.0,
        },
        live_context={
            "travel": {
                "away": {
                    "status": "available",
                    "rest_hours": 17.0,
                    "travel_miles": 1200.0,
                    "timezone_shift_hours": 1.0,
                    "games_last_7_days": 7,
                },
                "home": {"status": "no_recent_game"},
            },
            "umpire": {
                "status": "announced",
                "profile": {"run_factor": 1.03},
            },
        },
        away_starter_features={"skill_fip": 3.5, "expected_ip": 6.1, "starts": 12},
        home_starter_features={"skill_fip": 4.5, "expected_ip": 5.0, "starts": 10},
        away_bullpen_features={"skill_fip": 3.7, "workload_factor": 1.0},
        home_bullpen_features={"skill_fip": 4.6, "workload_factor": 1.03},
        away_lineup_features={"status": "confirmed", "factor": 1.06},
        home_lineup_features={"status": "confirmed", "factor": 0.96},
        away_injury_features={"factor": 1.0},
        home_injury_features={"factor": 0.98},
        context_coverage_pct=100,
    )

    probabilities = model_probabilities(game, ANCHORS)
    factors = {factor.name: factor for factor in probabilities.factors}

    assert factors["NYY posted lineup vs LHP"].run_delta > 0
    assert factors["BOS posted lineup vs RHP"].run_delta < 0
    assert factors["NYY rest and travel"].run_delta < 0
    assert factors["First-pitch weather"].run_delta > 0
    assert factors["Home-plate umpire run environment"].run_delta > 0
    assert probabilities.data_coverage_pct == 100
    assert probabilities.confidence == "high"


def test_official_injury_filter_uses_supported_roster_status(monkeypatch):
    monkeypatch.setattr(
        live_context,
        "_request_json",
        lambda _url: {
            "roster": [
                {
                    "person": {"id": 1, "fullName": "Impact Bat"},
                    "position": {"abbreviation": "RF"},
                    "status": {"code": "D10", "description": "Injured 10-Day"},
                    "note": "Hamstring strain",
                },
                {
                    "person": {"id": 2, "fullName": "Minor Leaguer"},
                    "position": {"abbreviation": "P"},
                    "status": {"code": "RM", "description": "Reassigned"},
                },
            ]
        },
    )

    injuries = live_context._injuries(147)

    assert injuries == [{
        "player_id": 1,
        "player": "Impact Bat",
        "position": "RF",
        "status_code": "D10",
        "status": "Injured 10-Day",
        "injury": "Hamstring strain",
    }]
