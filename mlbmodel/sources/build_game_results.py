#!/usr/bin/env python3
"""
build_game_results.py — ingest recent FINAL scores from the MLB Stats API and:
  1. write game_results.csv (team-level) so the model's anchors become data-driven
     (home_winp, league_runs, run SDs) instead of config defaults, and
  2. upsert games + game_outcomes into Supabase so settlement / CLV / calibration
     can grade sharp_observations + model_predictions as they accumulate.

Run from a repo dir (so `import config, db, _compat` resolve) with that repo's venv:
    cd sharp-money-tracker && .venv/bin/python ../../../mlb-model-planning/build_game_results.py --days 14
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import config          # noqa: E402
import db              # noqa: E402
import _compat as cmp  # noqa: E402

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
            a = g["teams"]["away"]; h = g["teams"]["home"]
            if "score" not in a or "score" not in h:
                continue
            ls = g.get("linescore", {}).get("innings", [])
            f5h = sum((i.get("home", {}) or {}).get("runs", 0) or 0 for i in ls[:5])
            f5a = sum((i.get("away", {}) or {}).get("runs", 0) or 0 for i in ls[:5])
            games.append({
                "date": g.get("officialDate", d["date"]),
                "away": abbr(a["team"]["name"]), "home": abbr(h["team"]["name"]),
                "ar": int(a["score"]), "hr": int(h["score"]),
                "f5a": int(f5a), "f5h": int(f5h),
            })
    return games


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
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
    out = Path(config.PIPELINE_DATA_DIR) / "game_results.csv"
    cols = ["game_date", "home_away", "team", "opp", "team_runs", "opp_runs", "result"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(res_rows)
    print(f"wrote {out} ({len(res_rows)} team-rows)")

    # 2) seed past games + game_outcomes in Supabase (settlement backbone)
    grows, orows = [], []
    for g in games:
        gpk = cmp.game_pk(g["date"], g["away"], g["home"])
        winner = g["home"] if g["hr"] > g["ar"] else g["away"]
        grows.append({"game_pk": gpk, "season": 2026, "game_date": g["date"],
                      "home_team": g["home"], "away_team": g["away"], "status": "final"})
        orows.append({"game_pk": gpk, "home_runs": g["hr"], "away_runs": g["ar"],
                      "home_f5_runs": g["f5h"], "away_f5_runs": g["f5a"],
                      "total_runs": g["hr"] + g["ar"], "margin_home": g["hr"] - g["ar"],
                      "winner_team": winner})
    # dedupe by game_pk — doubleheaders share the deterministic date|away|home key
    # (a known limitation of that key, consistent with sharp_tracker/bet_evaluator).
    grows = list({r["game_pk"]: r for r in grows}.values())
    orows = list({r["game_pk"]: r for r in orows}.values())
    db.upsert("games", grows, "game_pk")
    db.upsert("game_outcomes", orows, "game_pk")
    print(f"upserted games={db.count('games')}  game_outcomes={db.count('game_outcomes')}")


if __name__ == "__main__":
    main()
