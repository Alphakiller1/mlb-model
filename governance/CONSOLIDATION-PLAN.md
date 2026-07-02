# Consolidation Program — make MLB MODEL the single canonical home

> **Status update 2026-06-27:** the active expected-runs, pricing, sharp collection,
> settlement, reporting, and promotion runtime has moved into this repository. This plan's
> original Phase 2 matrix is retained as migration history. Current cutover status is in
> `IMPLEMENTATION-STATUS-2026-06-27.md`; legacy repositories remain parity references and
> must not be archived yet.

Version 1.0.0 · 2026-06-26. Governs the migration that makes `bet-evaluator` and
`sharp-money-tracker` safely obsolete. **Working principle: no broad rewrite; preserve validated
behavior; nothing is declared obsolete until the decommissioning gates pass.** This plan covers the
14 charter deliverables; the forensic capability inventory lives in
[VERIFICATION-AUDIT.md](VERIFICATION-AUDIT.md) (§3–6 lineage matrices) and is referenced, not duplicated.

## Status headline
**Migration is at Phase 2 (matrix + first verified migration), NOT complete.** One capability
(odds math) is **migrated and verified by an automated parity test** (`tests/test_parity_oddsmath.py`,
0 mismatches / 2000 inputs). Everything else is inventoried with a disposition below. **No repo is
obsolete.** Decommissioning gates: **0 of 12 met.**

## 1–3. Source → unified traceability matrix (dispositions)

