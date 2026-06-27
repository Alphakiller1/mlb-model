#!/usr/bin/env bash
# refresh.sh — one-command daily refresh for the unified MLB model.
# Pulls pipeline features + recent finals + today's slate, seeds the warehouse,
# runs the sharp tracker (live odds -> Supabase), and settles now-final games.
#
# Usage:  bash refresh.sh
set -euo pipefail

REPO=/Users/chase/Projects/mlb-model
PLAN=/Users/chase/Projects/mlb-model-planning          # local data cache (gitignored)
SRC=$REPO/mlbmodel/sources                             # governed home for the glue
DATA=$PLAN/pipeline_data
SMT=/Users/chase/Projects/SCL/_github-repos/sharp-money-tracker
PY312=/opt/homebrew/bin/python3.12

echo "==> 1/6 materialize pipeline features from Supabase hub_dataset"
$PY312 "$SRC/hub_to_csv.py" --env "$SMT/.env" --out "$DATA" | tail -1

echo "==> 2/6 build today's slate from MLB Stats API"
$PY312 "$SRC/build_today_matchups.py" --out "$DATA" | head -1

echo "==> 3/6 ingest recent finals (model anchors + game_outcomes)"
( cd "$SMT" && .venv/bin/python "$SRC/build_game_results.py" --days 14 | tail -2 )

echo "==> 4/6 seed teams + today's games into the warehouse"
( cd "$SMT" && .venv/bin/python "$SRC/seed_warehouse.py" )

echo "==> 5/6 run the sharp tracker (live odds -> de-vig -> Supabase)"
( cd "$SMT" && .venv/bin/python sharp_tracker.py | tail -12 )

echo "==> 6/7 settle now-final games (grades sharp observations)"
( cd "$SMT" && .venv/bin/python settle_sharp.py | tail -1 )

echo "==> 7/7 promotion gate (Constitution: OOS LB + DSR) — self-enforced, no auto-bet"
PYTHONPATH="$REPO" $PY312 -m mlbmodel.quant.promotion_gate --env "$SMT/.env" 2>&1 | head -3 || true

echo "==> done."
