# MLB MODEL

Unified MLB research and betting decision-support platform. It is paper-trading and
research software, not an auto-betting system and not a promise of profit.

## Current Authority

The active runtime now lives in this repository:

- MLBMA dataset materialization and slate/results ingestion
- transparent expected-runs baseline with exact factor lineage
- paired, book-level de-vigged market consensus
- sharp-versus-soft market observations
- value and risk assessment
- executable-entry walk-forward validation
- DSR/PBO/OOS promotion gate
- slate, matchup, market, pitcher-prop research, paper portfolio, results, and research
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

GitHub Pages builds `deployment_data/` into a static research dashboard through
`.github/workflows/deploy-pages.yml`. The hosted preview deliberately disables live odds and
warehouse access, displays that limitation in the interface, and cannot issue a wager action.

## Verify

```bash
ruff check mlbmodel tests
pytest -q
```

## Daily Pipeline

`refresh.sh` materializes MLBMA data, creates the slate, ingests finals, seeds the
warehouse, collects paired odds, publishes sharp observations, settles outcomes, and runs
the blocking promotion gate. It no longer shells into either legacy repository.

Before enabling executable-entry research, apply
`migrations/0001_executable_market_signals.sql`. Historical rows without a signal-time
entry price remain intentionally ineligible.

Apply `migrations/0002_paper_portfolio.sql` to enable the Portfolio view. It tracks paper
positions and correlated exposure only; sizing remains zero until the promotion gate passes.

## Governance

The versioned charter and migration evidence live in `governance/`. Governance documents
describe standards; tests and pipeline gates determine what is actually enforced.
