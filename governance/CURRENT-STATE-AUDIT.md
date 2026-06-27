# Current-State Audit — MLB MODEL

Version 1.0.0 · 2026-06-26 · evidence-based (verified by running the code, querying the
warehouse, and reading source — **not** inferred from filenames or docs).

Scope audited: bet-evaluator, sharp-money-tracker, the unified glue (mlbmodel/sources),
the Supabase warehouse (project `mvxjcfriirguhjujurhf`), and the MLBMA pipeline outputs as
consumed. **Betting Brain** (the Obsidian vault) and the **MLBMA pipeline internals** are
NOT on this machine and were audited only via their consumed outputs (CSV contract + the
`hub_dataset` export) — flagged below as not-directly-inspectable.

---

## 1. Verified current-state architecture

```
 SOURCES (live, verified)                WAREHOUSE (Supabase, 1 project)        CONSUMERS
 ─ The Odds API  ──┐                      52 tables/views:                       ─ sharp_tracker.py
 ─ Kalshi (candles)─┤── normalize ──▶     pipeline side: hub_dataset(36),        ─ bet_evaluator.py
 ─ MLB Stats API ──┤                       projection_snapshots(30)              ─ market_edge.py (scan)
 ─ hub_dataset ────┘                      betting side: teams(30) games(198)     ─ settle_sharp.py
   (pipeline export)                       game_outcomes(183) sharp_signals(5)   ─ analytical views
                                           sharp_observations(7) model_pred(1)
                                           prediction_market_snapshots(451)
```

**Data flow verified end-to-end this session:** MLB Stats API (slate + finals) + hub_dataset
(features) + Odds API (prices) → expected-runs model / de-vig+steam engine → warehouse →
market_edge scan + calibration views. One command (`refresh.sh`) runs the full daily chain.

---

## 2. Capability & maturity assessment (evidence classification)

