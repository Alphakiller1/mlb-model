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
