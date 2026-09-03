"""The fitted pitcher-prop matrix: the matchup terms that survived out-of-sample testing.

Each constant here was fitted on the earlier 70% of the 2026 season by date and scored on the
held-out later 30% (894 starts) by `scripts/fit_prop_matrix.py`. Only the slope ships — the
regression intercept is a train-period level offset, not matchup information, and carrying it
forward would bake a stale season mean into every start.

    term                                    weight    OOS gain
    K    += w * (opp K rate / league - 1)   +2.567      +2.95%
    Outs += w * (.295 - BABIP to date)     -19.183      +0.36%
    Outs += w * (rest days - 5)             -0.031      +0.28%

    combined, same holdout:  K RMSE 2.1427 -> 2.1109,  Outs RMSE 3.7517 -> 3.7442

What is deliberately NOT here matters as much, and is recorded in
`docs/PROP-MATRIX-FINDINGS.md` so nobody re-adds it from intuition:

* **Ballpark** scores -0.23% on K, -0.16% on ER and +0.00% on Outs. It drives home runs and
  team totals; it does not survive as a per-start pitcher-prop term.
* **Home/away** looks worth +0.61% on K with a free intercept and **-0.49%** without one. It
  was a season level offset, not a matchup effect.
* **Earned runs** are not predictable beyond the pitcher's own shrunk history: every factor
  tested came back negative, the best being -0.01%. The challenger engine reached the same
  conclusion from a different direction (fitted opponent weight 0.00 for hits/HR/ER), so two
  independent methods agree. ER therefore gets no matrix term at all.
* **Walks** likewise: opponent walk discipline scores -1.68%.
* **The composite indices dilute the signal.** The raw opponent strikeout rate is worth
  +2.87%; the blended ABQ proxy scores -0.13% and OSI -0.31%, because OSI mixes on-base and
  run conversion into a strikeout question. Weight the component per market, never the
  composite.
"""
from __future__ import annotations

from datetime import date, datetime

# Fitted 2026-09-03 on 2,980 point-in-time starts (2026-04-11..08-30).
OPPONENT_K_WEIGHT = 2.567
BABIP_OUTS_WEIGHT = -19.183
REST_OUTS_WEIGHT = -0.031

# Batters faced at which a pitcher's own rate earns half weight against the league rate.
# These are the strengths `mlbmodel.props.challenger.FITTED` fitted on 2,980 starts; re-fitting
# them independently on the 3,219-start log in `scripts/fit_rate_shrinkage.py` lands at
# 110 / 300 / 550 BF, close enough that they are estimates rather than curve fits, and the
# challenger's values score marginally better out of sample. They differ by an order of
# magnitude between markets, which one shared constant cannot express: a strikeout rate is
# meaningful after ~113 batters, a hit rate is still mostly batted-ball noise at 461.
#
# The engine used to shrink only `skill_era`, by starts/(starts+6), and fed `k_rate`,
# `bb_rate` and `h_rate` in raw. Measured on the same holdout, projecting the count for the
# start (rate x batters faced):
#
#     market   unshrunk R2   shrunk R2   unshrunk slope   shrunk slope
#     K          +0.0878      +0.1856        0.596           0.868
#     BB         -0.1374      -0.0041        0.323           0.502
#     H          +0.0840      +0.1764        0.642           0.988
#
# Slope is the tell: at 0.60 a projection is spread ~1.7x wider than its predictive content
# supports, which is what produced double-digit "edges" against the market.
RATE_SHRINK_BF = {"k": 113.0, "bb": 193.0, "h": 461.0}
# A pitcher with no game log at all still needs a denominator; this is a conservative floor
# rather than an estimate, and it shrinks such an arm hard toward league.
MIN_RATE_SAMPLE_BF = 0.0

