# MLB MODEL — Model Constitution

**Version 1.0.0** · ratified 2026-06-26 · SemVer; breaking changes to any standard bump MAJOR.
This document governs every current and future component. A change to published meaning requires
a version bump + an entry in the changelog at the bottom. Each standard names its **enforcement
mechanism** (the charter's requirement that the constitution be enforceable, not aspirational).

Enforcement types: **TEST** (automated pytest) · **GATE** (pipeline/CI step that blocks) ·
**SCHEMA** (DB constraint / contract validation) · **REGISTRY** (model-registry check) ·
**HUMAN** (recorded approval). Status: ✅ enforced · ◐ partial · ○ planned.

| # | Standard | Rule (normative) | Enforcement | Status |
|---|---|---|---|---|
| 1 | **Point-in-time integrity** | A feature/price used for a decision at time T must have been knowable at T. Pre-first-pitch filter on market candles is invariant. No future leakage from settlement back into features. | TEST (PIT assertions) + GATE (backfill rejects post-event prices) | ◐ |
| 2 | **Provenance & licensing** | Every source row records source, endpoint, fetch time, and license basis. Only API-ToS-compliant or licensed data enters the warehouse. No scraping that violates ToS. | SCHEMA (provenance cols) + HUMAN (source registry) | ○ |
| 3 | **Reproducibility** | Every experiment has a manifest: code commit, data version+hash, params, env, seed. Re-running yields identical numbers (seeded). | GATE (manifest required) + TEST (seed determinism) | ◐ |
| 4 | **Feature acceptance** | A feature enters production only with: mechanism, PIT availability, incremental value over baseline, correlation with existing features, stability, owner, version. | REGISTRY (feature registry) + HUMAN | ○ |
| 5 | **Leakage prevention** | No target-derived, post-cutoff, or settlement-informed inputs in features. Rolling stats for game i use only games < i. | TEST (leakage probes) + GATE | ◐ |
| 6 | **Sample-size requirements** | No segment/claim with n below the per-market floor may be called tradeable or promoted. Underpowered → reported as "insufficient", never as edge. | GATE (min-n per market) + TEST | ◐ |
| 7 | **Multiple-hypothesis correction** | Any scan over multiple segments applies FDR (BH) for discovery AND Deflated-Sharpe / PBO for strategy selection across trials. | TEST + GATE (selection.py) | ✅ DSR/PBO gate; legacy BH remains a parity reference |
| 8 | **Uncertainty & calibration** | Every probability ships with an interval. Calibration (Brier/log-loss + reliability) tracked per market; isotonic recalibration applied when sample supports. | TEST (calibration regression) + GATE | ◐ |
| 9 | **Causal vs associative** | Claims are labeled associative by default. "Causal" requires an explicit identification strategy; absent that, no causal language in outputs. | HUMAN (label) + TEST (lint outputs) | ○ |
| 10 | **Backtest & walk-forward** | Edges validated out-of-sample via walk-forward / purged CV, not a single in-sample scan. Report OOS separately from in-sample. | GATE (promotion needs OOS) | ◐ executable grouped walk-forward ✅; purged CV planned |
| 11 | **Market-price & vig handling** | Probabilities de-vigged two-sided; value measured net of vig at the executable entry price; CLV captured (prob + ROI space) on all analyzed games. | TEST (devig sums to 1) + SCHEMA | ◐ paired de-vig + executable entry ✅; CLV-all planned |
| 12 | **Promotion & rollback** | A model/signal reaches production only via champion-challenger on its market's gate. Every promotion is reversible; rollback procedure recorded. | REGISTRY + GATE + HUMAN | ◐ UI and pipeline gate enforced; registry/rollback planned |
| 13 | **Bio/medical-data boundaries** | Biomechanics/health data used only as aggregate, de-identified context features; never individual medical claims; license + consent verified before ingest. | HUMAN (review) + SCHEMA (no PII) | ○ (no such data yet) |
| 14 | **Explainability & auditability** | Every decision is reconstructable: inputs, model version, gate results, and a "why this could be wrong" note are logged immutably. | SCHEMA (audit log) + TEST | ◐ |
| 15 | **Security & access control** | Least privilege: read paths use the anon/publishable key; service_role only for governed writes; secrets gitignored; no secret in code or transcript-persisted config. | GATE (secret scan) + HUMAN | ◐ |
| 16 | **Responsible risk communication** | Outputs state uncertainty, sample size, and that this is decision-support/paper-trading — never auto-betting. No unsupported performance claims; stale claims marked. | TEST (output lint) + HUMAN | ◐ |
| 17 | **Model retirement** | Models/signals have a revalidation date; failing revalidation → demoted/retired with a recorded reason. No silent zombies. | REGISTRY (revalidation date) + GATE | ○ |
| 18 | **Research documentation** | Every signal/model has a research record (rationale, data, mechanism, effect size, CI, failure modes, owner, version) before production authority. | REGISTRY + HUMAN | ○ |

## Enforcement rollout (which become what, in order)

1. **TEST now** (no infra needed): odds-math round-trips, devig-sums-to-1, PIT candle filter,
   seed determinism, min-n, calibration-no-regression. → seeds the CI gate.
2. **GATE next** (CI): tests must pass; secret scan; manifest presence; promotion requires OOS + DSR.
3. **SCHEMA**: provenance columns, immutable audit log table, no-PII constraints.
4. **REGISTRY**: feature + model registries with model cards, revalidation dates, promotion status.
5. **HUMAN**: source-license registry, causal-claim review, bio-data review, promotion sign-off.

## Amendment process
Propose via an ADR (see ADVANCEMENT-FRAMEWORK). A standard's enforcement may strengthen (◐→✅)
in a MINOR release; weakening a standard or changing published meaning requires MAJOR + migration note.

## Changelog
- **1.0.0** (2026-06-26) — initial ratification; standards 7/11 partially enforced (BH-FDR, de-vig),
  remainder mapped to the rollout above.
