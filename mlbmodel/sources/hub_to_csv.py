#!/usr/bin/env python3
"""
hub_to_csv.py — materialize the mlbma pipeline's `hub_dataset` (stored in Supabase)
into the CSV files the bet-evaluator / sharp-money-tracker model code reads.

This is the bridge that lets the model run off the Supabase warehouse instead of a
Windows MLBMA_DATA_DIR path. It is READ-ONLY against Supabase and writes CSVs into a
local data dir you then point MLBMA_DATA_DIR at.

    python3 hub_to_csv.py --env /path/to/.env --out /path/to/data_dir

Stdlib only (urllib/json/csv) — runs on any Python 3.
NOTE: the daily slate files (today_matchups/today_weather/today_lineups) are NOT in
hub_dataset; they come from the pipeline's same-day run. Those will be reported missing.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.request
from pathlib import Path

# hub_dataset `name` -> target CSV filename (only the non-obvious ones; else lower()).
SPECIAL = {
    "SP_Game_Log": "sp_gamelog",
    "PALS": "metrics_pals",
    "OOR": "metrics_oor",
}


def load_env(env_path: Path) -> dict:
    out = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def get(base: str, key: str, path: str):
    req = urllib.request.Request(
        base.rstrip("/") + "/rest/v1/" + path,
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def write_csv(rows: list[dict], dest: Path) -> int:
    if not rows:
        dest.write_text("", encoding="utf-8")
        return 0
    # union of keys preserves columns even if rows are ragged
    cols: list[str] = []
    seen = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in cols})
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True, help="path to a .env with SUPABASE_URL/KEY")
    ap.add_argument("--out", required=True, help="output data dir (set MLBMA_DATA_DIR here)")
    args = ap.parse_args()

    env = load_env(Path(args.env))
    url, key = env.get("SUPABASE_URL", ""), env.get("SUPABASE_KEY", "")
    if not url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_KEY missing in the .env")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    index = get(url, key, "hub_dataset?select=name,row_count,updated_at&order=name")
    print(f"hub_dataset has {len(index)} datasets; materializing -> {out}")
    total = 0
    for meta in index:
        name = meta["name"]
        full = get(url, key, f"hub_dataset?name=eq.{urllib.parse.quote(name)}&select=rows")
        rows = full[0]["rows"] if full and isinstance(full[0].get("rows"), list) else []
        fname = SPECIAL.get(name, name.lower()) + ".csv"
        n = write_csv(rows, out / fname)
        total += n
        print(f"  {name:<30} -> {fname:<28} ({n} rows)")
    print(f"done: {total} rows across {len(index)} files.")

    # report the daily-slate files the model still needs but hub_dataset lacks
    need = ["today_matchups.csv", "today_weather.csv", "today_lineups.csv",
            "game_results.csv", "savant_team_leaderboard.csv", "sp_standard.csv"]
    missing = [n for n in need if not (out / n).exists()]
    if missing:
        print("\nSTILL MISSING (pipeline same-day run / not in hub_dataset):")
        for m in missing:
            print("  -", m)


if __name__ == "__main__":
    import urllib.parse  # noqa: E402 (kept local to stay stdlib-simple)
    main()
