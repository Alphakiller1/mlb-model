# Forensic Integration Verification — MLB MODEL

> **Historical audit, superseded 2026-06-27.** Its movement-at-open OOS result was
> invalidated because `delta = close - open` was used to select a position priced at the
> opening line. The unified gate now requires `signal_time`, `signal_delta`, and
> `entry_prob`; legacy rows without those fields are ineligible. Do not cite the ROI claims
> below as tradable evidence. See `IMPLEMENTATION-STATUS-2026-06-27.md`.

Version 1.0.0 · 2026-06-26 · evidence-based. Verifies whether the unified model genuinely
builds on Betting Brain, MLBMA, Sharp Money Tracker, and Bet Evaluator — through code, data
lineage, schemas, and **reproducible point-in-time out-of-sample tests run this session**, not
documentation or shared names. Complements the governance set (Constitution, Audit, Advancement,
Roadmap); this doc adds the lineage matrices, ablation evidence, and the decision-engine spec.

---

## 1. Executive verification verdict

**The "unified model" is an integration + governance LAYER over the preserved source systems —
not a reimplementation.** Verified facts:
- It **consumes MLBMA correctly** (hub_dataset → 36 feature CSVs → model; projection_snapshots;
  game_outcomes) — it does not recreate or silently alter pipeline work. ✔
- It **preserves Sharp Money Tracker behavior unchanged** (de-vig, steam, CLV) and, by ablation,
  that movement signal carries **real out-of-sample incremental value** (below). ✔
- **Bet Evaluator runs and logs predictions**, with anchors now data-driven; but it has **no settled
  betting track record yet**, so its predictive value is *unverified OOS*. ◐
- **Betting Brain is NOT inspectable on this machine** (the Obsidian vault is absent). Its
  contribution can only be assessed via the rules already encoded in `bet_evaluator` (win-prob,
  unit tiers) — everything else is **Unverified**. ✗-to-verify
- **No source logic was reimplemented or materially altered** — the repos run as-is, fed from one
  warehouse. The new code (`mlbmodel/`) adds *governance and validation*, not replacement.

**Bottom line:** integration is **real but partial and under-powered**. The strongest validated
behavior (Sharp Money Tracker movement → CLV) is preserved and shows OOS value; the weakest claim
(dog+steam +47.9%) **fails OOS**; Betting Brain integration is **unproven here**.

---

## 2. Current unified-model architecture (verified)

Integration layer = unified Supabase warehouse (52 tables/views) + `mlbmodel/` package
(governance, oddsmath, DSR/PBO, **walk-forward harness**) + glue in `mlbmodel/sources/`
(hub_to_csv, slate builder, finals ingest, seeder) + `refresh.sh`. Source repos
(bet-evaluator, sharp-money-tracker) preserved and fed by the glue. See CURRENT-STATE-AUDIT §1/§2.

---

## 3. Betting Brain logic-lineage matrix

| Capability | Source location | Unified location | Status | Evidence |
|---|---|---|---|---|
| Win-probability model rules | vault `06-Betting-Logic/Win-Probability-Model` (absent here) | `bet_evaluator.model_probabilities` | **Preserved (as encoded)** | code implements expected-runs + base-rate blend; vault itself not inspectable |
| Unit-sizing tiers | vault `Unit-Sizing` | `config.CONFIDENCE_TIERS` + `value_layer` | **Preserved** | tiers present in code |
| Market-edge rationale | vault `Market-Edge-Engine` | `market_edge` | **Preserved** | logic present |
| Handicapping heuristics, matchup analysis, confidence scoring, abstention rules | vault (absent) | — | **Unverified** | cannot inspect the vault on this machine |

**Action:** sync the vault to this machine (read-only) to complete this matrix; until then, treat
non-encoded Betting-Brain logic as **Unverified**, not integrated. **Do not claim Betting-Brain
integration beyond the rules visibly encoded in `bet_evaluator`.**

---

## 4. MLBMA data-lineage & utilization audit

**Consumed (verified):** `hub_dataset` (36 datasets, last updated 06-22) → materialized to CSVs →
`bet_evaluator` features (OSI, FIP, HR9, K%, bullpen) + `pitcher_model_layers`; `projection_snapshots`
(30, live 06-26); `game_outcomes` (183, ingested from MLB Stats API this session).

**Available but UNUSED by the win-prob model (opportunity):**
| Dataset | Rows | Potential use | Status |
|---|---|---|---|
| Pitch_Mix_* (batter/pitcher/team, L14) | ~16k | matchup edge, props | **Unused** by ML model |
| Batter_Splits_* (vsL/R, home/away, recent) | ~2k | totals/props, platoon | **Unused** |
| Reliever_Log (5599) / Bullpen_* | ~5.9k | bullpen fatigue, F5 | **Partially used** (team factor only) |
| Pitching_Score, vs_LHP/RHP | 90 | matchup priors | **Unused** |

