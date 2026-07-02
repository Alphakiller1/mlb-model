#!/usr/bin/env python3
"""
build_game_results.py — ingest recent FINAL scores from the MLB Stats API and:
  1. write game_results.csv (team-level) so the model's anchors become data-driven
     (home_winp, league_runs, run SDs) instead of config defaults, and
  2. upsert games + game_outcomes into Supabase so settlement / CLV / calibration
     can grade sharp_observations + model_predictions as they accumulate.

Run from the unified repository:
    python -m mlbmodel.sources.build_game_results --days 14 --out ./data
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import urllib.request
import zlib
from pathlib import Path

from mlbmodel import settings
from mlbmodel.storage.supabase import SupabaseWriter

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


def fetch_finals(start: str, end: str) -> list[dict]:
    url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={start}"
           f"&endDate={end}&hydrate=linescore,team")
    with urllib.request.urlopen(url, timeout=40) as r:
        data = json.loads(r.read().decode())
    games = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            a = g["teams"]["away"]
            h = g["teams"]["home"]
            if "score" not in a or "score" not in h:
                continue
            ls = g.get("linescore", {}).get("innings", [])
            f5h = sum((i.get("home", {}) or {}).get("runs", 0) or 0 for i in ls[:5])
            f5a = sum((i.get("away", {}) or {}).get("runs", 0) or 0 for i in ls[:5])
            games.append({
                "date": g.get("officialDate", d["date"]),
                "game_number": int(g.get("gameNumber") or 1),
                "mlb_game_pk": g.get("gamePk"),
                "away": abbr(a["team"]["name"]), "home": abbr(h["team"]["name"]),
                "ar": int(a["score"]), "hr": int(h["score"]),
                "f5a": int(f5a), "f5h": int(f5h),
            })
    return games


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out", default=str(settings.DATA_DIR))
    args = ap.parse_args()

    today = dt.date.today()
    start = (today - dt.timedelta(days=args.days)).isoformat()
    end = (today - dt.timedelta(days=1)).isoformat()
    games = fetch_finals(start, end)
    print(f"MLB finals {start}..{end}: {len(games)} games")

    # 1) game_results.csv — two team-rows per game (model anchor refresh)
    res_rows = []
    for g in games:
        res_rows.append({"game_date": g["date"], "home_away": "home", "team": g["home"],
                         "opp": g["away"], "team_runs": g["hr"], "opp_runs": g["ar"],
                         "result": "W" if g["hr"] > g["ar"] else "L"})
        res_rows.append({"game_date": g["date"], "home_away": "away", "team": g["away"],
                         "opp": g["home"], "team_runs": g["ar"], "opp_runs": g["hr"],
                         "result": "W" if g["ar"] > g["hr"] else "L"})
    out = Path(args.out) / "game_results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["game_date", "home_away", "team", "opp", "team_runs", "opp_runs", "result"]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(res_rows)
    print(f"wrote {out} ({len(res_rows)} team-rows)")

    # 2) seed past games + game_outcomes in Supabase (settlement backbone)
    grows, orows = [], []
    for g in games:
        gpk = game_pk(g["date"], g["away"], g["home"], g["game_number"])
        winner = g["home"] if g["hr"] > g["ar"] else g["away"]
        grows.append({"game_pk": gpk, "season": int(g["date"][:4]), "game_date": g["date"],
                      "home_team": g["home"], "away_team": g["away"], "status": "final"})
        orows.append({"game_pk": gpk, "home_runs": g["hr"], "away_runs": g["ar"],
                      "home_f5_runs": g["f5h"], "away_f5_runs": g["f5a"],
                      "total_runs": g["hr"] + g["ar"], "margin_home": g["hr"] - g["ar"],
                      "winner_team": winner})
    grows = list({r["game_pk"]: r for r in grows}.values())
    orows = list({r["game_pk"]: r for r in orows}.values())
    writer = SupabaseWriter()
    if writer.url and writer.key:
        writer.upsert("games", grows, "game_pk")
        writer.upsert("game_outcomes", orows, "game_pk")
        print(f"upserted games={len(grows)} game_outcomes={len(orows)}")
    else:
        print("warehouse write skipped: SUPABASE_URL/SUPABASE_KEY not configured")


if __name__ == "__main__":
    main()
