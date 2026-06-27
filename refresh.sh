#!/usr/bin/env bash
# Governed, self-contained daily refresh for the unified MLB Model.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV="${MLBMODEL_ENV:-$REPO/.env}"
DATA="${MLBMA_DATA_DIR:-$REPO/data}"
PYTHON="${PYTHON:-python3}"

if [[ ! -f "$ENV" ]]; then
  echo "missing $ENV; create it from env.template" >&2
  exit 1
fi

export MLBMA_DATA_DIR="$DATA"

echo "==> 1/7 materialize versioned MLBMA feature datasets"
"$PYTHON" -m mlbmodel.sources.hub_to_csv --env "$ENV" --out "$DATA"

echo "==> 2/7 build today's slate with collision-safe game identifiers"
"$PYTHON" -m mlbmodel.sources.build_today_matchups --out "$DATA"

echo "==> 3/7 ingest recent finals and update empirical anchors"
"$PYTHON" -m mlbmodel.sources.build_game_results --days 14 --out "$DATA"

echo "==> 4/7 seed teams and games"
"$PYTHON" -m mlbmodel.sources.seed_warehouse --data-dir "$DATA"

echo "==> 5/7 collect paired odds and sharp-vs-soft observations"
"$PYTHON" -m mlbmodel.market.collect --data-dir "$DATA"

echo "==> 6/7 settle eligible sharp observations"
"$PYTHON" -m mlbmodel.market.settle

echo "==> 7/7 enforce the executable-entry promotion gate"
"$PYTHON" -m mlbmodel.quant.promotion_gate --env "$ENV"

echo "==> refresh complete"
