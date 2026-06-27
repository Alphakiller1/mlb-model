# Roadmap, Migration & Risk — MLB MODEL

Version 1.0.0 · 2026-06-26. Covers required outputs 12–16. Every recommendation is classified
**Required · Recommended · Experimental · Rejected** with evidence, benefit, dependencies,
validation, implementation risk, and rollback.

---

## 12–13. Prioritized advancement roadmap (immediate / medium / experimental)

### Immediate (0–2 weeks) — enforce standards before adding complexity
| ID | Item | Class | Evidence | Benefit | Deps | Validation | Impl risk | Rollback |
|---|---|---|---|---|---|---|---|---|
| R1 | **Test suite + CI** (odds math, devig=1, PIT candle filter, seed determinism, min-n) | **Required** | 0 tests exist today | Locks invariants; enables every gate | none | tests green in CI | low | delete workflow |
| R2 | **DSR / PBO selection guard** on `market_edge` | **Required** | only BH-FDR present; n=110 in-sample finding | Controls selection bias across segments tried | R1 | unit test vs known cases | low | flag off; keep BH-only |
| R3 | **mlb-model package + git** (skeleton + glue as `sources/`, DSR in `quant/`) | **Required** | glue lives loose in planning dir | Governed home; isolates modules | R1 | `pip install -e .`; tests pass | low | keep using loose scripts |
| R4 | **Mark unsupported claims** (READMEs, "+47.9%") | **Required** | reproducible scan shows that segment n=11 | Honest risk comms (STD-16) | none | grep shows annotations | none | n/a |
| R5 | **Least-privilege keys** (anon for reads) | **Recommended** | service_role used for reads | Reduce blast radius | none | reads work w/ anon | low | revert to service_role |

### Medium (2–8 weeks) — the validation backbone
| ID | Item | Class | Evidence | Benefit | Deps | Validation | Impl risk | Rollback |
|---|---|---|---|---|---|---|---|---|
| R6 | **Walk-forward / purged-CV harness** | **Required** | only in-sample scan | OOS truth; promotion input | R1 | reproduces on synthetic | med | scan-only mode |
| R7 | **Daily `refresh.sh` schedule + settle loop** | **Required** | runs manually; 0 settled betting | Builds settled track record + CLV | cron | rows accrue, settle>0 | low | run manually |
| R8 | **Per-market promotion gates** (`gates.yaml`) | **Required** | one global min-n | Right metric per market | R6 | gate blocks bad candidate | med | disable gate |
| R9 | **Model + feature registry, model cards, revalidation dates** | **Required** | `model_versions` table only | Promotion/rollback/retirement | R3 | registry CRUD + card present | med | manual tracking |
| R10 | **Provenance + immutable audit log** (schema migration `0003`) | **Recommended** | timestamps only | Auditability (STD-2,14) | R3 | columns populated | low | additive; drop view |
| R11 | **Isotonic recalibration + per-market reliability gate** | **Recommended** | Brier views only | Calibrated probs | R6 | reliability slope ∈ range | med | use raw probs |
| R12 | **Drift detection + scheduled recalibration + perf attribution** | **Recommended** | none | Catch decay early | R9 | drift alert fires on shift | med | monitoring only |

### Experimental (gated, no production authority until validated)
| ID | Item | Class | Evidence | Benefit | Validation before promotion |
|---|---|---|---|---|---|
| R13 | Manufactured-arb state machine + hedge engine | **Experimental** | designed in PROFIT-PRIORITY | Profit/bankroll-hour | staged-workflow backtest + paper trading |
| R14 | Monte-Carlo game-state simulation | **Experimental** | none | Distributional totals/props | CRPS beats baseline OOS |
| R15 | Pitch/PA models + mixture-of-experts | **Experimental** | none | Granular edge | challenger beats champion OOS |
| R16 | Biomechanics/fatigue context (OpenBiomechanics) | **Experimental** | external dataset | Filter/explainer | STD-13 review; never sole signal |
| R17 | Bayesian updating, regime detection, causal inference | **Experimental** | none | Robustness | additive challenger; labeled |
| R18 | Polymarket cross-venue + executable arb | **Experimental** | absent (verified) | Arb breadth | fee/slippage + stale checks |

