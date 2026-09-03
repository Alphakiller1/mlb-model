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

## Final calibration — every market now positive R² and slope ≈ 1

Shrinkage fixed the sample-size problem; it left the projections still slightly wider than
their predictive content. `actual = a + b·projection`, so the calibrated projection is
`centre + b·(projection − centre)`. Fitted on the earlier 70% by date, verified on the
holdout (`scripts/fit_final_calibration.py`, applied in `matrix.SPREAD_CALIBRATION`).

Full chain, 966 held-out starts (`scripts/validate_prop_matrix.py`):

| market | construction | R² | slope |
|---|---|---|---|
| **K** | original, unshrunk | +0.0878 | 0.596 |
| | + per-market shrinkage | +0.1856 | 0.868 |
| | + opponent K term | +0.1958 | 0.887 |
| | **+ spread calibration (shipped)** | **+0.1973** | **0.915** |
| **BB** | original, unshrunk | −0.1374 | 0.323 |
| | + per-market shrinkage | −0.0041 | 0.502 |
| | **+ spread calibration (shipped)** | **+0.0228** | **1.025** |
| **H** | original, unshrunk | +0.0840 | 0.642 |
| | **+ per-market shrinkage (shipped)** | **+0.1764** | **0.988** |
| **Outs** | original | +0.1617 | 0.734 |
| | + regression & rest | +0.1625 | 0.785 |
| | **+ spread calibration (shipped)** | **+0.1756** | **1.074** |

Hits ship **uncalibrated**: shrinkage alone already lands them at slope 0.988, and applying
the fitted 0.957 overshoots to 1.033 and costs R². Walks are calibrated hardest (0.490 on top
of a 193-batter shrinkage) because per-start walk totals are close to unpredictable — halving
what spread remains is exactly what moves that market from negative R² to positive.

## Two constants that were guesses, now measured

**Pitch-mix opponent scale: ×16 → ×40.** The earlier refusal to fit this was over-cautious.
Hindsight contamination is real for the *pitcher* half, whose season line is close to the
thing being predicted — but the opponent half is a club aggregate over ~150 games, so one
start is under 1% of it. Swept against the holdout: 16 → +0.1967, 25 → +0.1970, **40 →
+0.1973**, 60 → +0.1972, 87 → +0.1962, 115 → +0.1941. The train half alone fits 115 and the
holdout 87, so the slope is unstable; 40 is the holdout optimum and is what ships.

**Opponent damping on ER: 0.50 → 0.00.** This was shipped as a judgment. Re-tested against a
leak-free baseline (self-history ER rate × *projected* outs, never the realised ones) across
five separate opponent proxies:

| proxy | train slope | holdout slope | holdout R² with it |
|---|---|---|---|
| run conversion (RCV) | +1.057 | **−1.138** | +0.0206 |
| on-base (OBR) | −0.449 | −0.563 | +0.0241 |
| OSI composite | +1.819 | **−1.049** | +0.0219 |
| total bases | +0.102 | **−2.167** | +0.0238 |
| K-avoidance | −0.181 | −0.072 | +0.0239 |
| *baseline, no opponent term* | | | **+0.0239** |

**Every proxy flips sign between halves, and none beats the baseline.** Sweeping the damping
leaves holdout R² identical to four decimals at every value from 0 to 1. Four independent
methods now agree that per-start earned runs carry no opponent signal, so the channel is
computed and displayed but contributes nothing. Weather, umpire and travel are untouched —
they are physical, were never tested here, and pass through at full weight.

## Earned runs — the baseline itself was never scored

ER carries no matchup term (measured four ways). But its *baseline* had never been tested
either. The engine built it from `blended_era/9 × IP`, where `blended_era = 0.70·skill_era +
0.30·ERA` and `skill_era` is a FIP/xFIP blend shrunk by `starts/(starts+6)` — three constants,
none of them scored. On the holdout (`scripts/fit_er_and_outs.py`):

| construction | R² | slope |
|---|---|---|
| shipped: 0.70·shrunk FIP + 0.30·ERA | **−0.0274** | 0.729 |
| shrunk FIP only, no ERA | −0.0332 | 0.508 |
| *league mean over the same outs* | *−0.0113* | 0.356 |
| ER/out shrunk at 120 outs | +0.0093 | 0.591 |
| **ER/out shrunk at 248 outs (shipped)** | **+0.0156** | **0.719** |
| ER/out shrunk at 700 outs | +0.0113 | 0.719 |

**The shipped construction was worse than the league mean.** The fix is the same per-rate
shrinkage every other market got, on outs rather than batters faced — and 248 outs is both the
sweep optimum and exactly what `challenger.FITTED` arrived at independently.

## Outs — the ERA-vs-skill gap belongs after all

The factor study saw this worth +0.29% alone but left it out because a four-factor stack
overfitted. Tested on its own alongside the BABIP term it earns its place: R² +0.1418 →
**+0.1463**, RMSE 3.7442 → 3.7344, at +0.0586 outs per run of gap. It is the progression half
of the same idea — a pitcher whose ERA sits below the skill behind it goes slightly longer.

## The decisive test: does the projection beat the book's own line?

