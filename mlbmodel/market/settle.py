"""Settle market observations and model predictions against final MLB outcomes."""
from __future__ import annotations

import datetime as dt

from mlbmodel.storage.supabase import SupabaseReader, SupabaseWriter


def grade(observation: dict, game: dict, outcome: dict) -> tuple[bool | None, bool | None]:
    market = observation["market_type"]
    selection = observation["selection"]
    line = observation.get("line")
    home = game["home_team"]
    home_runs, away_runs = outcome["home_runs"], outcome["away_runs"]
    total, margin = outcome["total_runs"], outcome["margin_home"]
    winner = outcome["winner_team"]
    if market == "ml":
        return winner == selection, False
    if market == "total" and line is not None:
        if total == line:
            return None, True
        return (total > line if selection == "over" else total < line), False
    if market == "team_total" and line is not None:
        team, _, direction = selection.partition("_")
        runs = home_runs if team == home else away_runs
        if runs == line:
            return None, True
        return (runs > line if direction == "over" else runs < line), False
    if market == "runline":
        team_margin = margin if selection == home else -margin
        runline = -1.5 if observation.get("side_role") == "fav" else 1.5
        return team_margin + runline > 0, False
    return None, None


def _first(row: dict, *names: str):
    for name in names:
        if name in row and row.get(name) is not None:
            return row.get(name)
    return None


def _team_pick(prediction: dict, game: dict) -> str | None:
    """Return the predicted winning team when the row publishes enough information.

    Existing `model_predictions` rows have not had a single documented shape. This accepts
    explicit team-pick columns first, then falls back to home/away win probabilities. Rows
    without a team side remain ungraded; the settle loop must never guess.
    """
    home, away = game["home_team"], game["away_team"]
    raw = _first(
        prediction,
        "predicted_winner",
        "selection",
        "team",
        "side",
        "pick",
        "model_pick",
    )
    if raw is not None:
        value = str(raw).upper().strip()
        if value == "HOME":
            return home
        if value == "AWAY":
            return away
        if value in {home, away}:
            return value

    home_prob = _first(
        prediction,
        "home_win_probability",
        "p_home_win",
        "home_probability",
        "model_home_probability",
    )
    away_prob = _first(
        prediction,
        "away_win_probability",
        "p_away_win",
        "away_probability",
        "model_away_probability",
    )
    try:
        if home_prob is not None:
            return home if float(home_prob) >= 0.5 else away
        if away_prob is not None:
            return away if float(away_prob) >= 0.5 else home
    except (TypeError, ValueError):
        return None
    return None


def grade_model_prediction(
    prediction: dict,
    game: dict,
    outcome: dict,
) -> tuple[bool | None, bool | None]:
    selection = _team_pick(prediction, game)
    if selection is None:
        return None, None
    return outcome["winner_team"] == selection, False


def _prediction_filter(prediction: dict) -> str | None:
    for key in ("prediction_id", "id"):
        if prediction.get(key) is not None:
            return f"{key}=eq.{prediction[key]}"
    return None


def run() -> int:
    reader, writer = SupabaseReader(), SupabaseWriter()
    games_result = reader.get("games?select=game_pk,home_team,away_team")
    outcomes_result = reader.get(
        "game_outcomes?select=game_pk,home_runs,away_runs,total_runs,"
        "margin_home,winner_team"
    )
    observations_result = reader.get(
        "sharp_observations?settled=eq.false&select=obs_id,game_pk,market_type,"
        "selection,line,side_role"
    )
    predictions_result = reader.get("model_predictions?settled=eq.false&select=*&limit=1000")
    if predictions_result.error:
        # Backward-compatible fallback for warehouses before migration 0003. Applying the
        # migration is still required before model-prediction updates can persist.
        predictions_result = reader.get("model_predictions?select=*&limit=1000")
    errors = [
        result.error
        for result in (games_result, outcomes_result, observations_result, predictions_result)
        if result.error
    ]
    if errors:
        raise RuntimeError("; ".join(errors))
    games = {row["game_pk"]: row for row in games_result.rows}
    outcomes = {row["game_pk"]: row for row in outcomes_result.rows}
    settled = 0
    for observation in observations_result.rows:
        game_pk = observation["game_pk"]
        if game_pk not in games or game_pk not in outcomes:
            continue
        won, push = grade(observation, games[game_pk], outcomes[game_pk])
        if won is None and not push:
            continue
        writer.update(
            "sharp_observations",
            f"obs_id=eq.{observation['obs_id']}",
            {"settled": True, "won": won, "push": bool(push)},
        )
        settled += 1
    for prediction in predictions_result.rows:
        if prediction.get("settled"):
            continue
        try:
            game_pk = int(prediction.get("game_pk"))
        except (TypeError, ValueError):
            continue
        if game_pk not in games or game_pk not in outcomes:
            continue
        won, push = grade_model_prediction(prediction, games[game_pk], outcomes[game_pk])
        if won is None and not push:
            continue
        filters = _prediction_filter(prediction)
        if not filters:
            continue
        outcome = outcomes[game_pk]
        writer.update(
            "model_predictions",
            filters,
            {
                "settled": True,
                "won": won,
                "push": bool(push),
                "settled_time": dt.datetime.now(dt.UTC).isoformat(),
                "actual_winner": outcome["winner_team"],
                "actual_home_runs": outcome["home_runs"],
                "actual_away_runs": outcome["away_runs"],
                "actual_total_runs": outcome["total_runs"],
                "actual_margin_home": outcome["margin_home"],
            },
        )
        settled += 1
    return settled


def main() -> None:
    print(f"settled records={run()}")


if __name__ == "__main__":
    main()