### Rejected (with reason)
- **Auto-betting / live execution** — out of charter scope (decision-support + paper only). Rejected.
- **Heavy black-box model as primary signal** — evidence (mlb-kalshi-bot) shows ML anti-calibrated on
  disagreement; transparency mandate. Rejected as *primary*; allowed only as gated challenger/fallback.
- **Scraping sportsbooks behind anti-bot for execution prices** — ToS/STD-2 violation. Rejected.
- **Replacing the expected-runs model before a challenger beats it OOS** — violates "no replacement
  without evidence". Rejected until R6/R8 exist.

---

## 14. Migration & rollback strategy

- **Additive-only schema:** new capability ships as `000N_*.sql` adding tables/columns or `v_*_v2`
  views. Published contracts (`model_predictions`, `game_outcomes`, `prediction_market_snapshots`,
  `hub_dataset`) are never changed in place. Rollback = drop the new object; old consumers unaffected.
- **Code:** all new modules behind interfaces + feature flags; challengers shadow-run (write to a
  `*_challenger` namespace) before champion swap. Rollback = flip flag to champion.
- **Model promotion:** registry records champion + challenger + metrics + approver; rollback = repoint
  the active pointer to the previous version (one row update), artifacts retained.
- **Data:** re-runs are idempotent (deterministic keys, upserts); a bad backfill is corrected by
  re-ingest, not in-place edits.

---

## 15. Technical-debt & risk register

| Risk / debt | Severity | Evidence | Mitigation | Owner |
|---|---|---|---|---|
| No tests/CI | **High** | verified absent | R1/R3 | platform |
| Selection bias in segment scan | **High** | in-sample n=110 called tradeable | R2 + R6 | quant |
| Features from stale 06-22 snapshot | **Med** | hub_dataset updated 06-22 | refresh pipeline export; PIT stamp | data |
| `backfill_history` non-PIT prices | **Med** | line 206 self-TODO | retire it; candlesticks only | data |
| OSI proxy mislabeled risk | **Med** | slate uses team OSI | label everywhere; restore matchup OSI | data |
| Single service_role key | **Med** | `.env` read+write | R5 least-privilege | platform |
| Secrets in chat transcript | **Med** | keys pasted this session | rotate Odds + service_role keys | owner |
| Doubleheaders merge on game_pk | **Low** | dedupe in finals ingest | include game number in key (future) | data |
| Betting history split across 2 Supabase projects | **Med** | betting-brain separate | decide consolidate vs dual-read | owner |
| 30 views return 0 rows | **Low** | scaffolding | populate via settle loop (R7) | data |
| No drift/monitoring | **Med** | absent | R12 | platform |

---

## 16. Unresolved research questions

1. Does `steam up ≥4pt` survive **out-of-sample + DSR/PBO**, or is it selection bias? (blocks any real use)
2. What is the model's **incremental** value over the sharp-consensus blend (does the prior add CLV)?
3. Correct **per-market sample-size floors** and calibration targets given Kalshi liquidity?
4. Is Kalshi closing price a sufficient CLV reference, or is a Pinnacle close needed per market?
5. Does the pipeline's **matchup OSI** materially beat the team-level proxy for win prob?
6. Optimal **staking** under small bankroll (flat-unit floor vs fractional Kelly) — at what bankroll switch?
7. For manufactured arb: realistic **hedge-conversion rate** and profit/bankroll-hour on MLB Kalshi?
8. Regime structure — do edges differ by month/park/weather enough to warrant regime conditioning?
9. Biomechanics: is there a license-clean path to **individual** pitcher fatigue features, or aggregate only?
10. Migration: consolidate the betting-brain history into this warehouse, or federate reads?

---

## Recommendation summary

**Do now (Required):** R1 tests/CI, R2 DSR/PBO, R3 package+git, R4 mark claims, R6 walk-forward,
R7 schedule+settle, R8 per-market gates, R9 registry. **Recommended:** R5, R10–R12.
**Experimental (gated):** R13–R18. **Rejected:** auto-betting, black-box-primary, ToS scraping,
premature model replacement.

This session implements **R1 (first tests), R2 (DSR/PBO), R3 (package skeleton + glue + git), R4**.
The rest are sequenced above with validation + rollback defined.