| Capability | Source (file·symbol) | Unified location | Status |
|---|---|---|---|
| Odds math (american/implied/decimal, prob→american) | bet_evaluator, market_data, _compat | `mlbmodel/market/oddsmath.py` | **Migrated & verified (parity test)** |
| De-vig two-sided | sharp_tracker.devig_game | `oddsmath.devig_two_way` (core) / legacy engine (full) | **Partially migrated** |
| Expected-runs model | bet_evaluator.model_probabilities | — (runs in legacy) | **Not migrated** (preserved baseline) |
| Value layer (edge/EV/Kelly/tiers) | bet_evaluator.value_layer | — | **Not migrated** |
| Sharp signals / steam / divergence | sharp_tracker | — (runs in legacy) | **Not migrated** |
| ROI/bootstrap/**BH-FDR** scan | market_edge | preserved; **DSR/PBO + walk-forward added** in `mlbmodel/quant`, `backtest` | **Replaced w/ validated improvement** |
| CLV / closing-line capture | prediction_markets candlesticks | warehouse `prediction_market_snapshots` + `mlbmodel/backtest/walkforward` | **Partially migrated** |
| Promotion / selection gate | (none) | `mlbmodel/quant/promotion_gate.py` | **New (no legacy equiv)** |
| Pitcher/matchup/projection layers | board_analytics, pitcher_model_layers | — | **Not migrated** |
| Odds/Kalshi/MLB-StatsAPI ingestion | market_data, prediction_markets, sources/* | `mlbmodel/sources/*` (slate, finals, hub, seed) + legacy fetchers | **Partially migrated** |
| Warehouse schema | schema.sql (both) | unified Supabase (applied) | **Migrated & verified** |
| CLI hub | chase.py | — | **Not migrated** |
| Dashboard / Command Center | command_center.py | rebranded (parallel-run); unified UI TBD | **Partially migrated (visual)** |
| Vault note output | bet_evaluator.write_to_vault | — | **Not migrated** |
| Tests | (none in legacy) | `tests/` (15) + parity | **New** |

## 4. Missing-capability report (must exist in MLB MODEL before cutover)
Expected-runs model, value/Kelly layer, sharp/steam engine, projection layers, ingestion fetchers,
CLI, dashboard, vault output — all still **run in the legacy repos**. These are the migration backlog.

## 5–6. Target architecture & information architecture
Target package boundaries: see [ADVANCEMENT-FRAMEWORK.md §8](ADVANCEMENT-FRAMEWORK.md). Unified IA
(one product, not linked tools): **Research dashboard → Game/Market evaluation → Sharp monitoring →
Opportunity ranking → Props → Projections → Line movement → CLV/results → Portfolio/exposure →
Research evidence → Data/model health → Settings/admin.** Decision-engine output fields + ABSTAIN
default per [VERIFICATION-AUDIT §11](VERIFICATION-AUDIT.md).

## 7. Design-contract compliance → [DESIGN-CONTRACT.md](DESIGN-CONTRACT.md)
Tokens canonicalized; legacy Command Center rebranded (parallel-run). **Gap:** no unified-UI
framework yet — decision required.

## 8. Data & schema migration plan
Unified Supabase warehouse already holds both schemas (applied additively). MLBMA remains the
governed publication layer. All schema changes ship as versioned, **additive** migrations
(`000N_*.sql`); never change a published meaning. Backward-compatible views (`v_*_v2`) for breaking changes.

## 9–10. Parity & visual-regression tests
- **Calculation parity (started):** oddsmath ✓. Next: de-vig, expected-runs (golden fixture game),
  value/EV/Kelly, market_edge segment outputs, CLV — each a `tests/test_parity_*.py` comparing legacy
  vs unified on identical point-in-time inputs, skipping when legacy is archived.
- **Visual regression:** capture Command Center + dashboard screenshots pre/post; assert token
  compliance; add Playwright snapshot tests once the unified UI exists.

## 11. Historical-data migration plan
Two Supabase projects exist (mlbma + betting-brain). Reconcile by: inventory both → map keys
(`game_pk`) → migrate betting history into the unified warehouse via additive upserts → verify counts
and CLV/ROI reconcile → keep the source as read-only archive. **Not yet done.**

## 12. Cutover & rollback
Phased, dependency-aware (charter order 6–10). Run legacy + unified **in parallel**, compare outputs
daily, only cut over a capability when its parity test is green for the parallel window. Rollback =
repoint the consumer/flag to legacy; warehouse is additive so no data rollback needed.

## 13. Legacy-repository archival plan
On cutover: legacy repos → **read-only archives** (GitHub "Archive repository"), README banner
pointing to MLB MODEL, license/attribution/decision-history preserved, no runtime deps remain
(grep the unified system for any import/path/submodule referencing legacy — must be zero).

## 14. Production-readiness / DECOMMISSIONING GATES (current: 0/12 met)
- [ ] Every capability has a recorded disposition — *partial (matrix above; needs completion)*
- [ ] All required capabilities exist in MLB MODEL — **no**
- [ ] Automated parity + regression tests pass — *oddsmath only*
- [ ] Historical data preserved & reconciled — **no**
- [ ] MLBMA contracts validated — *partial*
- [ ] Critical user workflows verified in unified — **no**
- [ ] Visual design follows the contract — *legacy rebranded; unified UI absent*
- [ ] Monitoring & rollback procedures exist — *partial (gate runs daily)*
- [ ] No undocumented runtime deps on legacy — **no (unified still calls legacy engines)**
- [ ] Successful parallel run completed — **no**
- [ ] Docs point exclusively to MLB MODEL — **no**
- [ ] Final exceptions/rejected behavior approved — **no**

**Therefore: bet-evaluator and sharp-money-tracker remain ACTIVE. Do not archive.**

## Next phase (concrete, sequenced)
1. Parity-migrate de-vig + expected-runs (golden fixtures) into `mlbmodel/{market,baseball}`.
2. Wrap the legacy sharp/steam engine behind a `mlbmodel` interface (no logic change) → kills the
   "unified calls legacy directly" dependency once reimplemented + parity-tested.
3. Decide the unified-UI stack; build the IA shell with the design tokens.
4. Reconcile the betting-brain history into the warehouse.
5. Begin the parallel run; track gate status here until 12/12.
