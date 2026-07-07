"""Stable slate game keys — disambiguate doubleheaders (MIL@STL vs MIL@STL#2)."""
from __future__ import annotations

from mlbmodel.sources.sync_mlbma import matchup_keys


def assign_slate_keys(games: list[dict]) -> None:
    """Attach a unique ``key`` to each slate game dict (mutates in place)."""
    rows = [{"Away": g["away"], "Home": g["home"]} for g in games]
    keys = matchup_keys(rows)
    for game, key in zip(games, keys, strict=True):
        game["key"] = key


def parse_game_key(key: str) -> tuple[str, str, int]:
    """Return (away, home, game_number) from a slate key."""
    raw = str(key or "").strip().upper()
    game_number = 1
    if "#" in raw:
        base, num_s = raw.rsplit("#", 1)
        game_number = int(num_s)
    else:
        base = raw
    away, home = base.split("@", 1)
    return away, home, game_number


def resolve_featured_game(featured: str, slate: list[dict]) -> str:
    """Map CLI ``--game MIL@STL`` to the first matching unique slate key."""
    raw = str(featured or "").strip().upper()
    keys = [g["key"] for g in slate if not g.get("err") and g.get("key")]
    if not keys:
        return raw
    if raw in keys:
        return raw
    if "@" in raw and "#" not in raw:
        for key in keys:
            if key == raw:
                return key
    return keys[0]


def game_option_label(game: dict, slate: list[dict]) -> str:
    """Dropdown label; append start time when the pair appears more than once."""
    away, home = game["away"], game["home"]
    label = f"{away} @ {home}"
    n = sum(
        1 for g in slate
        if not g.get("err") and g.get("away") == away and g.get("home") == home
    )
    if n > 1:
        time = str(game.get("time") or "").strip()
        if time:
            label += f" · {time}"
    return label
