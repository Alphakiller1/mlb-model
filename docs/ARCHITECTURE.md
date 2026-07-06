# MLB Model — Architecture

Unified research product: ingest MLBMA data → expected-runs model → market/prop pricing → self-contained HTML report → optional Supabase lean tracking.

## Data flow

```
mlbma-pipeline (compute + hub mirror)
        │
        ▼
sync_mlbma.py  ──►  data/ CSVs + live_context.json + mlbma_sync.json
        │
        ▼
DataRepository.load_game()  ──►  GameData (+ optional arsenal from pitcher board)
        │
        ├──► model_probabilities()     ──► slate / matchup win% & totals
        ├──► build_pitcher_board()     ──► 30k-draw prop sims
        └──► load_board() / collect    ──► sharp vs soft, prop prices
        │
        ▼
build_app()  ──►  index.html (GitHub Pages)
        │
        ├──► record_leans()  ──►  Supabase model_leans (when secrets set)
        └──► settle.yml      ──►  grade_leans() after finals
```

## Package map

| Module | Role |
|--------|------|
| `mlbmodel/sources/` | Hub sync, live context, game results, pitcher box scores |
| `mlbmodel/baseball/` | Repository, features, `model_probabilities`, arsenal attach |
| `mlbmodel/market/` | Odds board, sharp collection, value layer, pick'em, settle |
| `mlbmodel/props/` | Pitcher projection engine |
| `mlbmodel/leans/` | Record at build, grade after finals, calibration |
| `mlbmodel/quant/` | Promotion gate (blocks executable BET) |
| `mlbmodel/report/` | Chase-themed shell (`app.py`, `shell.py`, `views.py`, `matchup.py`, `decision.py`) |
| `mlbmodel/storage/` | Supabase REST reader/writer |

## Supabase tables

| Table | Writer | Reader |
|-------|--------|--------|
| `model_leans` | Pages build (`record_leans`) | Results view, `settle_leans` |
| `game_outcomes` | `build_game_results` | Settlement |
| `sharp_observations` | `market/collect` | Research / settle |
| `paper_positions` | (future execution) | Portfolio view |

## Deploy

`.github/workflows/deploy-pages.yml` on `main`: sync MLBMA → fetch odds/pick'em → `build_app --no-fetch` → GitHub Pages.

Requires `SUPABASE_URL` + `SUPABASE_KEY` secrets for lean recording. Apply migrations `0003` + `0004` on the shared project.

## Design note

`mlbmodel/report/static/mlbma_backgrounds.css` is an **MLB Model fork** (gradient-only). Do not overwrite from `mlbma-pipeline/dashboard/` — chase-analytics.com keeps stadium photo backgrounds.

Resync other vendored CSS with `python scripts/sync_chase_css.py --source ../mlbma-pipeline --check` (or `--write`). CI runs `--check` when `mlbma-pipeline` is available.