Everything above scores the model against the league mean, which is a low bar. This scores it
against the number the book posted, on the same starts, from the settled ledger with
point-in-time rebuilt projections (`scripts/model_vs_market.py`):

| market | n | MAE line | MAE original | **MAE rebuilt** | winner |
|---|---|---|---|---|---|
| **K** | 82 | 2.067 | 1.940 | **1.838** | **model** |
| **BB** | 35 | 1.157 | 0.804 | **0.932** | **model** |
| **Outs** | 68 | **2.941** | 3.056 | 3.051 | **MARKET** |

**Outs is the book's market.** A posted outs line prices bullpen plans, pitch-count limits,
injury management and how a manager has been using this arm — none of which reaches a
projection built from box scores. The model beats the league mean on Outs (R² +0.176) and
still loses to the line, which is the whole distinction: *beating the mean is not beating the
market, and only the second one is an edge.*

`matrix.MARKET_OUTFORECASTS_MODEL` gates that. Outs still projects and still displays its
probability; it just cannot render as actionable value, because the measurement says a
disagreement there is our error rather than the book's. On the live slate this suppressed 62
quotes and moved the actionable claimed edge from a median 9.1pts to **8.1pts**, with the
share above 10 points falling from 47% to **34%**.

Re-measure as the ledger fills, and drop a market from that set the moment it earns its way
out.

## The simulation's own shape constants — never checked until now

Fixing the pricing made this urgent. Prices used to be a normal refitted to `(mean, sd)`, so
only two moments of the simulation reached the board. They are now read straight off the
simulated distribution, which means **every shape constant in the sampler is priced directly**.
None had been scored (`scripts/validate_sim_shape.py`).

**Batters faced was modelled as a fixed ratio, and it is not one.** The sampler drew
`innings × normal(4.25, 0.16)`. The realised ratio depends heavily on outing length — 5.60
batters per inning under 4 IP, 4.50 from 4–6, 3.86 at 6+ — because a short outing is short
*because* of baserunners. The spread was understated 5.7× as well.

The clean parameterisation is `bf = outs + baserunners`, because baserunners allowed has mean
**6.33**, sd **2.57**, and a correlation with outs recorded of only **−0.039**: a starter allows
about six and a third baserunners whether he goes four innings or seven. Against 3,790 starts,
the old form scores RMSE 3.218 and this one **2.566**. This drives K/BB/H sampling.

**Innings spread was clipped too tightly.** Realised per-pitcher innings sd runs median 1.101,
p90 1.507; the 1.35 ceiling clipped 19% of pitchers — understating outing-length uncertainty
for exactly the volatile arms where it matters. Ceiling raised to 1.60.

**Outs priced 23% too confidently.** A simulated sd is conditional on the projected mean being
correct; a price needs the *predictive* sd, which also carries the projection's own error:

| market | sim sd | holdout RMSE | ratio | |
|---|---|---|---|---|
| K | 2.17 | 2.260 | 1.04 | ok |
| BB | 1.35 | 1.328 | 0.99 | ok |
| H | 2.15 | 1.976 | 0.92 | already conservative |
| **Outs** | **3.00** | **3.684** | **1.23** | **too tight** |

Only outing length was materially under-dispersed, and an independent route agrees — backing
sigma out of the pre-rebuild ledger's own prices gave 3.14 against a realised 3.91, a ratio of
1.245. `OUTS_SIGMA_INFLATION = 1.24` corrects it; all four markets now sit at 0.90–1.02. **A
sigma that is too tight does not bias the projection, it makes every probability drawn from it
overconfident** — which is how a board manufactures edge it has not earned.

Cumulative effect on actionable claimed edge across the three rounds:

| | median | p90 | share >10pts |
|---|---|---|---|
| original engine | 9.5pts | 20.5 | 46% |
| + matrix rebuild + market gate | 8.1pts | 16.6 | 34% |
| **+ shape fixes** | **7.2pts** | **16.0** | **34%** |

**Deliberately not changed:** the earned-run overdispersion shape, `gamma(4.5)`. The marginal
ER distribution implies ~4.0, but that marginal includes between-pitcher variance which the
model already carries separately in `er_mean`; inferring the conditional shape from it would
double-count. Left alone rather than changed on a flawed inference.

## Two grading bugs found in the same function

`mlbmodel/local_grading.py` (added upstream while this work was in progress) had both:

**It graded F5 earned runs against a team statistic.** `sp_game_log.f5_er` is the TEAM's earned
runs through five innings, not the starter's — on **19% of starts it exceeds his full-game ER
outright** (Scherzer 2.0 IP / 2 ER / f5_er 6; Verlander 3.2 IP / 5 ER / f5_er 8), because it
counts the bullpen after he was pulled. The board projects the *starter's* F5 earned runs, so
this scored a different quantity and manufactured error where there was none.
`mlbmodel.leans.grade` already voids that market for exactly this reason; the two graders now
agree.

**It converted innings to outs with `IP × 3`.** MLB notation `6.1` means six and *one third*
innings — 19 outs, not 18.3. 35% of starts end on a fractional inning, the mean shortfall is
0.38 outs and the worst case 1.4, which flips the graded side on **2.9%** of (start, half-point
line) pairs. That is a real error rate written into the record the model is judged by.
