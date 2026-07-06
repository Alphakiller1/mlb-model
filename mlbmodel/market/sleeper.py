"""Sleeper pick'em lines — MLB pitcher over/unders from the public lines API.

Sleeper exposes ``/lines/available`` (each line has a ``subject_id``, ``wager_type`` and an
``outcome_value``) and a static ``/v1/players/mlb`` id->player map used to resolve names and
filter to pitchers (position SP/RP). Sleeper carries the five raw pitcher markets (strikeouts,
hits allowed, earned runs, outs, walks) — no pitcher fantasy score — which grade directly against
the simulated components. The parsed line dict shape mirrors ``prizepicks`` so the report grades
all pick'em sources the same way. Non-fatal / no API key.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from mlbmodel.market.prizepicks import normalize_name

SLEEPER_LINES_URL = "https://api.sleeper.app/lines/available?dynasty=false"
SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/mlb"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Sleeper wager_type -> the projection key it grades against (pitcher markets only).
SLEEPER_PITCHER_STATS = {
    "strike_outs": "K",
    "hits_allowed": "H",
    "earned_runs": "ER",
    "outs": "Outs",
    "walks": "BB",
}
_PITCHER_POS = {"SP", "RP"}


def _parse(lines_payload: list, players_payload: dict) -> list[dict]:
    players = players_payload if isinstance(players_payload, dict) else {}
    lines: list[dict] = []
    for entry in lines_payload if isinstance(lines_payload, list) else []:
        option = (entry.get("options") or [{}])[0]
        if option.get("sport") != "mlb":
            continue
        proj_key = SLEEPER_PITCHER_STATS.get(option.get("wager_type"))
        if not proj_key:
            continue
        if str(entry.get("game_status") or option.get("game_status") or "") not in (
            "",
            "pre_game",
        ):
            continue
        player = players.get(str(entry.get("subject_id") or option.get("subject_id") or ""))
        if not player or player.get("position") not in _PITCHER_POS:
            continue
        value = option.get("outcome_value")
        if value is None:
            continue
        name = player.get("full_name") or (
            f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
        )
        if not name:
            continue
        lines.append(
            {
                "player": name,
                "player_key": normalize_name(name),
                "team": option.get("subject_team") or player.get("team"),
                "proj_key": proj_key,
                "stat_type": option.get("wager_type"),
                "line": float(value),
                "odds_type": "standard",
            }
        )
    return lines


def parse_payload(
    lines_payload: list, players_payload: dict, cache_path: str | Path | None = None
) -> list[dict]:
    lines = _parse(lines_payload, players_payload)
    if cache_path is not None:
        Path(cache_path).write_text(json.dumps(lines), encoding="utf-8")
    return lines


def _get_json(url: str) -> object:
    request = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (trusted host)
        return json.load(response)


def fetch_lines(cache_path: str | Path | None = None) -> list[dict]:
    lines_payload = _get_json(SLEEPER_LINES_URL)
    players_payload = _get_json(SLEEPER_PLAYERS_URL)
    return parse_payload(lines_payload, players_payload, cache_path)


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

    parser = argparse.ArgumentParser(description="Cache Sleeper MLB pitcher pick'em lines.")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--from-raw-lines", help="Already-downloaded lines/available JSON.")
    parser.add_argument("--from-raw-players", help="Already-downloaded players/mlb JSON.")
    args = parser.parse_args()
    try:
        if args.from_raw_lines and args.from_raw_players:
            lines_payload = json.loads(Path(args.from_raw_lines).read_text(encoding="utf-8"))
            players_payload = json.loads(Path(args.from_raw_players).read_text(encoding="utf-8"))
            lines = parse_payload(lines_payload, players_payload, args.cache)
        else:
            lines = fetch_lines(args.cache)
        pitchers = len({line["player_key"] for line in lines})
        print(f"sleeper lines={len(lines)} pitchers={pitchers}")
    except Exception as exc:  # noqa: BLE001 — non-fatal at build time
        print(f"sleeper fetch failed: {exc}")


if __name__ == "__main__":  # pragma: no cover
    main()