# Bounds on the inputs, not the outputs: a BABIP built on three starts can sit 150 points off
# league, and an unclipped term would turn that noise into a full inning of projected work.
BABIP_LUCK_CLIP = 0.06
REST_DAYS_RANGE = (3.0, 10.0)
REST_DAYS_CENTRE = 5.0
# A club needs a real sample before its strikeout rate is allowed to move a projection.
MIN_OPPONENT_BF = 400.0
LEAGUE_BABIP = 0.295


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def opponent_strikeout_rates(game_logs: list[dict]) -> tuple[dict[str, float], float]:
    """Strikeouts per batter faced by the club being pitched to, plus the league rate.

    Built from `sp_game_log.csv`, which the engine already loads. That is the same quantity
    the fit measured from the batter game log (the two agree at r=0.83 across all 30 clubs)
    and it spans a real range -- 0.184 for the most contact-oriented club to 0.258 for the
    most strikeout-prone -- so it is worth about half a strikeout end to end.
    """
    totals: dict[str, list[float]] = {}
    league_k = 0.0
    league_bf = 0.0
    for row in game_logs:
        team = str(row.get("opponent_team") or "").upper().strip()
        try:
            strikeouts = float(row.get("K"))
            batters = float(row.get("batters_faced"))
        except (TypeError, ValueError):
            continue
        if not team or batters <= 0:
            continue
        bucket = totals.setdefault(team, [0.0, 0.0])
        bucket[0] += strikeouts
        bucket[1] += batters
        league_k += strikeouts
        league_bf += batters
    league_rate = league_k / league_bf if league_bf > 0 else 0.219
    rates = {
        team: strikeouts / batters
        for team, (strikeouts, batters) in totals.items()
        if batters >= MIN_OPPONENT_BF
    }
    return rates, league_rate


def league_rates(game_logs: list[dict]) -> dict[str, float]:
    """Pooled league K/BB/H per batter faced — the prior every thin sample regresses to."""
    totals = {"k": 0.0, "bb": 0.0, "h": 0.0}
    batters = 0.0
    for row in game_logs:
        try:
            faced = float(row.get("batters_faced"))
        except (TypeError, ValueError):
            continue
        if faced <= 0:
            continue
        batters += faced
        for key, column in (("k", "K"), ("bb", "BB"), ("h", "H")):
            try:
                totals[key] += float(row.get(column))
            except (TypeError, ValueError):
                pass
    if batters <= 0:
        return {"k": 0.219, "bb": 0.082, "h": 0.225}
    return {key: value / batters for key, value in totals.items()}


def shrink_rate(
    rate_pct: float,
    market: str,
    batters_faced: float | None,
    league_rate: float,
) -> float:
    """Regress a per-batter rate (in percentage points) toward league by its own sample size.

    Equivalent to a beta-binomial posterior mean when `rate_pct` is the pitcher's own
    season rate, but applied to the engine's season/L14 blend so its recency weighting is
    preserved. Matchup adjustments are added *after* this: they are not sample-limited
    estimates of the pitcher and must not be regressed toward the league.
    """
    strength = RATE_SHRINK_BF.get(market)
    if strength is None:
        return rate_pct
    sample = max(MIN_RATE_SAMPLE_BF, float(batters_faced or 0.0))
    weight = sample / (sample + strength)
    league_pct = league_rate * 100.0
    return league_pct + (rate_pct - league_pct) * weight


def opponent_k_delta(
    opponent: str,
    rates: dict[str, float],
    league_rate: float,
) -> tuple[float, float | None]:
    """Strikeouts to add for facing this club. Returns ``(delta, normalised_rate)``."""
    rate = rates.get(str(opponent or "").upper().strip())
    if not rate or league_rate <= 0:
        return 0.0, None
    normalised = rate / league_rate
    return OPPONENT_K_WEIGHT * (normalised - 1.0), normalised


def regression_outs_delta(babip: float | None) -> float:
    """Outs to add for where the pitcher's batted-ball luck sits.

    ``luck = .295 - BABIP_to_date`` is positive when he has been lucky, and the fitted weight
    is negative: a lucky pitcher records *fewer* outs next time, because the luck regresses,
    hits follow and the outing shortens. That is the regression/progression signal, and until
    now it was computed, labelled on the board, and then discarded without moving a number.
    """
    if babip is None:
        return 0.0
    luck = _clip(LEAGUE_BABIP - float(babip), -BABIP_LUCK_CLIP, BABIP_LUCK_CLIP)
    return BABIP_OUTS_WEIGHT * luck


def rest_outs_delta(rest_days: float | None) -> float:
    """Outs to add for days of rest, centred on a normal five-day turn."""
    if rest_days is None:
        return 0.0
    rest = _clip(float(rest_days), *REST_DAYS_RANGE)
    return REST_OUTS_WEIGHT * (rest - REST_DAYS_CENTRE)


def days_rest(last_start: str | None, slate_date: str | None) -> float | None:
    """Calendar days between the pitcher's previous start and this one."""
    if not last_start or not slate_date:
        return None
    try:
        previous = datetime.fromisoformat(str(last_start)[:10]).date()
        current = datetime.fromisoformat(str(slate_date)[:10]).date()
    except (TypeError, ValueError):
        return None
    if not isinstance(previous, date) or current <= previous:
        return None
    return float((current - previous).days)
