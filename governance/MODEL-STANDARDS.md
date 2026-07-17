# Chase Analytics — Model Standards (org-level)

The portable rulebook every Chase Analytics sports model starts from. The MLB
Model's constitution discovered these rules the hard way; new sports (WNBA, …)
adopt them from day one instead of re-learning them. Tests and pipeline gates —
not documents — determine what is actually enforced.

## Pricing

1. A raw implied probability from a single price is never labeled vig-free.
   Market probabilities come from paired (two-way) de-vig or are labeled as
   including vig.
2. An edge is model probability minus the de-vigged market probability. No market
   price, no edge — model output without a price is a projection, not an edge.
3. Implausibly large edges (≥ 15 pts) are treated as input errors (`REVIEW`),
   never as bets.

## Prediction hygiene

4. Every prediction is persisted at decision time with a prediction id, run id,
   model version, and UTC timestamp — before the outcome is knowable.
5. A prediction may only be recorded against a price/line snapshot that is fresh
   for its slate. Stale snapshot lines may render (with a visible warning) but
   are never recorded or graded.
6. A movement/timing strategy needs a point-in-time signal and an executable
   entry price; selecting on information from after the decision time is leakage.

## Grading

7. Everything recorded is graded. Anything ungradeable carries an explicit,
   machine-readable reason code; nothing is silently skipped.
8. Predictions that can no longer grade (postponed games, unmatched players,
   unsupported markets) are voided with their reason after a bounded window —
   pending must never grow monotonically.
9. Never grade a market against a proxy outcome (e.g., F5 markets against
   full-game finals). Ungradeable-correctly beats graded-wrongly.
10. Exact-line outcomes are pushes, excluded from hit rates.

## Evaluation

11. Hit rate alone is not evidence. Track Brier score, calibration with
    confidence intervals (mean-predicted vs realized with Wilson CIs), and
    closing-line value per recorded lean.
12. Projection-type predictions settle by realized value, building per-market
    error distributions that calibrate the model's variance assumptions.
13. No strategy is promoted to bet-authority without: out-of-sample lower bound
    above the hurdle, Deflated Sharpe clearance, PBO clearance, and a minimum
    OOS sample. Unpromoted strategies cannot produce a BET state.

## Operations

14. Failure states are visible: empty is rendered as an honest empty state, and
    scheduled jobs report their outcome (and failures) to a channel a human
    actually reads.
15. Scrapes validate a schema contract (required fields, minimum rows) and fail
    loudly on upstream drift.
16. Data writes are idempotent (deterministic keys, upserts); re-runs repair, they
    do not duplicate.

## Communication

17. Research/analytics framing, always: no output is betting advice or a wager
    instruction; public surfaces carry the disclaimer and a methodology link.
18. Every displayed fitted quantity states its basis and sample size.
19. A descriptive statistic is never presented as a model driver.
