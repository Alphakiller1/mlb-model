# Model inspection — 2026-09-04

A full-model audit, scored against the settled `model_leans` ledger rather than against
intuition. The prop matrix had already been rebuilt; this looks at everything else — the game
model, the market-fusion layer, and the grading pipeline that feeds all of them.

Two defects were fixed in place (below). The rest are ranked by what they would be worth.

## Fixed here

### 1. Pick'em stored the probability of the wrong side — 100% of UNDER rows

`_collect_pickem` wrote `model_prob = p_over` regardless of which side the lean took. Every
one of the **92 graded pick'em UNDER rows** in the ledger therefore carried the probability of
the *over* — a pick whose projection sat below the line was recorded at 0.29 rather than 0.71.

The effect is not cosmetic: every reliability, Brier and ROI figure computed on Underdog or
Sleeper rows was scored against the opposite side, which inverts the calibration curve for
that whole source. `model_prob` now means for pick'em what it means everywhere else — the
probability that the **recorded selection** wins.

### 2. Transient grading failures were made permanent

`VOID_AFTER_DAYS = 4` voids anything still pending after four days, with whatever reason it
last had. That is right for terminal reasons (`unsupported_market`), but wrong for reasons
that were only ever a timing problem: a lean voided as `game_outcome_missing` was gradeable —
the final simply had not been ingested yet.

On inspection this described **587 rows on the 2026-08-24 slate alone**, spread across just
**10 game_pks**, every one of whose outcomes the warehouse already holds (the same pks grade
fine on other rows). That is most of the game model's evidence base discarded for a scheduling
reason.

`_RECOVERABLE_REASONS` now re-opens those on later runs, using the same mechanism that already
backfilled falsely-voided F5 markets. Re-running settlement recovered all **587**, taking the
graded pool from 1,274 to **1,401** and roughly doubling the game model's sample. If the data
still is not there, the row simply voids again, so retrying costs nothing.

## The main finding: the run line is the model's worst market

With the recovered rows included:

| market | n | model says | reality | gap |
|---|---|---|---|---|
| **runline −1.5 (laying)** | **66** | **45.4%** | **34.8%** | **−10.5** |
| runline +1.5 (taking) | 31 | 55.6% | 48.4% | −7.2 |
| matchup runline (all) | 59 | 49.4% | 40.7% | −8.7 |
| sharp runline (all) | 38 | 47.5% | 36.8% | −10.7 |

Both sources over-predict by 9–11 points, independently. And the reason this is structural
rather than a small sample: **a real MLB favourite covers −1.5 about 35–40% of the time.** The
observed 34.8% is normal. The model's 45.4% is *above the league-wide ceiling for the market* —
no set of favourites covers −1.5 at 45%.

The convolution itself is sound. `margin_cover_probability` returns 35.7% for an even game and
50.7% for a 5.5-vs-4.0 game, and the gap it produces between winning and winning by two is a
sensible ~9.5 points. Feeding it an average of 45.4% means the model believes its favourites
average roughly **+1.0 runs of expected margin**, when a typical MLB favourite is nearer +0.3
to +0.5.

**So the root cause is not the run-line math — it is that `exp_margin` is over-dispersed.**
That is the same disease the prop projections had before the rebuild: spread far wider than
the signal underneath supports. The moneyline shows the same signature in its tails:

| bucket | n | predicted | actual |
|---|---|---|---|
| 0.3–0.4 | 6 | 37.3% | 83.3% |
| 0.4–0.5 | 36 | 44.5% | 44.4% |
| 0.5–0.6 | 40 | 55.2% | 55.0% |
| **0.6–0.7** | **12** | **62.7%** | **16.7%** |

The middle is well calibrated — it cannot be far wrong near 50%. Both tails are inverted, and
the confident tail is the one that costs money.

**Recommended fix, in the order the props were fixed:** regress `exp_margin` toward zero by a
fitted slope, measured on the now-recoverable ledger, and re-derive the run line from the
shrunk margin. Do not hand-tune the run-line probability directly — the convolution is correct
and should stay downstream of an honest margin.

## Ranked backlog

1. **Shrink `exp_margin`** (above). Largest single miss in the model, and now measurable
   because the recovered rows roughly doubled the sample. Same method as the prop rebuild:
   regress outcome on projection, ship the slope.
2. **Nothing in the game model has demonstrated an edge.** Every game market sits at
   Brier 0.229–0.281 with predictions clustered at 50%; `f5_total` and `sharp ml` are exactly
   50.0% predicted and 50.0% actual. That is honest, but it is not yet a product. Calibration
   first, edge second.
3. **`pitcher_stats_not_found`** voids 40 prop-k rows and 27 of each projection market. Worth
   a name-resolution pass — these are now recoverable, so each fix returns retroactive data.
4. **PrizePicks `pp_fantasy` grades nothing** (28 rows, all void) and Underdog/Sleeper
   `earned_runs` is `unsupported_market`. Both are gradeable quantities; the guard is broader
   than it needs to be.
5. **`projection f5_er` is 994 of 1,031 void.** Correct given the starter-vs-team mismatch
   documented in `PROP-MATRIX-FINDINGS.md`, but it means an entire projected market is
   decorative. Either project the team quantity or stop projecting it.

## Method note

Everything above is scored on deduplicated rows: the ledger stores one row per book, so a
naive count inflates n by roughly 4.7x and makes noise look like signal. Dedupe on
`(slate_date, source, market, selection, line, game_pk, pitcher_name)` before drawing any
conclusion from this table.
