# Pitcher prop matrix — what each factor is actually worth

Measured 2026-09-03 on 2,980 point-in-time starts (2026-04-11 → 08-30), fit on the earlier
70% by date and scored on the held-out later 30% (894 starts). Baseline for every row is the
pitcher's own shrunk self-history; the number is the out-of-sample residual variance the
factor removes **on top of that baseline**. A factor that cannot beat self-history is not
matchup information, whatever its raw correlation looks like.

Opponent strength is rebuilt from `mlbma_pipeline/data/batter_gamelog.csv` (33,170 dated
rows, carrying `opp_starter_hand`). The `opponent_*` columns in `sp_game_log.csv` are a
back-join of the season-to-date team index onto every historical row — all 30 clubs carry one
value for the whole season — so they encode end-of-season knowledge on opening day and cannot
be fit against (STD-1 / STD-5).

Reproduce with `PYTHONPATH=. python scripts/factor_study.py`.

## Strikeouts — real, and it is the ABQ K-avoidance axis

| factor | OOS R² gain | corr | fitted weight |
|---|---|---|---|
| **opponent K-avoidance rate** | **+2.87%** | +0.208 | +2.567 |
| all four components, free weights | +2.96% | +0.185 | — |
| opp K-avoidance vs *this* hand | +2.23% | +0.189 | +2.208 |
| opp on-base (OBR axis) | +0.82% | +0.121 | −2.594 |
| home / away | +0.61% | +0.083 | — |
| handedness platoon delta | +0.29% | +0.074 | −0.582 |
| opp run conversion (RCV axis) | −0.21% | −0.000 | — |
| ballpark | −0.23% | +0.061 | — |
| regression / progression | −0.17% | −0.009 | — |
| fatigue | +0.00% | +0.016 | — |

**The composite dilutes the signal.** The raw opponent K-rate is worth +2.87%, while the
blended `ABQ` proxy scores −0.13% and `OSI` scores −0.31%. OSI mixes on-base and run
conversion into a strikeout question, and those axes are collinear with K-rate but of the
opposite sign — the OBR weight comes out negative (−2.594) precisely because it is standing
in for "this club makes contact". **Weight the component per market; never the composite.**

Adding all four components buys +0.09% over the K-rate alone, which is inside the noise. The
platoon delta adds +0.01% and its weight flips negative — it is not independently supported.
Use the overall opponent K-rate, and use the hand split only where the club's hand-specific
sample is large.

## Outs — real, and it is the regression/progression signal

| factor | OOS R² gain | corr | fitted weight |
|---|---|---|---|
| **BABIP luck to date** | **+0.97%** | +0.099 | −19.183 |
| rest days | +0.41% | +0.067 | −0.031 |
| ERA-vs-skill gap | +0.29% | +0.075 | +0.083 |
| home / away | +0.28% | +0.050 | — |
| four-factor stack | +0.46% | +0.067 | — |
| prior-start pitch count | −0.46% | −0.042 | — |
| 3-start pitch load | −0.50% | +0.011 | — |
| ballpark | +0.00% | −0.045 | — |

The sign is the mechanism: `luck_babip = .295 − BABIP_to_date`, so a **positive** value means
the pitcher has been lucky on balls in play. The fitted weight is **negative** — a lucky
pitcher records *fewer* outs in his next start, because the luck regresses, hits follow, and
the outing shortens. That is the regression/progression ideology, and it is measurable.

Note the four-factor stack (+0.46%) scores **worse** than BABIP luck alone (+0.97%). The
extra terms are fitting noise. Ship the single term.

Fatigue is real but only through **rest days**, not pitch counts: prior-start pitch count
(−0.46%) and 3-start load (−0.50%) both hurt out of sample.

## Earned runs — nothing beats self-history

| factor | OOS R² gain |
|---|---|
| created metric ABQ | −0.01% |
| ballpark | −0.16% |
| opp extra-base power | −0.19% |
| BABIP luck | −0.19% |
| handedness platoon | −0.20% |
| created metric OSI | −0.23% |
| all components, free weights | −0.23% |
| opp run conversion (RCV) | −0.36% |
| fatigue | −0.29% |
| ERA-vs-skill gap | −0.68% |
| regression / progression | −0.68% |

**Every factor tested is negative.** Per-start earned runs are not predictable beyond the
pitcher's own shrunk history — the sequencing noise dominates. This is the same conclusion
the challenger engine reached from a different direction (fitted opponent weight 0.00 for
hits/HR/ER), so two independent methods agree.

