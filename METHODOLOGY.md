# Methodology — MLB Model

Chase Analytics research software. This is the public, plain-language companion to the
versioned charter in `governance/` (which remains authoritative). **Paper-trading and
research only — no output is 
a wager instruction, and nothing here promises profit.**

## What each layer means

- **Projections.** A context-aware expected-runs model (lineups, starter skill,
  bullpen quality/workload, weather, umpire, travel/rest, pitch-mix response) with
  exact sequential factor lineage — every probability can show which factor moved it.
  Pitcher props come from 30,000-draw distributions with pitch-by-pitch opponent response.
- **Markets.** Book-level paired de-vig; raw implied probabilities are never labeled
  vig-free. Sharp-vs-soft divergence is observed point-in-time with executable entry prices.
- **Value states.** `BET` can only be produced by a strategy that has passed the
  promotion gate (walk-forward out-of-sample lower bound, Deflated Sharpe, PBO,
  minimum sample). Unpromoted strategies cap at `MONITOR`/`WATCH`.
- **Results.** Every lean the model records is graded after finals. Ungradeable leans
  carry an explicit reason code and void after 4 days — the record never hides skips.
  Pick'em leans are recorded **only** when the line snapshot is fresh for the slate;
  stale snapshot lines display with a warning but are never graded as picks.
- **CLV.** Each build refreshes closing odds on open leans; settlement computes
  closing-line value (implied close − implied entry, positive = beat the close).
- **Calibration.** Reliability buckets use the mean predicted probability per bucket
  with Wilson 95% intervals on the realized rate, plus an overall Brier score.
  Under-sampled buckets are marked, not interpreted.
- **Projection error.** Trusted pitcher projections settle by realized value
  (K/BB/ER/outs/hits), building per-market error distributions that feed back into
  prop sigma validation.

## Fantasy-score grading

PrizePicks MLB pitcher fantasy scores follow DraftKings classic scoring
(IP×2.25, K×2, W×4, ER×−2, H/BB/HBP×−0.6, CG+2.5); rare no-hitter/CGSO bonuses are
not derivable from the box endpoint and are omitted. Underdog and Sleeper fantasy
formulas are **not yet verified** — their fantasy leans void with
`fantasy_formula_unverified` rather than risk grading with the wrong formula.
First-5-innings markets (`f5_ml`, `f5_total`, `f5_er`) void with
`unsupported_market` until linescore-based F5 outcomes are ingested — grading them
against full-game finals would misgrade them.

## Known limitations

- The expected-runs model is transparent but not yet calibrated strongly enough to
  claim a durable betting edge; the promotion gate holds everything at HOLD/ABSTAIN
  until the out-of-sample evidence clears.
- Lineups and umpires are legitimately unavailable before MLB posts them; confidence
  degrades visibly instead of being inferred.
- The public deployment has no prop-price snapshot or betting warehouse credentials;
  market sections honestly display `NO MARKET`.

## Where this fits in Chase Analytics

- **mlb-model (this repo)** — MLB decision-support engine and model lab.
- **[wnba-edge-model](https://github.com/Alphakiller1/wnba-edge-model)** — the WNBA
  product; earlier-stage, same standards.
- **[chase-analytics.com](https://chase-analytics.com/)** — the consumer MLB research
  dashboard (MLBMA pipeline).

Cross-cutting standards live in `governance/MODEL-STANDARDS.md`.
