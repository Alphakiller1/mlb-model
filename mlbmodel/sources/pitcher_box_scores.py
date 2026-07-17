"""Fetch final-game pitcher box scores from the MLB Stats API for lean settlement."""
from __future__ import annotations

import json
import urllib.request
from functools import lru_cache

from mlbmodel.baseball.features import normalize_name

_UA = "mlb-model/1.0"


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode())


def _pitcher_stats_from_player(player: dict) -> dict | None:
    pitching = (player.get("stats") or {}).get("pitching") or {}
    if not pitching:
        return None
    innings = str(pitching.get("inningsPitched") or "0")
    outs = 0
    if "." in innings:
        whole, frac = innings.split(".", 1)
        outs = int(whole or 0) * 3 + int(frac or 0)
    else:
        outs = int(innings or 0) * 3
    return {
        "strikeouts": pitching.get("strikeOuts"),
        "walks": pitching.get("baseOnBalls"),
        "earned_runs": pitching.get("earnedRuns"),
        "outs": outs,
        "hits": pitching.get("hits"),
        "innings": innings,
        # Decision + fantasy-score inputs (game-level 0/1 counts in the box).
        "wins": pitching.get("wins"),
        "hit_batsmen": pitching.get("hitBatsmen"),
        "complete_games": pitching.get("completeGames"),
    }


def _game_pitchers(game_pk: int) -> list[tuple[str, dict]]:
    payload = _get_json(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")
    rows: list[tuple[str, dict]] = []
    for side in ("away", "home"):
        players = (payload.get("teams") or {}).get(side, {}).get("players") or {}
        for player in players.values():
            person = (player.get("person") or {}).get("fullName")
            stats = _pitcher_stats_from_player(player)
            if person and stats:
                rows.append((person, stats))
    return rows


@lru_cache(maxsize=64)
def _final_game_pks(game_date: str) -> list[int]:
    payload = _get_json(
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&startDate={game_date}&endDate={game_date}"
    )
    pks: list[int] = []
    for day in payload.get("dates") or []:
        for game in day.get("games") or []:
            if game.get("status", {}).get("abstractGameState") != "Final":
                continue
            pk = game.get("gamePk")
            if pk is not None:
                pks.append(int(pk))
    return pks


def fetch_pitcher_stats_for_date(game_date: str) -> dict[str, dict]:
    """Map normalized pitcher name → box-score stats for all finals on ``game_date``."""
    out: dict[str, dict] = {}
    for game_pk in _final_game_pks(game_date):
        try:
            for name, stats in _game_pitchers(game_pk):
                key = normalize_name(name)
                if key:
                    out[key] = stats
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return out


def lookup_pitcher_stats(
  stats_by_date: dict[str, dict[str, dict]],
  *,
  slate_date: str,
  pitcher_name: str | None,
) -> dict | None:
    if not pitcher_name or not slate_date:
        return None
    day = stats_by_date.get(str(slate_date)[:10])
    if not day:
        return None
    return day.get(normalize_name(pitcher_name))
