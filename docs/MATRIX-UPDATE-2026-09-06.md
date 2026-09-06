# Matrix and market pricing update — 2026-09-06

Runtime version: `v3-matrix-20260906`. The upstream MLBMA metric lineage remains unchanged.

## Pitcher projection changes

The opponent strikeout coefficient is fitted in strikeouts per start. The production
engine converted it into a rate using `baseline_ip * 4.25`, but its workload simulation
had already changed to outs plus baserunners. This made the applied count adjustment
depend on outing length even when the fitted opponent adjustment was identical.

The conversion now divides by mean batters faced from the actual projected workload
draws, after workload calibration, environment adjustments, clipping and rounding.
The fitted coefficient, rate guardrail and final strikeout calibration are unchanged.
The matrix output includes `projected_batters_faced` and
`opponent_k_applied_strikeouts`, allowing its actual expected contribution to be audited.

Independent simulation tests cover short, typical and long outings and opponents whose
strikeout rates differ from league by -10%, +10% and +20%. A +10% matchup difference
adds approximately 0.249 strikeouts after calibration across those workloads. The
existing rate guardrail still limits extreme adjustments.

League priors now pair each market's observed numerator with its own observed
denominator. A missing walk count is not a zero-walk observation. Nonfinite, negative
and malformed innings/count observations are excluded; valid zero counts and zero-out
starts are retained. The current complete starter log is unaffected by this filtering.

## Game-line and prop pricing changes

Full-game totals, team totals and integer run lines now separate wins, losses and
pushes. Fair odds and the comparison to paired de-vigged book prices use
`P(win | no push)`. Expected value per original unit staked includes the refunded mass:

`EV = (1 - P(push)) * [P(win | no push) * decimal_odds - 1]`.

The same convention now applies to integer pitcher-prop lines. Previously the game
total under absorbed push outcomes as wins, while prop fair prices treated refunds as
losses. The report carries push probability alongside the conditional probability.
This agrees with DraftKings' documented refund on an exact-line total:
https://help.draftkings.com/hc/en-us/articles/4405230607507-What-is-a-total-or-Over-Under-wager-US

Run-line convolution also replaces the fixed 30-run cutoff with adaptive support,
omitting less than 1e-12 probability mass before normalization. Opposite contracts
partition wins/losses/pushes even in high-scoring environments.

## Evidence and limits

These are tested implementation corrections, not a newly fitted strategy or a claim of
improved future hit rate. Existing promotion gates and fitted coefficients remain in place.
The legacy `scripts/validate_prop_matrix.py` requires a batter log at a machine-specific
path that is unavailable here. It also multiplies rates by realized holdout batters
faced and derives some calibration centres from holdout predictions. Its historical
scores must not be described as an independent end-to-end pregame accuracy test.
Fresh chronological validation with predicted workload is required before claiming
an accuracy gain or promoting new weights.

First-five markets retain their existing approximate starter-ER construction. They
are not covered by the full-game pricing correction, and starter ER is not identical
to team runs through five innings.

## Verification

- Full test suite and lint checks, plus integration coverage of the matrix's K effect.
- Integer totals/props: exact-line mass never becomes a win or loss.
- Run lines: opposite outcomes plus push sum to one within 1e-10.
- EV: an independently specified 30% win / 50% loss / 20% push contract yields -0.20
  units at even money and fair odds +167.
- Half-point totals retain their previous probability calculation.
- Today's inputs are refreshed separately from the committed research snapshots.