**Lineage gaps:** features are from a **static 06-22 snapshot** (point-in-time risk, STD-1); no
per-row provenance/license (STD-2); `today_*` slate not in hub (rebuilt from MLB Stats API).

**Action:** route future predictions/snapshots/decisions/outcomes back through governed MLBMA
contracts (versioned migrations) — see MLBMA governance in ADVANCEMENT-FRAMEWORK §10.

---

## 5. Sharp Money Tracker integration matrix (+ OOS ablation evidence)

| Capability | Source fn | Unified | Status | Evidence |
|---|---|---|---|---|
| De-vig (two-sided) | `sharp_tracker.devig_game` | same, fed by unified warehouse | **Preserved** | ran live; sums to 1 |
| Sharp-vs-soft divergence | `sharp_signals_for_game` | same | **Preserved** | live signals produced |
| Line-movement / steam | candlestick `_movement_stats` (PIT-clean) | same | **Preserved & verified PIT** | pre-first-pitch filter |
| CLV tracking | `prediction_market_snapshots` + views | same | **Preserved** | v_open_vs_close_brier n=451 |
| ROI/bootstrap/BH-FDR | `market_edge` | preserved + **DSR/PBO added** | **Extended** | `mlbmodel/quant/selection.py` |
| **Movement→outcome predictive value** | line-move logic | **walk-forward OOS** | **Verified incremental** | **OOS: steam ROI +24.2% vs −6.5% no-signal baseline** |
| Reverse-line / stale-price / cross-market / limits | — | — | **Missing** | not implemented |
| Kelly / exposure monitoring | `_kelly` in market_edge | present (not portfolio-level) | **Partial** | no bankroll/exposure engine |

**Reproducible OOS result (this session):** fit steam threshold on earliest 70% by `snapshot_time`,
test on strictly-later 30%. OOS n=32, **win 65.6%, ROI +24.2% net of Kalshi fee, CLV +8.7%**, but
**95% bootstrap LB −10.2%** (under-powered). Ablation OOS: no-signal −6.5% → steam +24.2% (signal
adds value); liquidity filter redundant; **dog+steam collapses to n=1 (old +47.9% claim is overfit).**

---

## 6. Bet Evaluator integration assessment

| Item | Status | Evidence |
|---|---|---|
| Expected-runs model runs in unified env | **Verified** | PHI@NYM 59.3% vs 57.5% → PASS, logged to `model_predictions` |
| Anchors data-driven | **Verified (extended)** | from `game_results.csv` (home_winp 0.524, league_runs 4.63) |
| Prediction logging to warehouse | **Verified** | `model_predictions` row written |
| OOS predictive value / calibration of the model itself | **Unverified** | 1 prediction, none settled; no model OOS yet |
| Incremental value over sharp-consensus | **Unverified** | requires settled predictions + ablation |

---

## 7. Behavioral parity & regression-test plan

Now enforced (this session): odds-math invariants, devig=1, DSR/PBO behavior, PIT split / no-leakage,
execution-fee sign — **13 tests, CI green**. To add (Required): golden-file parity for `bet_evaluator`
output (pin a fixture game), de-vig parity vs `sharp_tracker`, candlestick PIT-filter assertion against
live data, calibration-no-regression. Each becomes a CI gate (Constitution rollout step 1–2).

---

## 8. Source-system ablation plan

**Run this session (within-strategy):** no-signal vs steam vs +liquidity vs +dog — see §5.
**True source ablation (BLOCKED, honest):** "performance without Betting Brain / MLBMA / Sharp"
requires (a) a **unified prediction that fuses features from each source** and (b) a **settled
betting track record** to score. Neither exists yet (model and sharp engine are separate; 0 settled
betting predictions). **Acceptance:** once R7 (daily settle) accrues ≥ N settled predictions and a
fused model exists, run leave-one-source-out walk-forward and report incremental log-loss/CLV/ROI per
source. Until then, source-ablation claims are **not supportable** and must not be made.

---

## 9. Missing, weakened, or incorrectly altered capabilities

| Capability | Status | Impact | Action | Test | Risk/rollback |
|---|---|---|---|---|---|
| dog+steam "+47.9% ROI" | **Weakened/refuted OOS** | overconfidence | mark historical; require OOS+DSR | walk-forward gate | none (doc) |
| Reverse-line, stale-price, cross-market, limits | **Missing** | misses short-term edges | implement as gated signals | per-signal OOS | flag-off |
| Portfolio/bankroll/exposure engine | **Missing** | drawdown control | build staking module | drawdown test | flag-off |
| Walk-forward / OOS | **Now present (new)** | enables promotion | extend to all markets | CI | n/a |
| Betting-Brain non-encoded logic | **Unverified/absent** | unknown | sync vault read-only | lineage complete | none |
| Provenance/licensing, audit log | **Missing** | governance | schema migration 0003 | schema test | additive |

