# Advancement Framework — MLB MODEL

Version 1.0.0 · 2026-06-26. Covers required outputs 7–11: traceability, extensibility
architecture, research/model lifecycle, MLBMA governance, and automated quality/promotion gates.

---

## 7. Current → target traceability matrix

| Constitution std | Current state (verified) | Target state | Bridging artifact |
|---|---|---|---|
| 1 PIT | candlestick clean; features from static snapshot | all inputs PIT-stamped; backfill_history retired | `quant/pit.py` checks + PIT test |
| 3 Reproducibility | deterministic keys, seeds | per-run manifest + data hash | `experiments/manifest.yaml` |
| 5 Leakage | ad hoc | leakage probes in CI | `tests/test_leakage.py` |
| 6 Sample size | min-n in one scan | per-market floor enforced | gate config `gates.yaml` |
| 7 Multiple testing | BH-FDR ✅ | + Deflated-Sharpe / PBO | `quant/selection.py` (added) |
| 8 Calibration | Brier views | isotonic recalib + per-market reliability gate | `quant/calibration.py` |
| 10 Walk-forward | in-sample scan | purged walk-forward harness | `backtest/walkforward.py` |
| 12 Promotion | none | champion-challenger registry | `registry/` + `gates.yaml` |
| 14 Auditability | timestamped rows | immutable decision audit log | `decision_audit` table |
| 17/18 Lifecycle/docs | design docs | per-signal records + revalidation dates | `signals/<id>.yaml` |

Tracking IDs (`STD-1`…`STD-18`) map to roadmap items in ROADMAP-AND-RISK.md.

---

## 8. Extensibility architecture (modular boundaries)

The dependency rule (one-way): `sources → store → {market, baseball} → quant → decision →
{arb, paper} → report → cli`. New capability enters as an **isolated module behind an interface**,
earns production authority only through the gates (§11). Boundaries that allow the charter's future
work without a rewrite:

| Future capability | Plugs in at | Interface (stable contract) | Isolation guarantee |
|---|---|---|---|
| New data provider | `sources/<name>.py` | `Source.fetch() -> list[NormalizedRow]` + provenance | quarantine bad rows; never touches model |
| New market / prop | `baseball/projections` + `decision/gates` | per-market gate in `gates.yaml` | own acceptance gate; no shared bucket |
| Pitch / PA models | `baseball/` submodel | `Model.predict(state) -> Dist` | champion-challenger vs baseline |
| Mixture-of-experts | `decision/ensemble.py` | weighted combine of `Model` outputs | challengers shadow-run first |
| Bayesian updating | `quant/bayes.py` | prior+evidence → posterior Dist | additive; baseline unchanged |
| Physics / biomechanics | `sources/biomech` + `baseball/fatigue` | aggregate context features only (STD-13) | filter/explainer, never sole signal |
| Fatigue/travel/weather | `baseball/context.py` | feature funcs returning bounded factors | clamped; feature-acceptance gate |
| Financial techniques (regime, microstructure) | `market/regime.py` | `regime(state) -> label` | tags decisions; no silent behavior change |
| Causal inference | `quant/causal.py` | explicit identification strategy | labeled causal; separate from associative |
| Multi-agent / adversarial review | `research/` CI job | proposes ADRs + challenger runs | advisory; cannot self-promote |
| Monte Carlo / game-state sim | `baseball/sim.py` | `simulate(state, n) -> outcome dist` | challenger; validated vs outcomes |
| Alt runtimes / optimization | `models/registry` artifacts | model card + parity test | parity-tested before swap |

**Rule:** every advancement is addable as an isolated, testable module **before** it receives
production authority. No module may change a published MLBMA contract without a versioned migration.

---

## 9. Research & model lifecycle (per signal/model)

```
hypothesis → mechanism → data audit → experiment → PIT backtest → robustness →
challenger (shadow) → monitored production → revalidation → retirement
```

Each signal is a version-controlled record `signals/<id>.yaml` that MUST contain:
research rationale · data sources + PIT availability · expected mechanism · effect size ·
confidence/credible interval · **incremental** predictive value (over baseline) · market value
after vig · stability by season/regime · correlation with existing features · failure conditions ·
owner · version · promotion status · revalidation date.

