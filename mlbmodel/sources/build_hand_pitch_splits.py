#!/usr/bin/env python3
"""
build_hand_pitch_splits.py — plate-appearance-level team offense, cut two ways.

Both outputs come from ONE pass over the MLB Stats API play-by-play feed, because both
need the same thing: every completed plate appearance, tagged with the hand of the pitcher
who finished it and the type of the pitch that ended it.

  1. team_hand_splits.csv       — team offense vs LHP / vs RHP over a recent window
                                  (K%, BB%, AVG, OBP, SLG, ISO, wOBA). This is the true
                                  platoon split: every PA against a pitcher of that hand,
                                  relievers included — not "games started by a lefty".
  2. team_pitch_type_splits.csv — team offense against each PITCH TYPE, on the same PA
                                  grammar, plus a league row per pitch type to shrink toward.

The PA whitelist below was validated against MLB's own date-bounded team totals
(`stats=byDateRange`): NYY 2026-08-01..08-30 reproduced PA/AB/H/BB/SO/HR/TB/HBP/SF exactly.
Two traps it encodes:

  * `result.type` is "atBat" for pickoffs and caught stealings too — those end a play but
    NOT a plate appearance, and counting them inflates PA. Whitelist the terminal events.
  * The unbounded `stats=statSplits` endpoint ignores startDate/endDate entirely, so it
    cannot produce a rolling window and must not be trusted as a check against one.

Run from the repository root:
    python -m mlbmodel.sources.build_hand_pitch_splits --days 30 --mix-days 120 --out ./data
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
UA = {"User-Agent": "mlb-model/1.0"}

# Only key names listed here are returned, at any depth — this turns a ~590 KB play-by-play
# document into ~37 KB, which is what makes a multi-month sweep practical.
PBP_FIELDS = (
    "allPlays,result,eventType,about,halfInning,matchup,pitchHand,code,"
    "playEvents,details,type,isPitch"
)

NAME_TO_ABBR = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
    "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Athletics": "ATH", "Oakland Athletics": "ATH",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDP",
    "San Francisco Giants": "SFG", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TBR", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}

STRIKEOUTS = {"strikeout", "strikeout_double_play", "strikeout_triple_play"}
WALKS = {"walk", "intent_walk"}
SAC_FLIES = {"sac_fly", "sac_fly_double_play"}
SAC_BUNTS = {"sac_bunt", "sac_bunt_double_play"}
TOTAL_BASES = {"single": 1, "double": 2, "triple": 3, "home_run": 4}

# Events that terminate a plate appearance. Anything outside this set (pickoff_1b,
# caught_stealing_2b, stolen_base_3b, game_advisory, ...) ends a play without ending a PA
# and must not be counted.
PA_EVENTS = (
    STRIKEOUTS | WALKS | SAC_FLIES | SAC_BUNTS | set(TOTAL_BASES) | {
        "field_out", "force_out", "grounded_into_double_play", "double_play", "triple_play",
        "hit_by_pitch", "field_error", "fielders_choice", "fielders_choice_out",
        "catcher_interf", "other_out", "batter_interference",
    }
)

# FanGraphs-scale linear weights. The absolute level is irrelevant here — every number is
# read as a distance from the league mean of the same statistic — but the RATIOS between
# events are what make wOBA a run-value statistic rather than an average with extra steps.
WOBA_WEIGHTS = {"bb": 0.690, "hbp": 0.720, "single": 0.890, "double": 1.270,
                "triple": 1.620, "home_run": 2.100}

PITCH_NAMES = {
    "FF": "4-Seam Fastball", "SI": "Sinker", "FT": "2-Seam Fastball", "FC": "Cutter",
    "SL": "Slider", "ST": "Sweeper", "SV": "Slurve", "CU": "Curveball",
    "KC": "Knuckle Curve", "CS": "Slow Curve", "CH": "Changeup", "FS": "Splitter",
    "FO": "Forkball", "SC": "Screwball", "KN": "Knuckleball", "EP": "Eephus",
    "FA": "Fastball",
}
# Intentional balls and pitchouts are not part of an arsenal.
SKIP_PITCH_TYPES = {"IN", "PO", "AB", "UN", "", "NP"}


def _get(url: str, timeout: int = 30, retries: int = 3) -> dict:
    last: Exception | None = None
    for _ in range(retries):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last = exc
    raise RuntimeError(f"MLB Stats API failed after {retries} tries: {url}") from last


def fetch_schedule(start: str, end: str) -> list[dict]:
    """Completed regular-season games in [start, end], as warehouse abbreviations.

    `detailedState`, not `abstractGameState`: a postponed game still reports the abstract
    state "Final" and carries an empty play-by-play, so filtering on the abstract state
    silently mixes zero-PA shells into the game count.
    """
    data = _get(f"{API}/schedule?sportId=1&startDate={start}&endDate={end}&gameType=R",
                timeout=45)
    games: list[dict] = []
    for day in data.get("dates", []):
        for game in day.get("games", []):
            if (game.get("status") or {}).get("detailedState") != "Final":
                continue
            away = NAME_TO_ABBR.get(str(game["teams"]["away"]["team"]["name"]).strip())
            home = NAME_TO_ABBR.get(str(game["teams"]["home"]["team"]["name"]).strip())
            if not away or not home:
                continue  # All-Star / exhibition sides — never invent an abbreviation.
            games.append({
                "game_pk": int(game["gamePk"]),
                "date": str(game.get("officialDate") or day.get("date") or "")[:10],
                "away": away,
                "home": home,
            })
    return games


def _terminal_pitch(play: dict) -> str:
    """Pitch type that ended the plate appearance, or '' when it did not end on a pitch.

    Attributing the whole PA outcome to its final pitch is the convention Baseball Savant's
    pitch-arsenal leaderboards use. It is a convention, not a measurement: a walk is
    credited to ball four and a strikeout to the put-away pitch.
    """
    for event in reversed(play.get("playEvents") or []):
        if not event.get("isPitch"):
            continue
        code = str((((event.get("details") or {}).get("type")) or {}).get("code") or "").upper()
        return "" if code in SKIP_PITCH_TYPES else code
    return ""


def fetch_plate_appearances(game_pk: int) -> list[dict]:
    data = _get(f"{API}/game/{game_pk}/playByPlay?fields={PBP_FIELDS}")
    plays = []
    for play in data.get("allPlays", []):
        event = str((play.get("result") or {}).get("eventType") or "")
        if event not in PA_EVENTS:
            continue
        hand = str((((play.get("matchup") or {}).get("pitchHand")) or {}).get("code") or "")
        hand = hand.upper()
        plays.append({
            "half": str((play.get("about") or {}).get("halfInning") or ""),
            "hand": hand if hand in {"L", "R"} else "",
            "event": event,
            "pitch": _terminal_pitch(play),
        })
    return plays


def blank_bucket() -> dict[str, float]:
    return {"pa": 0, "ab": 0, "h": 0, "tb": 0, "bb": 0, "ibb": 0, "hbp": 0, "so": 0,
            "hr": 0, "sf": 0, "sh": 0, "ci": 0, "single": 0, "double": 0, "triple": 0}


def accumulate(bucket: dict[str, float], event: str) -> None:
    bucket["pa"] += 1
    if event in STRIKEOUTS:
        bucket["so"] += 1
    if event in WALKS:
        bucket["bb"] += 1
    if event == "intent_walk":
        bucket["ibb"] += 1
    if event == "hit_by_pitch":
        bucket["hbp"] += 1
    if event in SAC_FLIES:
        bucket["sf"] += 1
    if event in SAC_BUNTS:
        bucket["sh"] += 1
    if event == "catcher_interf":
        bucket["ci"] += 1
    bases = TOTAL_BASES.get(event)
    if bases:
        bucket["h"] += 1
        bucket["tb"] += bases
        if event == "home_run":
            bucket["hr"] += 1
        else:
            bucket[event] += 1
    # AB excludes walks, HBP, sacrifices and catcher's interference.
    bucket["ab"] = (bucket["pa"] - bucket["bb"] - bucket["hbp"]
                    - bucket["sf"] - bucket["sh"] - bucket["ci"])


def rates(bucket: dict[str, float]) -> dict[str, float | None]:
    pa, ab = bucket["pa"], bucket["ab"]
    obp_denom = ab + bucket["bb"] + bucket["hbp"] + bucket["sf"]
    woba_denom = ab + bucket["bb"] - bucket["ibb"] + bucket["sf"] + bucket["hbp"]
    woba_num = (
        WOBA_WEIGHTS["bb"] * (bucket["bb"] - bucket["ibb"])
        + WOBA_WEIGHTS["hbp"] * bucket["hbp"]
        + WOBA_WEIGHTS["single"] * bucket["single"]
        + WOBA_WEIGHTS["double"] * bucket["double"]
        + WOBA_WEIGHTS["triple"] * bucket["triple"]
        + WOBA_WEIGHTS["home_run"] * bucket["hr"]
    )
    avg = bucket["h"] / ab if ab else None
    slg = bucket["tb"] / ab if ab else None
    return {
        "k_pct": 100.0 * bucket["so"] / pa if pa else None,
        "bb_pct": 100.0 * bucket["bb"] / pa if pa else None,
        "avg": avg,
        "obp": (bucket["h"] + bucket["bb"] + bucket["hbp"]) / obp_denom if obp_denom else None,
        "slg": slg,
        "iso": (slg - avg) if (avg is not None and slg is not None) else None,
        "woba": woba_num / woba_denom if woba_denom else None,
        "hr_pct": 100.0 * bucket["hr"] / pa if pa else None,
    }


COUNT_COLS = ["pa", "ab", "h", "tb", "bb", "hbp", "so", "hr"]
RATE_COLS = ["k_pct", "bb_pct", "avg", "obp", "slg", "iso", "woba", "hr_pct"]


def _row(keys: dict, bucket: dict, extra: dict | None = None) -> dict:
    row = dict(keys)
    row.update({col: int(bucket[col]) for col in COUNT_COLS})
    for col, value in rates(bucket).items():
        row[col] = None if value is None else round(value, 5)
    if extra:
        row.update(extra)
    return row


def _write(path: Path, rows: list[dict], header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in header})


HAND_HEADER = (["team", "pitcher_hand", "games"] + COUNT_COLS + RATE_COLS
               + ["window_start", "window_end"])
MIX_HEADER = (["team", "pitch_type", "pitch_name"] + COUNT_COLS + RATE_COLS
              + ["window_start", "window_end"])


def aggregate(games: list[dict], plays_by_game: list[list[dict]], hand_start: str) -> tuple:
    """Fold PA rows into (team, hand) and (team, pitch type) buckets plus league rows."""
    hand: dict[tuple[str, str], dict] = defaultdict(blank_bucket)
    hand_games: dict[tuple[str, str], set] = defaultdict(set)
    hand_league: dict[str, dict] = defaultdict(blank_bucket)
    mix: dict[tuple[str, str], dict] = defaultdict(blank_bucket)
    mix_league: dict[str, dict] = defaultdict(blank_bucket)

    for game, plays in zip(games, plays_by_game):
        in_hand_window = game["date"] >= hand_start
        for play in plays:
            team = game["away"] if play["half"] == "top" else game["home"]
            if in_hand_window and play["hand"]:
                accumulate(hand[(team, play["hand"])], play["event"])
                accumulate(hand_league[play["hand"]], play["event"])
                hand_games[(team, play["hand"])].add(game["game_pk"])
            if play["pitch"]:
                accumulate(mix[(team, play["pitch"])], play["event"])
                accumulate(mix_league[play["pitch"]], play["event"])
    return hand, hand_games, hand_league, mix, mix_league


def build(out_dir: Path, days: int = 30, mix_days: int = 120, workers: int = 12,
          end_date: str | None = None) -> dict:
    end = end_date or dt.date.today().isoformat()
    end_day = dt.date.fromisoformat(end)
    mix_start = (end_day - dt.timedelta(days=max(days, mix_days))).isoformat()
    hand_start = (end_day - dt.timedelta(days=days)).isoformat()

    games = fetch_schedule(mix_start, end)
    if not games:
        raise RuntimeError(f"no completed games between {mix_start} and {end}")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        plays_by_game = list(pool.map(lambda g: fetch_plate_appearances(g["game_pk"]), games))

    hand, hand_games, hand_league, mix, mix_league = aggregate(games, plays_by_game, hand_start)

    window = {"window_start": hand_start, "window_end": end}
    hand_rows = [
        _row({"team": team, "pitcher_hand": pitcher_hand}, bucket,
             {"games": len(hand_games[(team, pitcher_hand)]), **window})
        for (team, pitcher_hand), bucket in sorted(hand.items())
    ]
    hand_rows += [
        _row({"team": "LGE", "pitcher_hand": pitcher_hand}, bucket,
             {"games": len(games), **window})
        for pitcher_hand, bucket in sorted(hand_league.items())
    ]

    mix_window = {"window_start": mix_start, "window_end": end}
    mix_rows = [
        _row({"team": team, "pitch_type": pitch, "pitch_name": PITCH_NAMES.get(pitch, pitch)},
             bucket, mix_window)
        for (team, pitch), bucket in sorted(mix.items())
    ]
    mix_rows += [
        _row({"team": "LGE", "pitch_type": pitch, "pitch_name": PITCH_NAMES.get(pitch, pitch)},
             bucket, mix_window)
        for pitch, bucket in sorted(mix_league.items())
    ]

    _write(out_dir / "team_hand_splits.csv", hand_rows, HAND_HEADER)
    _write(out_dir / "team_pitch_type_splits.csv", mix_rows, MIX_HEADER)

    return {
        "games": len(games),
        "hand_rows": len(hand_rows),
        "mix_rows": len(mix_rows),
        "hand_pa": sum(int(b["pa"]) for b in hand_league.values()),
        "mix_pa": sum(int(b["pa"]) for b in mix_league.values()),
        "hand_window": [hand_start, end],
        "mix_window": [mix_start, end],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build team hand + pitch-type PA splits.")
    parser.add_argument("--days", type=int, default=30,
                        help="lookback for the vs-LHP/vs-RHP splits (default 30)")
    parser.add_argument("--mix-days", type=int, default=120,
                        help="lookback for the per-pitch-type splits (default 120)")
    parser.add_argument("--out", default="./data")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD; defaults to today")
    args = parser.parse_args(argv)

    summary = build(Path(args.out), args.days, args.mix_days, args.workers, args.end_date)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
