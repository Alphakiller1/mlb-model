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


def _number(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _prediction_market(prediction: dict) -> str | None:
    raw = _first(
        prediction,
        "market_type",
        "market",
        "bet_type",
        "prediction_market",
        "prop_market",
        "prop",
        "stat_key",
    )
    if raw is None:
        return None
    value = str(raw).lower().strip().replace(" ", "_").replace("-", "_")
    if value in {"h2h", "moneyline", "ml"}:
        return "ml"
    if value in {"total", "totals", "game_total", "full_game_total"}:
        return "total"
    if value in {"team_total", "team_totals"}:
        return "team_total"
    if value in {"runline", "run_line", "spread", "spreads"}:
        return "runline"
    if value in {"f5_ml", "f5_moneyline", "first_5_moneyline", "h2h_1st_5_innings"}:
        return "f5_ml"
    if value in {"f5_total", "first_5_total", "totals_1st_5_innings"}:
        return "f5_total"
    if value in {"f5_runline", "f5_spread", "spreads_1st_5_innings"}:
        return "f5_runline"
    return value


def _direction_pick(prediction: dict) -> str | None:
    raw = _first(
        prediction,
        "direction",
        "total_side",
        "side",
        "selection",
        "pick",
        "model_pick",
    )
    if raw is None:
        return None
    value = str(raw).lower().strip()
    if "over" in value:
        return "over"
    if "under" in value:
        return "under"
    return None


def _line_value(prediction: dict) -> float | None:
    return _number(
        _first(
            prediction,
            "line",
            "total_line",
            "runline",
            "run_line",
            "spread",
            "handicap",
            "point",
            "threshold",
        )
    )


def _team_from_prediction(prediction: dict, game: dict) -> str | None:
    home, away = game["home_team"], game["away_team"]
    raw = _first(prediction, "team", "selection", "side", "pick", "model_pick")
    if raw is not None:
        value = str(raw).upper().strip()
        if "_" in value:
            value = value.split("_", 1)[0]
        if value == "HOME":
            return home
        if value == "AWAY":
            return away
        if value in {home, away}:
            return value
    return None


def _norm_text(value) -> str:
    return " ".join(str(value or "").lower().replace(".", "").split())


def _player_id(prediction: dict):
    return _first(prediction, "player_id", "pitcher_id", "mlb_player_id")


def _player_name(prediction: dict) -> str | None:
    raw = _first(
        prediction,
        "player",
        "player_name",
        "pitcher",
        "description",
        "athlete",
    )
    return str(raw).strip() if raw is not None and str(raw).strip() else None


def _prop_stat_key(prediction: dict, market: str | None) -> str | None:
    raw = _first(prediction, "stat_key", "prop", "prop_type", "market_key") or market
    if raw is None:
        return None
    value = str(raw).lower().strip().replace(" ", "_").replace("-", "_")
    if value in {"k", "ks", "so", "strikeout", "strikeouts", "pitcher_strikeouts"}:
        return "K"
    if value in {"bb", "bbs", "walk", "walks", "pitcher_walks"}:
        return "BB"
    if value in {"er", "earned_run", "earned_runs", "pitcher_earned_runs"}:
        return "ER"
    if value in {"out", "outs", "pitching_outs", "pitcher_outs"}:
        return "Outs"
    return None


def _prop_actual_value(player_outcome: dict | None, stat_key: str | None) -> float | None:
    if not player_outcome or not stat_key:
        return None
    stat = str(_first(player_outcome, "stat_key", "prop", "prop_type") or "").strip()
    if stat and _prop_stat_key({"stat_key": stat}, stat) != stat_key:
        return None
    aliases = {
        "K": ("value", "actual_value", "strikeouts", "k", "so"),
        "BB": ("value", "actual_value", "walks", "bb"),
        "ER": ("value", "actual_value", "earned_runs", "er"),
        "Outs": ("value", "actual_value", "outs", "pitching_outs"),
    }
    return _number(_first(player_outcome, *aliases[stat_key]))


def _matched_player_outcome(prediction: dict, rows: list[dict]) -> dict | None:
    stat_key = _prop_stat_key(prediction, _prediction_market(prediction))
    if not stat_key:
        return None
    pred_id = _player_id(prediction)
    pred_name = _player_name(prediction)
    if pred_id is not None:
        for row in rows:
            row_id = _first(row, "player_id", "pitcher_id", "mlb_player_id")
            if row_id is not None and str(row_id) == str(pred_id):
                if _prop_actual_value(row, stat_key) is not None:
                    return row
    name_key = _norm_text(pred_name)
    if name_key:
        for row in rows:
            row_name = _first(row, "player", "player_name", "pitcher", "description")
            if _norm_text(row_name) == name_key and _prop_actual_value(row, stat_key) is not None:
                return row
    return None


def _player_outcome_matches(prediction: dict, player_outcome: dict | None) -> bool:
    if not player_outcome:
        return False
    pred_id = _player_id(prediction)
    row_id = _first(player_outcome, "player_id", "pitcher_id", "mlb_player_id")
    if pred_id is not None:
        return row_id is not None and str(row_id) == str(pred_id)
    pred_name = _player_name(prediction)
    row_name = _first(player_outcome, "player", "player_name", "pitcher", "description")
    return bool(pred_name and row_name and _norm_text(pred_name) == _norm_text(row_name))


def _period_outcome(
    market: str,
    outcome: dict,
) -> tuple[float | None, float | None, float | None] | None:
    if market.startswith("f5_"):
        home_runs = _number(_first(outcome, "f5_home_runs", "home_f5_runs", "first5_home_runs"))
        away_runs = _number(_first(outcome, "f5_away_runs", "away_f5_runs", "first5_away_runs"))
        if home_runs is None or away_runs is None:
            return None
        return home_runs, away_runs, home_runs - away_runs
    home_runs = _number(_first(outcome, "home_runs", "home_score", "home_final"))
    away_runs = _number(_first(outcome, "away_runs", "away_score", "away_final"))
    if home_runs is None or away_runs is None:
        return None
    margin_home = _number(_first(outcome, "margin_home"))
    if margin_home is None:
        margin_home = home_runs - away_runs
    return home_runs, away_runs, margin_home


def _winner_from_outcome(game: dict, outcome: dict, margin_home: float | None = None) -> str | None:
    raw = _first(outcome, "winner_team", "winner")
    if raw is not None:
        value = str(raw).upper().strip()
        if value in {game["home_team"], game["away_team"]}:
            return value
    if margin_home is None:
        period = _period_outcome("ml", outcome)
        if period is None:
            return None
        _home_runs, _away_runs, margin_home = period
    if margin_home > 0:
        return game["home_team"]
    if margin_home < 0:
        return game["away_team"]
    return None


def grade_model_prediction(
    prediction: dict,
    game: dict,
    outcome: dict,
    player_outcome: dict | None = None,
) -> tuple[bool | None, bool | None]:
    market = _prediction_market(prediction)
    if market is None:
        selection = _team_pick(prediction, game)
        if selection is None:
            return None, None
        winner = _winner_from_outcome(game, outcome)
        if winner is None:
            return None, None
        return winner == selection, False

    prop_stat = _prop_stat_key(prediction, market)
    if prop_stat:
        if not _player_outcome_matches(prediction, player_outcome):
            return None, None
        line = _line_value(prediction)
        direction = _direction_pick(prediction)
        actual = _prop_actual_value(player_outcome, prop_stat)
        if line is None or direction is None or actual is None:
            return None, None
        if actual == line:
            return None, True
        return (actual > line if direction == "over" else actual < line), False

    period = _period_outcome(market, outcome)
    if period is None:
        return None, None
    home_runs, away_runs, margin_home = period
    total_runs = home_runs + away_runs

    if market in {"ml", "f5_ml"}:
        selection = _team_pick(prediction, game)
        if selection is None:
            return None, None
        winner = _winner_from_outcome(game, outcome, margin_home)
        if winner is None:
            return None, True
        return winner == selection, False

    if market in {"total", "f5_total"}:
        line = _line_value(prediction)
        direction = _direction_pick(prediction)
        if line is None or direction is None:
            return None, None
        if total_runs == line:
            return None, True
        return (total_runs > line if direction == "over" else total_runs < line), False

    if market == "team_total":
        line = _line_value(prediction)
        direction = _direction_pick(prediction)
        team = _team_from_prediction(prediction, game)
        if line is None or direction is None or team is None:
            return None, None
        runs = home_runs if team == game["home_team"] else away_runs
        if runs == line:
            return None, True
        return (runs > line if direction == "over" else runs < line), False

    if market in {"runline", "f5_runline"}:
        team = _team_from_prediction(prediction, game)
        line = _line_value(prediction)
        if team is None:
            return None, None
        if line is None:
            side_role = str(prediction.get("side_role") or "").lower()
            if side_role in {"fav", "favorite"}:
                line = -1.5
            elif side_role in {"dog", "underdog"}:
                line = 1.5
            else:
                return None, None
        team_margin = margin_home if team == game["home_team"] else -margin_home
        graded_margin = team_margin + line
        if graded_margin == 0:
            return None, True
        return graded_margin > 0, False

    return None, None


def _prediction_filter(prediction: dict) -> str | None:
    for key in ("prediction_id", "id"):
        if prediction.get(key) is not None:
            return f"{key}=eq.{prediction[key]}"
    return None


def run() -> int:
    reader, writer = SupabaseReader(), SupabaseWriter()
    games_result = reader.get("games?select=game_pk,home_team,away_team")
    outcomes_result = reader.get("game_outcomes?select=*")
    observations_result = reader.get(
        "sharp_observations?settled=eq.false&select=obs_id,game_pk,market_type,"
        "selection,line,side_role"
    )
    predictions_result = reader.get("model_predictions?settled=eq.false&select=*&limit=1000")
    prop_outcomes_result = reader.get("player_prop_outcomes?select=*")
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
    prop_outcomes_by_game: dict[int, list[dict]] = {}
    if not prop_outcomes_result.error:
        for row in prop_outcomes_result.rows:
            try:
                row_game_pk = int(row.get("game_pk"))
            except (TypeError, ValueError):
                continue
            prop_outcomes_by_game.setdefault(row_game_pk, []).append(row)
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
        player_outcome = _matched_player_outcome(
            prediction,
            prop_outcomes_by_game.get(game_pk, []),
        )
        won, push = grade_model_prediction(
            prediction,
            games[game_pk],
            outcomes[game_pk],
            player_outcome,
        )
        if won is None and not push:
            continue
        filters = _prediction_filter(prediction)
        if not filters:
            continue
        outcome = outcomes[game_pk]
        actual_home_runs = _number(_first(outcome, "home_runs", "home_score", "home_final"))
        actual_away_runs = _number(_first(outcome, "away_runs", "away_score", "away_final"))
        actual_margin_home = _number(_first(outcome, "margin_home"))
        if actual_home_runs is not None and actual_away_runs is not None:
            if actual_margin_home is None:
                actual_margin_home = actual_home_runs - actual_away_runs
            actual_total_runs = _number(_first(outcome, "total_runs"))
            if actual_total_runs is None:
                actual_total_runs = actual_home_runs + actual_away_runs
        else:
            actual_total_runs = _number(_first(outcome, "total_runs"))
        actual_winner = _winner_from_outcome(games[game_pk], outcome, actual_margin_home)
        updates = {
            "settled": True,
            "won": won,
            "push": bool(push),
            "settled_time": dt.datetime.now(dt.UTC).isoformat(),
            "actual_winner": actual_winner,
            "actual_home_runs": actual_home_runs,
            "actual_away_runs": actual_away_runs,
            "actual_total_runs": actual_total_runs,
            "actual_margin_home": actual_margin_home,
        }
        prop_stat = _prop_stat_key(prediction, _prediction_market(prediction))
        actual_prop = _prop_actual_value(player_outcome, prop_stat)
        if prop_stat and player_outcome and actual_prop is not None:
            updates.update(
                {
                    "actual_player_name": _first(
                        player_outcome,
                        "player",
                        "player_name",
                        "pitcher",
                        "description",
                    ),
                    "actual_prop_stat": prop_stat,
                    "actual_prop_value": actual_prop,
                }
            )
        writer.update(
            "model_predictions",
            filters,
            updates,
        )
        settled += 1
    return settled


def main() -> None:
    print(f"settled records={run()}")


if __name__ == "__main__":
    main()