**Gate between stages** (cannot skip):
- experiment → PIT backtest: data audit passed (PIT, provenance, sample size).
- PIT backtest → robustness: positive OOS, not just in-sample.
- robustness → challenger: survives DSR/PBO + per-market gate.
- challenger → production: beats champion on the market's gate over a monitored shadow window.
- production → revalidation: scheduled; failing → demote/retire (STD-17).

**Hard rule (charter):** a small signal MUST NOT enter production merely because it improves one
historical backtest. Incremental value + OOS + robustness are required.

---

## 10. MLBMA as the system of record — governance spec

MLBMA is the **governed publication layer**. Assessment: the warehouse already publishes most
required layers; gaps are provenance, uncertainty, decisions/abstentions, and audit history.

| Publication layer | Today | Governance action |
|---|---|---|
| Source observations | `sharp_observations`, odds rows | add provenance cols (STD-2) |
| Normalized data | odds/kalshi normalized | versioned data contract |
| Features | `hub_dataset` (pipeline) | feature registry + PIT stamps |
| Predictions | `model_predictions` ✅ | keep; add model_version FK (exists) |
| Fair probabilities | de-vig outputs | publish with interval (STD-8) |
| Simulations | — | new `simulations` table when sim lands |
| Market snapshots | `prediction_market_snapshots`, odds | ✅ keep contract |
| Uncertainty | partial (bootstrap) | publish CI columns |
| Model versions | `model_versions` ✅ | add model cards in registry |
| Decisions & abstentions | partial (`verdict`) | add `decisions` + abstention reason |
| Outcomes | `game_outcomes` ✅ | keep |
| CLV & ROI | views (need settled data) | populate via daily settle |
| Research evidence | docs | `signals/` records linked by id |
| Data-quality warnings | console only | `data_quality_events` table |
| Audit history | timestamps | immutable `decision_audit` |

**Migration discipline:** preserve reliable existing contracts (`model_predictions`,
`game_outcomes`, `prediction_market_snapshots`, `hub_dataset`). Changes ship as **versioned
migrations** (`0003_*.sql`) that add columns/tables; never silently change a published meaning.
A consumer reads a contract version; breaking changes create a new view (`v_*_v2`).

---

## 11. Automated quality & promotion gates (per market)

Separate acceptance gates — accuracy or historical ROI alone is insufficient.

| Market | Primary metrics | Promotion threshold (illustrative; calibrate on data) |
|---|---|---|
| Game ML | log loss, Brier, reliability, CLV | OOS log loss < market baseline; calibration slope ∈ [0.9,1.1]; CLV ≥ 0 |
| Totals | Brier, distributional (CRPS), CLV | OOS CRPS < baseline; reliability passes |
| Run line | Brier, CLV, push-aware | beats baseline OOS; push handling correct |
| First-five | Brier, CLV | own sample ≥ floor; OOS positive |
| Batter props | log loss, calibration, vig-adj value | per-prop floor; calibrated; +EV after vig OOS |
| Pitcher props | distributional score, MAE, calibration | beats `projection_accuracy` baseline OOS |
| Market-movement signals | ROI-at-entry, bootstrap LB, **DSR/PBO**, CLV | LB>hurdle AND survives DSR/PBO AND CLV>0 OOS |
| Portfolio / staking | drawdown, profit/bankroll-hour, Kelly sanity | bounded drawdown; no min-stake rounding to zero |

**Gate stack (CI + runtime), all logged:**
1. tests pass (odds math, devig, PIT, leakage, calibration-no-regression)
2. data audit: provenance + PIT + sample size
3. multiple-testing: BH-FDR (discovery) + DSR/PBO (selection)
4. out-of-sample: walk-forward positive, reported separately
5. champion-challenger: challenger shadow-beats champion on the market gate
6. human sign-off recorded in registry

A candidate failing any required gate cannot exceed WATCH / cannot be promoted. **Honest-empty is
the default outcome.**
