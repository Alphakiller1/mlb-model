"""Settle sharp observations against final MLB outcomes through Supabase REST."""
from __future__ import annotations

import logging

from mlbmodel.storage.supabase import SupabaseReader, SupabaseWriter

log = logging.getLogger(__name__)


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
    errors = [
        result.error
        for result in (games_result, outcomes_result, observations_result)
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
    return settled


def run_all() -> tuple[int, int]:
    """Settle sharp observations and model leans."""
    sharp_settled = run()
    try:
        from mlbmodel.leans.grade import settle_leans

        lean_settled = settle_leans(reader=SupabaseReader(), writer=SupabaseWriter())
    except Exception as exc:
        log.warning("model lean settlement failed: %s", exc)
        lean_settled = 0
    return sharp_settled, lean_settled


def main() -> None:
    sharp, leans = run_all()
    print(f"settled sharp observations={sharp} model_leans={leans}")


if __name__ == "__main__":
    main()
