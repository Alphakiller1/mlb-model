import pandas as pd

from mlbmodel.local_grading import grade_pending, record_run


def test_local_ledger_records_and_grades_game_and_pitcher_prop(tmp_path):
    pd.DataFrame([
        {"game_date": "2026-08-01", "home_away": "home", "team": "BOS", "opp": "NYY", "team_runs": 5, "opp_runs": 3},
        {"game_date": "2026-08-01", "home_away": "away", "team": "NYY", "opp": "BOS", "team_runs": 3, "opp_runs": 5},
    ]).to_csv(tmp_path / "game_results.csv", index=False)
    pd.DataFrame([{"date": "2026-08-01", "pitcher_name": "Test Pitcher", "K": 7, "BB": 2, "ER": 3, "IP": 6, "f5_er": 1}]).to_csv(tmp_path / "sp_game_log.csv", index=False)
    written = record_run(tmp_path, "2026-08-01", {9: [{"market": "ml", "side": "BOS", "model": 60, "mkt": -120}]}, {9: "NYY@BOS"}, [{"game_pk": 9, "pitcher": "Test Pitcher", "prop": "K", "side": "over", "line": 5.5, "model_mean": 6.2}])
    result = grade_pending(tmp_path)
    assert written == 2
    assert result["graded"] == 2
    ledger = pd.read_csv(tmp_path / "prediction_ledger.csv")
    assert ledger["won"].tolist() == [True, True]
