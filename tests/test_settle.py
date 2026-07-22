from mlbmodel.market.settle import _prediction_filter, grade, grade_model_prediction


GAME = {"home_team": "BOS", "away_team": "NYY"}
OUTCOME = {
    "home_runs": 5,
    "away_runs": 2,
    "total_runs": 7,
    "margin_home": 3,
    "winner_team": "BOS",
}


def test_sharp_moneyline_grades_against_winner():
    won, push = grade(
        {"market_type": "ml", "selection": "BOS"},
        GAME,
        OUTCOME,
    )

    assert won is True
    assert push is False


def test_model_prediction_grades_explicit_winner():
    won, push = grade_model_prediction(
        {"predicted_winner": "BOS"},
        GAME,
        OUTCOME,
    )

    assert won is True
    assert push is False


def test_model_prediction_derives_winner_when_outcome_has_scores_only():
    won, push = grade_model_prediction(
        {"predicted_winner": "BOS"},
        GAME,
        {"home_score": 5, "away_score": 2},
    )

    assert won is True
    assert push is False


def test_model_prediction_grades_probability_side():
    won, push = grade_model_prediction(
        {"home_win_probability": 0.42},
        GAME,
        OUTCOME,
    )

    assert won is False
    assert push is False


def test_model_prediction_grades_total_market():
    won, push = grade_model_prediction(
        {"market_type": "total", "selection": "over", "line": 6.5},
        GAME,
        OUTCOME,
    )

    assert won is True
    assert push is False


def test_model_prediction_grades_team_total_market():
    won, push = grade_model_prediction(
        {"market_type": "team_total", "selection": "BOS_over", "line": 4.5},
        GAME,
        OUTCOME,
    )

    assert won is True
    assert push is False


def test_model_prediction_grades_runline_market():
    won, push = grade_model_prediction(
        {"market_type": "runline", "selection": "NYY", "line": 1.5},
        GAME,
        OUTCOME,
    )

    assert won is False
    assert push is False


def test_model_prediction_pushes_on_exact_total_line():
    won, push = grade_model_prediction(
        {"market": "total", "direction": "under", "line": 7},
        GAME,
        OUTCOME,
    )

    assert won is None
    assert push is True


def test_model_prediction_grades_f5_only_with_f5_outcome_fields():
    won, push = grade_model_prediction(
        {"market_type": "f5_total", "selection": "under", "line": 3.5},
        GAME,
        OUTCOME,
    )

    assert won is None
    assert push is None

    won, push = grade_model_prediction(
        {"market_type": "f5_total", "selection": "under", "line": 3.5},
        GAME,
        {**OUTCOME, "f5_home_runs": 2, "f5_away_runs": 1},
    )

    assert won is True
    assert push is False


def test_model_prediction_grades_player_prop_with_matched_outcome():
    won, push = grade_model_prediction(
        {
            "market_type": "pitcher_strikeouts",
            "player": "Away Starter",
            "selection": "over",
            "line": 5.5,
        },
        GAME,
        OUTCOME,
        {"player_name": "Away Starter", "stat_key": "K", "value": 7},
    )

    assert won is True
    assert push is False


def test_model_prediction_player_prop_pushes_exact_line():
    won, push = grade_model_prediction(
        {
            "market_type": "player_prop",
            "prop": "Outs",
            "player_id": 42,
            "direction": "under",
            "line": 17,
        },
        GAME,
        OUTCOME,
        {"player_id": 42, "stat_key": "Outs", "value": 17},
    )

    assert won is None
    assert push is True


def test_model_prediction_player_prop_requires_matched_outcome():
    won, push = grade_model_prediction(
        {
            "market_type": "pitcher_walks",
            "player": "Away Starter",
            "selection": "under",
            "line": 2.5,
        },
        GAME,
        OUTCOME,
        {"player_name": "Other Starter", "stat_key": "BB", "value": 1},
    )

    assert won is None
    assert push is None


def test_model_prediction_does_not_guess_without_side():
    won, push = grade_model_prediction(
        {"verdict": "PASS"},
        GAME,
        OUTCOME,
    )

    assert won is None
    assert push is None


def test_prediction_filter_requires_unique_prediction_id():
    assert _prediction_filter({"game_pk": 123}) is None
    assert _prediction_filter({"prediction_id": "abc", "game_pk": 123}) == "prediction_id=eq.abc"
