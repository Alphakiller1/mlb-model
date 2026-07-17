"""PrizePicks pick'em lines — pitcher over/unders from the public projections API.

PrizePicks publishes MLB projections at api.prizepicks.com/projections?league_id=2 as JSON:API
(``data`` = projection lines, ``included`` = player records). Five of the six pitcher markets map
straight to a simulated component (hits/K/ER/outs/BB); "Pitcher Fantasy Score" maps to the
PrizePicks-scored ``PP_Fantasy`` projection. This module fetches + caches those lines so the
static build can grade the model against them. It has no API key and costs no Odds-API credits;
it degrades to an empty board on any error (unofficial endpoint — may rate-limit / block).
"""
from __future__ import annotations

import json
import unicodedata
import urllib.request
from pathlib import Path

PP_LEAGUE_MLB = 2
PP_URL = (
    f"https://api.prizepicks.com/projections?league_id={PP_LEAGUE_MLB}"
    "&per_page=1000&single_stat=true"
)
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# PrizePicks stat_type -> the projection key it grades against (see props.model projections).
PP_PITCHER_STATS = {
    "Pitcher Fantasy Score": "PP_Fantasy",
    "Hits Allowed": "H",
    "Pitcher Strikeouts": "K",
    "Earned Runs Allowed": "ER",
    "Pitching Outs": "Outs",
    "Walks Allowed": "BB",
}
# Short display label per market, for the pick'em table.
STAT_LABEL = {
    "PP_Fantasy": "Fantasy",
    "H": "Hits",
    "K": "Strikeouts",
    "ER": "Earned runs",
    "Outs": "Outs",
    "BB": "Walks",
}
# Prefer the true ~50/50 standard line; fall back to the shifted goblin/demon variants.
_ODDS_PREFERENCE = {"standard": 0, "goblin": 1, "demon": 2}


def normalize_name(name: str | None) -> str:
    """Lowercased, accent- and punctuation-stripped name for matching PP players to our slate."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == " ").strip()


def _parse(payload: dict) -> list[dict]:
    players = {
        item["id"]: item.get("attributes", {})
        for item in payload.get("included", [])
        if item.get("type") == "new_player"
    }
    lines: list[dict] = []
    for row in payload.get("data", []):
        attrs = row.get("attributes", {})
        proj_key = PP_PITCHER_STATS.get(attrs.get("stat_type"))
        if not proj_key or attrs.get("status") not in (None, "pre_game"):
            continue
        line_score = attrs.get("line_score")
        if line_score is None:
            continue
        rel = (row.get("relationships", {}).get("new_player", {}) or {}).get("data", {}) or {}
        player = players.get(rel.get("id"), {})
        name = player.get("name")
        if not name:
            continue
        lines.append(
            {
                "player": name,
                "player_key": normalize_name(name),
                "team": player.get("team"),
                "proj_key": proj_key,
                "stat_type": attrs.get("stat_type"),
                "line": float(line_score),
                "odds_type": attrs.get("odds_type") or "standard",
            }
        )
    return lines


def parse_payload(payload: dict, cache_path: str | Path | None = None) -> list[dict]:
    """Parse a raw PrizePicks JSON:API payload into pitcher lines; optionally cache them.

    Kept separate from the network fetch so the build can download the payload with curl (which
    the PrizePicks/Cloudflare edge accepts) and hand the raw JSON here to parse.
    """
    lines = _parse(payload)
    if cache_path is not None:
        from mlbmodel.market.lines_cache import write_lines_cache

        write_lines_cache(lines, cache_path)
    return lines


def fetch_lines(cache_path: str | Path | None = None) -> list[dict]:
    """Fetch + parse live (urllib). Works locally; the edge may 403 automated clients, so the
    build path downloads with curl and calls ``parse_payload`` on the raw JSON instead."""
    request = urllib.request.Request(
        PP_URL, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:  # noqa: S310 (trusted host)
        payload = json.load(response)
    return parse_payload(payload, cache_path)


def load_lines(cache_path: str | Path | None) -> list[dict]:
    from mlbmodel.market.lines_cache import read_lines_cache

    lines, _ = read_lines_cache(cache_path)
    return lines


def board_by_player(lines: list[dict]) -> dict[str, dict[str, dict]]:
    """Map normalized player name -> proj_key -> the single preferred line (standard > goblin > demon)."""
    board: dict[str, dict[str, dict]] = {}
    for line in lines:
        key, proj = line.get("player_key"), line.get("proj_key")
        if not key or not proj:
            continue
        current = board.setdefault(key, {}).get(proj)
        if current is None or (
            _ODDS_PREFERENCE.get(line.get("odds_type"), 3)
            < _ODDS_PREFERENCE.get(current.get("odds_type"), 3)
        ):
            board[key][proj] = line
    return board


def main() -> None:  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Cache PrizePicks MLB pitcher pick'em lines.")
    parser.add_argument("--cache", required=True)
    parser.add_argument(
        "--from-raw", help="Parse this already-downloaded PrizePicks JSON instead of fetching."
    )
    args = parser.parse_args()
    try:
        if args.from_raw:
            payload = json.loads(Path(args.from_raw).read_text(encoding="utf-8"))
            lines = parse_payload(payload, args.cache)
        else:
            lines = fetch_lines(args.cache)
        pitchers = len({line["player_key"] for line in lines})
        print(f"prizepicks lines={len(lines)} pitchers={pitchers}")
    except Exception as exc:  # noqa: BLE001 — non-fatal at build time
        print(f"prizepicks fetch failed: {exc}")


if __name__ == "__main__":  # pragma: no cover
    main()
