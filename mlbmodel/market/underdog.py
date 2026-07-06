"""Underdog pick'em lines — MLB pitcher over/unders from the public over_under_lines API.

Underdog's ``/beta/v5/over_under_lines`` returns ``over_under_lines`` (each with a ``stat_value``
and an ``over_under.appearance_stat`` naming the player + stat), plus ``appearances`` (line ->
player + team) and ``players``/``games`` for identity. The same six pitcher markets PrizePicks
carries are here; "Fantasy Points" grades against ``PP_Fantasy`` because Underdog's pitcher
fantasy scoring matches PrizePicks (verified: their standard fantasy lines agree). Fetch/parse and
the line dict shape mirror ``prizepicks`` so the report grades both sources the same way — reuse
``prizepicks.normalize_name`` and ``prizepicks.board_by_player``. Non-fatal / no API key.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from mlbmodel.market.prizepicks import normalize_name

UD_URL = "https://api.underdogfantasy.com/beta/v5/over_under_lines"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Underdog display_stat -> the projection key it grades against.
UD_PITCHER_STATS = {
    "Fantasy Points": "PP_Fantasy",
    "Hits Allowed": "H",
    "Strikeouts": "K",
    "Earned Runs Allowed": "ER",
    "Pitching Outs": "Outs",
    "Walks Allowed": "BB",
}
_PITCHER_POS = {"SP", "RP"}


def _team_abbr(games: list[dict]) -> dict[str, str]:
    """team_id -> abbreviation, parsed from each game title ("AWAY vs HOME")."""
    mapping: dict[str, str] = {}
    for game in games:
        parts = [part.strip() for part in str(game.get("title") or "").split(" vs ")]
        if len(parts) == 2:
            if game.get("away_team_id"):
                mapping[game["away_team_id"]] = parts[0]
            if game.get("home_team_id"):
                mapping[game["home_team_id"]] = parts[1]
    return mapping


def _parse(payload: dict) -> list[dict]:
    players = {player["id"]: player for player in payload.get("players", [])}
    appearances = {appearance["id"]: appearance for appearance in payload.get("appearances", [])}
    teams = _team_abbr(payload.get("games", []))
    lines: list[dict] = []
    for line in payload.get("over_under_lines", []):
        if line.get("status") not in (None, "active"):
            continue
        appearance_stat = (line.get("over_under") or {}).get("appearance_stat") or {}
        proj_key = UD_PITCHER_STATS.get(appearance_stat.get("display_stat"))
        if not proj_key:
            continue
        appearance = appearances.get(appearance_stat.get("appearance_id"))
        if not appearance:
            continue
        player = players.get(appearance.get("player_id"))
        if (
            not player
            or player.get("sport_id") != "MLB"
            or player.get("position_name") not in _PITCHER_POS
        ):
            continue
        stat_value = line.get("stat_value")
        if stat_value is None:
            continue
        name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
        if not name:
            continue
        lines.append(
            {
                "player": name,
                "player_key": normalize_name(name),
                "team": teams.get(appearance.get("team_id")),
                "proj_key": proj_key,
                "stat_type": appearance_stat.get("display_stat"),
                "line": float(stat_value),
                "odds_type": "standard",  # Underdog single o/u lines are the standard line.
            }
        )
    return lines


def parse_payload(payload: dict, cache_path: str | Path | None = None) -> list[dict]:
    lines = _parse(payload)
    if cache_path is not None:
        Path(cache_path).write_text(json.dumps(lines), encoding="utf-8")
    return lines


def fetch_lines(cache_path: str | Path | None = None) -> list[dict]:
    request = urllib.request.Request(
        UD_URL, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:  # noqa: S310 (trusted host)
        payload = json.load(response)
    return parse_payload(payload, cache_path)


def load_lines(cache_path: str | Path | None) -> list[dict]:
    if not cache_path:
        return []
    path = Path(cache_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def main() -> None:  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Cache Underdog MLB pitcher pick'em lines.")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--from-raw", help="Parse an already-downloaded Underdog JSON.")
    args = parser.parse_args()
    try:
        if args.from_raw:
            payload = json.loads(Path(args.from_raw).read_text(encoding="utf-8"))
            lines = parse_payload(payload, args.cache)
        else:
            lines = fetch_lines(args.cache)
        pitchers = len({line["player_key"] for line in lines})
        print(f"underdog lines={len(lines)} pitchers={pitchers}")
    except Exception as exc:  # noqa: BLE001 — non-fatal at build time
        print(f"underdog fetch failed: {exc}")


if __name__ == "__main__":  # pragma: no cover
    main()