---

## 10. Unsupported claims & hidden risks

- "+47.9% dog+steam" — **refuted OOS (n=1)**. Remove/annotate. (Evidence: §5 ablation.)
- "Most advanced" — unsupported until gates pass. (Constitution STD-16.)
- 30 analytical views imply breadth — **most return 0 rows**; scaffolding, not capability.
- **Hidden risks:** features from a stale 06-22 snapshot (PIT); OSI is a team-level proxy; betting
  history split across two Supabase projects; secrets pasted in chat (rotate); single service_role key;
  ~30-day depth + OOS n=32 → **insufficient statistical power for any promotion today**.

---

## 11. Profitability decision-engine specification

Builds on ADVANCEMENT-FRAMEWORK §5/§11. Every recommendation must emit ALL of:
market & selection · available price · fair price & probability (with model_version) · vig-free
consensus · EV (net of vig + execution fee) · credible/confidence interval · **max acceptable entry
price** · suggested risk allocation (fractional-Kelly w/ flat floor) · primary supporting signals ·
conflicting signals · data timestamp · expected settlement horizon · **invalidating conditions** ·
and a decision ∈ {BET, MONITOR, HEDGE, REDUCE, ABSTAIN}. **Default = ABSTAIN** unless all required
gates (§ gates) pass; honest-empty is success, not failure.

Opportunity score inputs (interpretable, pre-ML): model fair prob, market-implied, vig-free consensus,
executable price, EV-after-cost, uncertainty (interval width), edge stability (OOS), expected edge
decay (time-to-first-pitch), liquidity/limits, news/lineup risk, correlation with open exposure,
bankroll impact, model/data freshness.

---

## 12. Short-term opportunity framework

Drivers verified available: line movement/steam (Kalshi candles, PIT-clean), de-vig divergence,
liquidity/volume, time-to-first-pitch (MLB Stats API). To add: lineup/scratch + bullpen-availability
catalysts (MLB Stats API), weather, stale-line detection across books. Objective: capture CLV before
the close; **act at the open** (empirically: open Brier 0.250 vs close 0.244). Gate: only when the
movement signal + freshness + liquidity pass and bootstrap LB > hurdle OOS.

---

## 13. Long-term portfolio & bankroll framework

Optimize calibration + repeatable EV + bankroll growth + drawdown control, NOT wager count or
headline ROI. Components to build: per-market calibration tracking (isotonic), fractional-Kelly with
flat-unit floor + per-bet/exposure caps, correlation-aware staking (correlated books/markets),
regime conditioning (month/park/weather), champion-challenger model rotation, scheduled recalibration.
Primary metrics: log loss, Brier, CLV, max drawdown, profit/bankroll-hour, OOS walk-forward.

---

## 14. MLBMA publishing & audit contract

Per ADVANCEMENT-FRAMEWORK §10: publish source observations, normalized data, features (PIT-stamped),
predictions, fair probabilities + intervals, simulations, market snapshots, decisions/abstentions,
outcomes, CLV/ROI, research evidence, data-quality events, model versions, and an immutable audit log
— all via versioned, additive migrations. Preserve existing contracts (`model_predictions`,
`game_outcomes`, `prediction_market_snapshots`, `hub_dataset`).

---

## 15. Prioritized remediation roadmap

See ROADMAP-AND-RISK §12. Re-prioritized by this audit's evidence:
1. **R7 daily settle loop** — grow the settled betting sample (the binding constraint on every claim).
2. **Extend walk-forward to ML/totals/runline/F5/props + DSR/PBO gate** (new harness is the seed).
3. **Sync Betting-Brain vault read-only** to complete the lineage matrix.
4. **Provenance + audit-log migration (0003).**
5. **Staking/exposure engine** for long-term drawdown control.
6. Then experimental signals (reverse-line, stale-price) as gated challengers.

---

## 16. Acceptance criteria for "integration complete"

Integration is **complete** only when ALL hold:
1. Lineage matrices (§3–6) have **no Unverified rows** (Betting-Brain vault inspected).
2. Each source's **incremental value measured by leave-one-out walk-forward** on a settled sample
   (log-loss/CLV/ROI), reported with bootstrap CIs.
3. Every promoted signal/model passes its **per-market gate + DSR/PBO + OOS LB > hurdle**.
4. MLBMA publishes all required layers via versioned contracts with an immutable audit log.
5. Parity/regression tests green in CI for every preserved behavior.
6. A decision-engine output carries all §11 fields and defaults to ABSTAIN.

**Today: criteria 1–6 are NOT met.** The platform is honestly at "integration real but partial,
evidence under-powered." The new harness + governance make the remaining work *measurable*.
