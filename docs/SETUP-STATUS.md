# MLB MODEL — Operational Status

> **Historical setup record.** Current runtime and gate status are documented in
> `governance/IMPLEMENTATION-STATUS-2026-06-27.md`. The daily pipeline no longer requires
> either legacy repository.

Last verified: 2026-06-26. The two betting repos now run **end-to-end on live data into one
unified Supabase warehouse**. Nothing in the mlbma pipeline or the betting-brain vault was modified.

## What's wired and working

| Component | Status | Notes |
|---|---|---|
| **Odds API** | ✅ live | key in both repos' `.env`; verified (496/500 quota) |
| **Kalshi** | ✅ keyless | public API, used by prediction_markets.py |
| **MLB Stats API** | ✅ keyless | new slate builder (`build_today_matchups.py`) — 15 games/day |
| **Supabase warehouse** | ✅ unified | mlbma project `mvxjcfriirguhjujurhf`; 52 tables/views |
| **Python 3.12 venvs** | ✅ both repos | `.venv/` in each (pandas 3.0.3, requests, psycopg2) |
| **Pipeline features** | ✅ from Supabase | `hub_dataset` → 36 CSVs via `hub_to_csv.py` (no Windows path) |
| **sharp_tracker** | ✅ end-to-end | live odds → de-vig (29 books incl. Pinnacle) → `sharp_signals`/`sharp_observations` |
| **bet_evaluator** | ✅ end-to-end | expected-runs model → `model_predictions` (logged a PASS verdict correctly) |
| **game_results / outcomes** | ✅ ingested | MLB Stats API finals → `game_results.csv` (real anchors) + `game_outcomes` (183 games); settlement path verified |
| **Kalshi closing lines** | ✅ backfilled | 451 settled games → `prediction_market_snapshots` |
| **market_edge profit scan** | ✅ live | surfaces `steam up ≥4pt` +28.2% ROI/u (95% LB +9.4%, n=110, FDR-survives); fades correctly rejected |
| **calibration views** | ✅ populated | `v_open_vs_close_brier` (n=451: open 0.250 vs close 0.244), `v_pm_calibration` reliability table |

> ⚠️ The `steam up ≥4pt` finding is in-sample on n=110 — needs Deflated-Sharpe/PBO + out-of-sample
> validation (plan §6) before real-money confidence. Strong hypothesis, not proven edge.

Warehouse now holds (one project): `hub_dataset` 36, `projection_snapshots` 30 (pipeline side) +
`teams` 30, `games` 198, `game_outcomes` 183, `sharp_signals` 5, `sharp_observations` 8,
`model_predictions` 1 (betting side).

**Model anchors are now data-driven** (last 14d of finals): home_winp 0.524, league_runs 4.63,
margin_sd 4.56 — replacing config defaults. Settlement grades sharp observations once their games go
final (today's settle tonight after a re-run).

## Daily refresh — one command

```bash
bash /Users/chase/Projects/mlb-model/refresh.sh
```
Runs: materialize features (Supabase `hub_dataset` → CSVs) → build today's slate (MLB Stats API)
→ seed `teams`+`games` → run `sharp_tracker` (live odds → Supabase).

Single-bet eval (example):
```bash
cd /Users/chase/Projects/SCL/_github-repos/bet-evaluator
.venv/bin/python bet_evaluator.py --game "PHI@NYM" --market ml --side PHI --odds -135 --no-write
```

## Helper scripts (in this planning folder — outside both repos)

- `hub_to_csv.py` — Supabase `hub_dataset` → the CSV layout the model reads (read-only).
- `build_today_matchups.py` — MLB Stats API probables + warehouse FIP/OSI → `today_matchups.csv`.
- `seed_warehouse.py` — upsert `teams` + today's `games` (FK targets for signals/predictions).
- `refresh.sh` — chains the above + `sharp_tracker`.

## Known gaps / honest caveats

1. **Daily-slate fields not in `hub_dataset`:** `today_weather`, `savant_team_leaderboard`, `sp_standard`
   (now handled: `game_results` is built from MLB Stats API). The model degrades gracefully (neutral
   weather; Savant K/BB modifier skipped). To restore: the pipeline's same-day run, or add a weather API.
2. **Reference features are from 2026-06-22** (last `hub_dataset` update). FIP/OSI joins use that snapshot;
   a few rookies (e.g. Steven Cruz, Reynaldo López) have blank FIP → treated as neutral. Re-run the pipeline
   export to refresh `hub_dataset`.
3. **Betting history not migrated.** The empty betting tables here fill going forward; the prior
   settled-contract sample lives in the separate "betting-brain" project (migration is a later choice).
4. **Analytical views** (`v_sharp_edge_ranked`, etc.) need settled/accumulated data before they surface rows.
5. **OSI is a team-level proxy** (from `team_profiles` home/away split), not the pipeline's exact
   lineup-vs-SP matchup OSI. Good enough as a prior; the pipeline value is more precise when available.

## Next steps (per the strategic plan §7)

- Scaffold the unified `mlb-model` repo and move this glue (`hub_to_csv`, slate builder, seeder) into a
  proper `sources/` package; promote `refresh.sh` to a CLI subcommand.
- Add `game_results` ingestion (MLB Stats API finals) to enable settlement, CLV, and the calibration views.
- Then Phase 3 paper-trading ledger.
