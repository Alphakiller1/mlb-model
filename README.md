# MLB MODEL

Unified MLB research and betting decision-support platform. It is paper-trading and
research software, not an auto-betting system and not a promise of profit.

## Current Authority

The active runtime now lives in this repository:

- MLBMA dataset materialization and slate/results ingestion
- context-aware expected-runs model with exact sequential factor lineage
- paired, book-level de-vigged market consensus
- sharp-versus-soft market observations
- value and risk assessment
- executable-entry walk-forward validation
- DSR/PBO/OOS promotion gate
- official lineup, first-pitch weather, umpire, injury, travel/rest, and probable-pitcher inputs
- 30,000-draw pitcher-prop distributions with pitch-by-pitch opponent response
- slate, matchup, market, pitcher-prop, paper portfolio, results, and research
  interface

Bet Evaluator and Sharp Money Tracker remain read-only parity references until the
remaining historical-reconciliation and parallel-run gates are complete.

## Safety Invariants

- A descriptive statistic is never presented as a model driver.
- A movement strategy needs a point-in-time signal and executable entry price.
- Opposite contracts from the same game remain in the same validation partition.
- Raw implied probabilities are never labeled vig-free.
- An unpromoted strategy cannot produce a `BET` action.
- Missing prices and failed data reads produce visible no-action states.
- A deployed slate must be an exact MLBMA match or visibly use the same live-schedule
  fallback as Chase Analytics.

## Run

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp env.template .env

.venv/bin/python -m mlbmodel.report.app \
  --game NYY@BOS \
  --data-dir /path/to/mlbma/data \
  --out mlb_model_app.html
```

The generated HTML is self-contained except for MLB image/font assets. Open it directly or
serve the directory with a static server.

## Hosted Research Preview

GitHub Pages runs `mlbmodel.sources.sync_mlbma` before every build. It refreshes team,
starter, batter, bullpen, workload, and pitch-mix inputs from MLBMA's public Supabase
mirror, reconciles `Today_Matchups` against the live MLB schedule, and collects the
point-in-time MLB/Open-Meteo game context.

- A current, exact pipeline slate is used directly.
- A stale or mismatched pipeline slate activates Chase Analytics' live-schedule fallback.
- The source, run date, game count, and fallback state are written to `mlbma_sync.json` and
  displayed in the interface.

The workflow accepts an `mlbma-pipeline-complete` repository dispatch and runs hourly as a
fallback after it is merged to the default branch. The public preview has no prop-price
snapshot or betting warehouse credentials, so market reports show `NO MARKET` and cannot
issue a wager action.

## Verify

```bash
ruff check mlbmodel tests
pytest -q
```

## Daily Pipeline

`refresh.sh` materializes MLBMA data, creates the slate, ingests finals, seeds the
warehouse, collects paired odds, publishes sharp observations, settles outcomes, and runs
the blocking promotion gate. It no longer shells into either legacy repository.

The MLBMA pipeline mirrors `Today_Matchups`, `Today_Lineups`, and `Last_Updated` alongside
its research datasets, then dispatches the model Pages workflow after a successful mirror.

Before enabling executable-entry research, apply
`migrations/0001_executable_market_signals.sql`. Historical rows without a signal-time
entry price remain intentionally ineligible.

Apply `migrations/0002_paper_portfolio.sql` to enable the Portfolio view. It tracks paper
positions and correlated exposure only; sizing remains zero until the promotion gate passes.

### Self-tracked leans (`model_leans`)

Apply `migrations/0003_model_leans.sql` on the shared Supabase project. Each Pages build
records model leans (markets, pick'em, props) when `SUPABASE_URL` + `SUPABASE_KEY`
(service role) are set as GitHub Actions secrets on this repo. The nightly
`.github/workflows/settle.yml` job refreshes finals and grades leans; the **Results** view
shows W-L-P, calibration buckets, and by-source hit rates. Without credentials, every view
degrades to an honest empty state — the build never fails.

## Governance

The versioned charter and migration evidence live in `governance/`. Governance documents
describe standards; tests and pipeline gates determine what is actually enforced.
