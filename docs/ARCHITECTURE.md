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
| `mlbmodel/report/` | Shell (`app.py`, `shell.py`, `views.py`, `matchup.py`, `decision.py`, `chase_theme.py`, `interactive.py`, `top_leans.py`, `html_fmt.py`) |
| `mlbmodel/trends/` | Situational trend engine (Trends view) |
| `mlbmodel/storage/` | Supabase REST reader/writer |

## Report shell (8 views)

Nav order in `shell.NAV`: **Today · Matchups · Trends · Markets · Props · Portfolio · Results · Research**.

Matchups: featured game renders full terminal; other games show compact summary with full terminal in `<template>` hydrated on first `switchGame()`.

Markets: `decide()` thresholds default to fixed floors; when ≥25 settled sharp leans exist, `thresholds_from_leans()` calibrates STRONG/BET edge floors from realized hit rates.

## Supabase tables

| Table | Writer | Reader |
|-------|--------|--------|
| `model_leans` | Pages build (`record_leans`) | Results view, `settle_leans` |

Lean sources recorded at each build (idempotent upsert to `model_leans`):

| Source | What gets logged |
|--------|------------------|
| `sharp` | Sharp+model fusion plays (STRONG/BET/LEAN) |
| `matchup` | Full-game markets with positive model edge or BET/MONITOR state |
| `f5` | First-5 markets (total, ML) with edge or actionable state |
| `prop` | Sportsbook pitcher props with edge ≥0.5pt or BET/MONITOR |
| `prizepicks` / `underdog` / `sleeper` | Pick'em lines incl. fantasy score (OVER/UNDER vs model) |
| `projection` | Trusted pitcher projection means (K, ER, fantasy, F5_ER, etc.) |
| `game_outcomes` | `build_game_results` | Settlement |
| `sharp_observations` | `market/collect` | Research / settle |
| `paper_positions` | (manual / future execution) | Portfolio view |

## Deploy

`.github/workflows/deploy-pages.yml` on `main`: sync MLBMA → fetch odds/pick'em → `build_app --no-fetch` → post-build smoke (view presence + HTML size budget) → GitHub Pages.

Requires `SUPABASE_URL` + `SUPABASE_KEY` secrets for lean recording. Apply migrations `0003` + `0004` on the shared project.

## Settle

`.github/workflows/settle.yml` (07:00, 13:00, 17:00, 23:00 UTC): `build_game_results` **must succeed** before `market.settle` runs; then `check_pending_leans.py` logs any remaining unsettled rows.

## Design note

`mlbmodel/report/static/mlbma_backgrounds.css` is an **MLB Model fork** (gradient-only). Do not overwrite from `mlbma-pipeline/dashboard/` — chase-analytics.com keeps stadium photo backgrounds.

Major panels use **`.ca-board`** from the vendored design system (opaque broadcast boards). Neon section icons are vendored SVGs in `static/assets/icons/` (sync via `scripts/sync_chase_icons.py`); `publish_assets()` copies them beside `index.html` on build.

Resync dashboard CSS with `python scripts/sync_chase_css.py --source ../mlbma-pipeline --check` (or `--write`).
