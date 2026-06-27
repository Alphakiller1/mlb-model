#!/usr/bin/env python3
"""
seed_warehouse.py — upsert teams (30) + today's games (15) into the Supabase
warehouse so the FK targets exist before sharp_tracker / bet_evaluator write
signals & predictions. Idempotent.

Run from a repo dir (so `import config, db, _compat` resolve) with that repo's venv:
    cd sharp-money-tracker && .venv/bin/python ../../../mlb-model-planning/seed_warehouse.py
or simply use refresh.sh which wires the paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

# allow running from anywhere: ensure the CWD repo is importable
sys.path.insert(0, str(Path.cwd()))

import config          # noqa: E402
import db              # noqa: E402
import _compat as cmp  # noqa: E402
import pandas as pd    # noqa: E402


def main() -> None:
    dd = str(config.PIPELINE_DATA_DIR)
    today = cmp.TODAY

    tp = pd.read_csv(f"{dd}/team_profiles.csv")
    teams = sorted(tp["team"].astype(str).str.upper().str.strip().unique())
    trows = [{"team_id": i + 1, "team_abbr": t, "team_name": t} for i, t in enumerate(teams)]
    db.upsert("teams", trows, "team_abbr")
    print(f"  teams: {db.count('teams')}")

    m = pd.read_csv(f"{dd}/today_matchups.csv")
    grows = []
    for _, r in m.iterrows():
        a = str(r["Away"]).upper().strip()
        h = str(r["Home"]).upper().strip()
        grows.append({
            "game_pk": cmp.game_pk(today, a, h), "season": 2026, "game_date": today,
            "scheduled_start": cmp.scheduled_start(today, r.get("Time")),
            "home_team": h, "away_team": a, "status": "scheduled",
        })
    db.upsert("games", grows, "game_pk")
    print(f"  games: {db.count('games')}")


if __name__ == "__main__":
    main()