| Capability | Classification | Evidence |
|---|---|---|
| Expected-runs model (`bet_evaluator`) | **Implemented & verified** | Ran PHI@NYM → 59.3% vs 57.5%, PASS, logged to `model_predictions`. Transparent; self-labels "uncalibrated prior". |
| De-vig + sharp/soft + steam (`sharp_tracker`) | **Implemented & verified** | Ran live: 30 books, 3–5 signals + observations written to Supabase. |
| Profit scan: ROI-at-entry, bootstrap CI, **BH-FDR** (`market_edge`) | **Implemented & verified** | Ran on 451 settled: `steam up ≥4pt` TRADEABLE (+28.2%/u, LB +9.4%, n=110); fades rejected. |
| Kalshi closing lines (candlesticks) | **Implemented & verified, PIT-clean** | `_movement_stats` filters to **pre-first-pitch** candles; 451 clean lines ingested. |
| Quant metrics: Brier, log-loss, Wilson, bootstrap, SPRT, Kelly | **Implemented & verified** | `quant_analysis.py` / `quant_review.py` (two copies). |
| Calibration views (Brier open/close, price-bucket reliability) | **Implemented & verified** | `v_open_vs_close_brier` n=451 (open 0.250 / close 0.244); `v_pm_calibration` live. |
| Model anchors from real finals | **Implemented & verified** | `game_results.csv` → home_winp 0.524, league_runs 4.63 (was config defaults). |
| Unified warehouse (pipeline + betting in one project) | **Implemented & verified** | Schema applied additively; projection data intact. |
| Settlement of **betting** signals | **Implemented but unverified** | `settle_sharp` runs but 0 graded (today's games not final; no settled betting track record yet). |
| 30 analytical views (`v_sharp_edge_ranked`, etc.) | **Partially implemented** | Most return 0 rows — scaffolding awaiting settled/accumulated data. |
| Point-in-time integrity | **Partial** | Candlestick path clean; `backfill_history` self-flags prices as NOT clean (line 206 TODO). |
| OSI in today's slate | **Approximation (documented)** | Team-level `team_profiles` OSI used as proxy for pipeline matchup OSI (I built the slate builder). |
| Manufactured-arb state machine, hedge engine | **Documented but absent** | Designed in `PROFIT-PRIORITY.md`; no code. |
| Paper-trading ledger, positions, postmortem | **Documented but absent** | Plan §3; no code. |
| Walk-forward / purged CV, **Deflated-Sharpe / PBO**, isotonic recalibration | **Documented but absent** | Mentioned in docs only; not in code (BH-FDR is the only multiple-testing control present). |
| Tests | **Absent** | 0 test files, no pytest/unittest in either repo. |
| CI / drift detection / champion-challenger / model registry workflow | **Absent** | No `.github/`, no drift/registry code; `model_versions` table exists but no registry process or model cards. |
| `steam up ≥4pt` edge | **Experimental** | In-sample segment scan, n=110, no out-of-sample / DSR yet. |

**Not directly inspectable** (audited via outputs only): Betting Brain vault logic; MLBMA
pipeline transformations/feature generation (consumed via `hub_dataset` + CSV contract).

---

## 3. Compliance audit against the charter (prompts 1–2)

| Charter standard | Status | Note |
|---|---|---|
| Point-in-time data integrity | **Partial** | Candlestick clean; backfill_history unclean (flagged); model features from a static 06-22 snapshot. |
| Data provenance & licensing | **Gap** | No license/provenance manifest; sources are API-ToS-bound (Odds API, Kalshi, MLB Stats API all permit this use). |
| Reproducibility | **Partial** | Deterministic `game_pk`, seeded RNG in scans; **no experiment manifests, no pinned data hashes, no env lockfile beyond requirements.txt**. |
| Feature acceptance / leakage prevention | **Gap** | No formal feature acceptance gate; leakage prevented ad hoc (candlesticks) not by policy/test. |
| Sample-size requirements | **Partial** | `market_edge --min-n 30` enforced; not applied per-market elsewhere. |
| Multiple-hypothesis correction | **Implemented** | BH-FDR in `market_edge`. **DSR/PBO for strategy selection absent.** |
| Uncertainty & calibration | **Partial** | Bootstrap CIs + Brier present; isotonic recalibration absent; model self-labels uncalibrated. |
| Causal vs associative | **Gap** | All current signals associative; no causal framework or labeling. |
| Backtest / walk-forward | **Gap** | Segment scan only; no walk-forward / purged CV / out-of-sample split. |
| Market-price & vig handling | **Implemented** | De-vig (two-sided), ROI at entry net of vig, CLV captured. |
| Model promotion / rollback | **Gap** | No registry workflow, no champion-challenger, no rollback procedure. |
| Bio/medical-data boundaries | **N/A yet** | No biomechanics data ingested; boundary policy must precede it. |
| Explainability / auditability | **Partial** | Model is transparent + worded; warehouse is timestamped/versioned; no formal audit log of decisions. |
| Security / access control | **Gap** | service_role key in `.env` (gitignored ✓) but used for reads too; no least-privilege (anon key unused). |
| Responsible risk communication | **Partial** | Honest-empty + "why this could be wrong" in design; READMEs carry a stale +47.9% headline. |
| Model retirement | **Gap** | No deprecation/retirement policy. |
| Research documentation | **Partial** | Strong design docs (PROFIT-PRIORITY, plan); no per-signal research records. |

---

## 4. Strengths that must be preserved (do not replace without evidence)

1. **`market_edge` discipline** — ROI-at-entry, bootstrap CI, BH-FDR, **honest-empty**. This is
   the scientific core; extend (add DSR/PBO/walk-forward), never weaken.
2. **Transparent expected-runs model** — interpretable, self-aware about being an uncalibrated
   prior. Preserve as the baseline every future model must beat.
3. **Point-in-time candlestick closing lines** — the clean CLV backbone. Preserve the
   pre-first-pitch filter as an invariant (make it a test).
4. **Unified, versioned warehouse** — `metric_version`/`model_version` stamps, idempotent schema,
   timestamped snapshots. Preserve as the system of record.
5. **De-vig / sharp-consensus engine** — correct two-sided de-vig, sharp-book set, steam logic.
6. **Honest-empty + "why this could be wrong" philosophy** — the cultural strength; encode it as
   a default in the decision layer.

---

## 5. Critical gaps & unsupported claims

**Critical gaps (ranked):**
1. **Zero automated tests / CI** — nothing enforces correctness or the invariants above. (Required)
2. **No out-of-sample / walk-forward / DSR-PBO** — segment findings are in-sample; selection bias
   uncontrolled at the strategy level. (Required) **[Now measured]** The DSR guard added this session
   (`mlbmodel/quant/selection.py`), run on the live 451-game scan, shows the **best-Sharpe segment
   reaches DSR ≈ 0.61 and FAILS the 0.95 gate** — i.e. no current segment survives selection-bias
   correction. The `market_edge` "TRADEABLE" label (ROI-LB + Kelly + BH only) is therefore not yet
   sufficient for promotion; DSR/PBO must gate it.
3. **No model registry / promotion / rollback / champion-challenger** — no governed way to advance
   a model without destabilizing validated behavior. (Required)
4. **No per-signal research lifecycle records** — signals can't be traced to hypothesis/mechanism. (Required)
5. **No drift detection / scheduled recalibration / monitoring.** (Recommended)
6. **Point-in-time discipline is partial** — features from a stale snapshot; `backfill_history`
   unclean; no PIT policy/test. (Required)
7. **Security**: single service_role key for read+write; no least-privilege. (Recommended)

**Unsupported / stale claims to correct:**
- README "+47.9% ROI underdog+steam" — from an old, larger, different-project sample; the current
  reproducible scan shows that exact segment at **n=11 (insufficient)**. Mark as historical/unverified.
- The 30 analytical views imply analysis breadth, but **most return 0 rows** — they are scaffolding,
  not evidence of capability.
- Any "most advanced" framing — unsupported until demonstrated via the validation gates.
- OSI in the slate is a **proxy**, not the pipeline's matchup OSI — must be labeled wherever surfaced.