The champion currently multiplies ER by a stack of opponent indices, park-free but
lineup-, weather-, umpire-, travel- and injury-adjusted. That stack is unsupported. ER should
be projected from self-history and priced honestly, not decorated.

## Walks — nothing

Opponent walk discipline scores −1.68%, and −1.68% again on the hand split. No factor helps.

## What this means for the board

1. **K** gets an opponent K-avoidance term at its fitted weight, plus home/away.
2. **Outs** gets a BABIP-regression term and a rest-days term.
3. **ER** and **BB** get self-history only, and must be presented with that uncertainty.
4. Ballpark earns a weight of zero in every market tested. Wiring it in would add noise.
   (It matters for HR and for team totals; it does not survive as a *per-start pitcher prop*
   factor.)
5. The gains are small in absolute terms — 2.87% of residual variance is the honest ceiling
   for the best factor on the best market. Any board claiming a double-digit edge on a pitcher
   prop is reporting a bug, not an edge.

## The pitch-mix term — it was 94% the pitcher, and that half was dead weight

Measured 2026-09-03 on 3,790 starts with `scripts/pitch_mix_audit.py`. Scored using the
**current** season-aggregate pitch-mix tables, which already know how each start turned out.
That contamination is deliberate and it only *helps* the term: a factor that cannot predict
with hindsight is broken outright.

The engine adds `k_rate_delta` on top of the pitcher's own season K rate, which it has
already applied to `k_rate`. Splitting the score into its two halves:

| component | share of total sd | corr with realised K rate | partial corr, holding his own season K rate constant |
|---|---|---|---|
| pitcher's own stuff | 94% | +0.3502 | **+0.0027** |
| opponent lineup | 30% | +0.1042 | **+0.0858** |
| total (what shipped) | 100% | +0.3598 | **+0.0375** |

The pitcher half correlates **+0.708 with his own season K rate** — it is a restatement of
skill already in the projection. Once that is held constant it is worth **+0.0027**, i.e.
nothing. Worse, carrying it **halved the combined signal**, from the +0.0858 the opponent
half gives alone down to +0.0375, because it is ~3x the magnitude and pure noise relative to
the outcome. Counting the same skill twice is also exactly what an over-dispersed board looks
like from the inside.

**Fixed:** `k_rate_delta` and `er_factor` are now the opponent half only. The pitcher half is
still computed and returned as `pitcher_arsenal_score` for the board, because "how good is
this arsenal" is worth showing — it just cannot move the number. On the live slate the term's
spread fell from sd 0.751 (range −1.24…+1.69) to sd 0.319 (−0.61…+0.78).

**The scales were deliberately not re-fitted.** The only data that could fit them is the
season-aggregate pitch mix used above, which is contaminated; a weight fitted on it would be
fitted to hindsight. `×16` and `×1.8` are unchanged, which shrinks the term ~3.3x — the
conservative direction. Re-fit properly once point-in-time pitch-mix snapshots exist.

### Two more defects in the same term

**Three tables, one baseline.** Opponent values come from individual-batter rows when a
lineup is posted and from team-batting rows otherwise, but both were scored against a
baseline built from team batting alone. The tables sit on different scales — mean whiff rate
19.2 (pitcher mix), 20.6 (team batting), 22.8 (individual batter), with xwOBA differing ~30
points between batter and team rows. The same pitcher/opponent matchup therefore moved by up
to **2.15 K-rate points** purely on whether MLB had posted the lineup, against a real signal
whose whole standard deviation is ~0.15. Each table now carries its own baseline; the
systematic component of that jump fell from +0.064 to **+0.005**. The residual spread is
genuine — a posted nine really is different from the club aggregate.

**A fabricated OPS column.** `lineup_ops` was set to `opponent_row["xwoba"]` and rendered
under an `OPS` header immediately left of the real `Opp xwOBA` column, so the board printed
the same number twice under two different names (with a `xwOBA × 2.8` fallback inventing an
OPS when the value was missing). Column removed.

### What did NOT turn out to be wrong

Two hypotheses were tested and rejected, recorded so they are not re-investigated:

* **Coverage weighting.** The score is a usage-weighted *sum*, not an average, so a pitcher
  with thin pitch-mix coverage should score systematically smaller. In practice coverage runs
  0.91–1.00 (sd 0.011), so normalising changes the correlation from +0.3598 to +0.3599.
  Not a real defect.
* **Clip saturation.** `clip(total × 16, ±2.5)` pins **0.0%** of starts at a bound.
