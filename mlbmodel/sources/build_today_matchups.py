#!/usr/bin/env python3
"""
build_today_matchups.py — construct today's slate file (today_matchups.csv) that the
model code requires, from the FREE MLB Stats API (probable pitchers) joined to the
pipeline's SP/team profiles already materialized in MLBMA_DATA_DIR.

This fills the one gap hub_dataset does not carry: the same-day slate. Output columns
are the unified MLB Model's governed slate contract.

    python3 build_today_matchups.py --out /path/to/pipeline_data [--date YYYY-MM-DD]

Stdlib only. OSI is sourced from team_profiles (home/away split) as a proxy for the
pipeline's matchup OSI; FIP/HR9/K%/hand are joined from sp_profiles by pitcher_id.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import urllib.request
import zlib
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

MATCHUP_COLUMNS = [
    "Game_PK", "MLB_Game_PK", "Game_Number", "Slate_Date", "Time",
    "Away", "Home", "Away_SP", "Home_SP", "Away_Hand",
    "Home_Hand", "Away_OSI", "Home_OSI", "Away_FIP", "Home_FIP", "Away_HR9",
    "Home_HR9", "Away_K%", "Home_K%",
]

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


def abbr(name: str) -> str:
    return NAME_TO_ABBR.get(name.strip(), name.strip().upper()[:3])


def game_pk(game_date: str, away: str, home: str, game_number: int = 1) -> int:
    suffix = "" if game_number == 1 else f"|{game_number}"
    return zlib.crc32(f"{game_date}|{away}|{home}{suffix}".encode())


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sp_index(rows: list[dict]) -> dict:
    """pitcher_id -> {FIP,HR9,K_pct,hand}."""
    idx = {}
    for r in rows:
        pid = str(r.get("pitcher_id", "")).split(".")[0].strip()
        if pid:
            idx[pid] = {"FIP": r.get("FIP", ""), "HR9": r.get("HR9", ""),
                        "K": r.get("K_pct", ""), "hand": (r.get("pitcher_hand", "") or "R")[:1]}
    return idx


def team_osi(rows: list[dict]) -> dict:
    """team -> {home_osi, away_osi, osi}."""
    idx = {}
    for r in rows:
        t = str(r.get("team", "")).strip().upper()
        if t:
            idx[t] = {"home": r.get("home_osi", ""), "away": r.get("away_osi", ""),
                      "osi": r.get("osi", "")}
    return idx


def fetch_schedule(date_iso: str) -> list[dict]:
    url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_iso}"
           "&hydrate=probablePitcher,team")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode())
    dates = data.get("dates", [])
    return dates[0]["games"] if dates else []


def fetch_pitch_hands(pitcher_ids) -> dict:
    """Authoritative L/R pitching handedness from the MLB Stats API people endpoint.

    sp_profiles' pitcher_hand is unreliable: lefties are mislabeled R and freshly
    promoted starters are absent entirely (defaulting to R). That silently flips the
    opposing lineup's platoon split (vRHP shown when the starter is a lefty). The
    official people record is the source of truth for handedness, so it wins over the
    profile join. Returns {pitcher_id(str): "L"|"R"}; empty on any fetch failure so the
    sp_profiles fallback still applies.
    """
    ids = sorted({str(pid) for pid in pitcher_ids if pid})
    if not ids:
        return {}
    url = f"https://statsapi.mlb.com/api/v1/people?personIds={','.join(ids)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return {}
    hands = {}
    for person in data.get("people", []):
        code = str((person.get("pitchHand") or {}).get("code") or "").strip().upper()[:1]
        if code in ("L", "R"):
            hands[str(person.get("id"))] = code
    return hands


def et_time(game_date_utc: str) -> str:
    d = dt.datetime.fromisoformat(game_date_utc.replace("Z", "+00:00")).astimezone(ET)
    return d.strftime("%I:%M %p ET").lstrip("0")


def build_rows(out: Path, date_iso: str, games: list[dict] | None = None) -> list[dict]:
    sp = sp_index(read_csv(out / "sp_profiles.csv"))
    tm = team_osi(read_csv(out / "team_profiles.csv"))
    games = fetch_schedule(date_iso) if games is None else games

    probable_ids = [
        (g["teams"][side].get("probablePitcher") or {}).get("id")
        for g in games
        for side in ("away", "home")
    ]
    api_hand = fetch_pitch_hands(probable_ids)

    rows = []
    for g in games:
        a = g["teams"]["away"]["team"]["name"]
        h = g["teams"]["home"]["team"]["name"]
        aa, ha = abbr(a), abbr(h)
        ap = g["teams"]["away"].get("probablePitcher", {}) or {}
        hp = g["teams"]["home"].get("probablePitcher", {}) or {}
        asp = sp.get(str(ap.get("id", "")), {})
        hsp = sp.get(str(hp.get("id", "")), {})
        game_number = int(g.get("gameNumber") or 1)
        rows.append({
            "Game_PK": game_pk(date_iso, aa, ha, game_number),
            "MLB_Game_PK": g.get("gamePk"),
            "Game_Number": game_number,
            "Slate_Date": date_iso,
            "Time": et_time(g["gameDate"]),
            "Away": aa, "Home": ha,
            "Away_SP": ap.get("fullName", "TBD"), "Home_SP": hp.get("fullName", "TBD"),
            "Away_Hand": api_hand.get(str(ap.get("id", "")), asp.get("hand", "R")),
            "Home_Hand": api_hand.get(str(hp.get("id", "")), hsp.get("hand", "R")),
            "Away_OSI": tm.get(aa, {}).get("away", ""),
            "Home_OSI": tm.get(ha, {}).get("home", ""),
            "Away_FIP": asp.get("FIP", ""), "Home_FIP": hsp.get("FIP", ""),
            "Away_HR9": asp.get("HR9", ""), "Home_HR9": hsp.get("HR9", ""),
            "Away_K%": asp.get("K", ""), "Home_K%": hsp.get("K", ""),
        })
    return rows


def write_rows(rows: list[dict], dest: Path) -> None:
    with dest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MATCHUP_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {column: row.get(column, "") for column in MATCHUP_COLUMNS}
            for row in rows
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="MLBMA_DATA_DIR to write today_matchups.csv into")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    out = Path(args.out)
    games = fetch_schedule(args.date)
    print(f"MLB Stats API: {len(games)} games for {args.date}")
    rows = build_rows(out, args.date, games)

    dest = out / "today_matchups.csv"
    write_rows(rows, dest)
    print(f"wrote {dest} ({len(rows)} games)")
    for r in rows:
        print(f"  {r['Away']:>3} @ {r['Home']:<3}  {r['Time']:<10} "
              f"{r['Away_SP']} (FIP {r['Away_FIP']}) vs {r['Home_SP']} (FIP {r['Home_FIP']})")


if __name__ == "__main__":
    main()
