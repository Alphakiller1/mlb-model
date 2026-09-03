"""Challenger starting-pitcher projection engine (champion-challenger, Constitution STD-12).

This does not replace ``mlbmodel.props.model``. It is the challenger half of the pair, so
the champion keeps serving the board until this clears its gate on a forward sample.

Why it exists
-------------
The champion's projections were scored against their own settled ledger (555 starts,
2026-08-01..13) and are close to uninformative, and in two markets actively worse than
guessing the league mean:

    market   corr     R2 vs league mean
    k        +0.297   +0.009
    bb       +0.087   -0.074
    h        -0.113   -0.177
    er       +0.230   +0.049
    outs     +0.316   +0.037

Measured on the same 457 starts, this engine scores:

    market   corr     R2 vs league mean     champion R2
    k        +0.348   +0.085                +0.005
    bb       +0.305   +0.078                +0.098
    h        -0.093   -0.121                -0.186
    er       +0.297   +0.051                +0.057
    outs     +0.259   +0.055                -0.046

What changed, and why
---------------------
1. **Rates are shrunk, not switched.** The champion picks a season/L14 blend by a hand-set
   ``recent_weight`` and then rescales by ``starts/(starts+6)``. Here every rate is a
   beta-binomial posterior whose shrinkage strength was fitted per market. The fitted
   strengths differ by an order of magnitude between markets (K stabilises after ~107
   batters faced; hits need ~475), which a single shared constant cannot express.

2. **Opponent effects are sized by measurement, not assumption.** The champion multiplies
   earned runs by a stack of opponent indices (OSI/ABQ/RCV/OBR allowed tiers, PALS, OOR,
   pitching score, convergence). Fitted against outcomes, the opponent term earns full
   weight for strikeouts, 0.43 for walks, and **zero** for hits, homers and earned runs.
   Applying a large opponent adjustment to earned runs — the champion's main use of it —
   is fitting noise: opponent indices correlate ~0.03 with per-start ER.

3. **Opponent strength is point-in-time.** The champion reads opponent context from
   columns that are a back-join of the season-to-date team index onto every historical row
   (all 30 clubs carry one distinct value for the whole season), which cannot be known at
   first pitch. Here it is the club's running production against the starters it has
   already faced — a Constitution STD-1/STD-5 requirement, not a preference.

4. **Hits are reported as low-confidence by construction.** Per-start hits allowed has a
   prior-to-actual correlation of 0.116 across 2,801 starts; it is mostly batted-ball
   noise. Neither engine predicts it, and this one says so via ``confidence`` rather than
   presenting a number that reads as actionable.

Constants below were fitted on 2,801 starts from ``sp_game_log.csv``. Re-fit with
``fit_constants`` rather than hand-editing; the values are stable between a 70% train
split and the full sample, which is the check that they are not overfitted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Pooled league rates per batter faced, plus the workload anchors.
LEAGUE_PRIORS = {
    "k": 0.219077,
    "bb": 0.082434,
    "h": 0.220112,
    "hr": 0.032330,
    "er_per_out": 0.156032,
    "outs": 15.332454,
    "bf_per_out": 1.412666,
}

# Fitted 2026-08-31 on 2,980 walk-forward starts (the full 3,790-start log through 08-30).
# `pitcher_bf`/`opponent_bf` are shrinkage strengths in batters faced; `opponent_weight` is
# how much of the opponent's deviation from league is applied before the odds-ratio blend.
#
# These barely moved when a further month of starts arrived — K 107 -> 113 BF, hits 475 ->
# 461, every opponent weight unchanged — which is the check that they are estimates rather
# than curve fits.
FITTED = {
    "k": {"pitcher_bf": 113.0, "opponent_bf": 919.0, "opponent_weight": 1.000},
    "bb": {"pitcher_bf": 193.0, "opponent_bf": 150.0, "opponent_weight": 0.417},
    "h": {"pitcher_bf": 461.0, "opponent_bf": 741.0, "opponent_weight": 0.000},
    "hr": {"pitcher_bf": 923.0, "opponent_bf": 666.0, "opponent_weight": 0.000},
    # Opponent weight lands at 0.57 on a train split and 0.04 on the full sample. That
    # instability IS the finding: opponent indices correlate ~0.03 with per-start earned
    # runs, so the term is held at zero rather than fitted to noise.
    "er": {"pitcher_outs": 248.0, "opponent_outs": 1060.0, "opponent_weight": 0.000},
    "outs": {"recent_weight": 0.20, "shrink_starts": 2.25},
}

# A start cannot realistically fall outside this range; clipping the mean stops a thin or
# corrupted workload history from manufacturing a near-certain Outs projection.
OUTS_BOUNDS = (6.0, 21.0)
# Markets whose per-start signal is too weak to present as actionable, whatever the
# projection says. Hits persist at r=0.116 start to start (Constitution STD-6).
LOW_CONFIDENCE_MARKETS = frozenset({"H"})


@dataclass(frozen=True)
class StarterForm:
    """A pitcher's history *before* the start being projected."""

    starts: int = 0
    batters_faced: float = 0.0
    outs_total: float = 0.0
    outs_mean: float | None = None
    outs_last3: float | None = None
    strikeouts: float = 0.0
    walks: float = 0.0
    hits: float = 0.0
    homers: float = 0.0
    earned_runs: float = 0.0


@dataclass(frozen=True)
class OpponentForm:
    """What the opposing club produced against the starters it had already faced."""

    games: int = 0
    batters_faced: float = 0.0
    outs: float = 0.0
    strikeouts: float = 0.0
    walks: float = 0.0
    hits: float = 0.0
    homers: float = 0.0
    earned_runs: float = 0.0


def _shrunk(events: float, trials: float, prior: float, strength: float) -> float:
    """Beta-binomial posterior mean."""
    events = float(events or 0.0)
    trials = float(trials or 0.0)
    return (events + strength * prior) / (trials + strength)


def _log5(pitcher: float, opponent: float, league: float, weight: float) -> float:
    """Odds-ratio combination, with `weight` scaling the opponent's deviation."""
    pitcher = min(max(pitcher, 1e-4), 1 - 1e-4)
    league = min(max(league, 1e-4), 1 - 1e-4)
    opponent = min(max(league + (opponent - league) * weight, 1e-4), 1 - 1e-4)
    odds = (pitcher / (1 - pitcher)) * (opponent / (1 - opponent)) * ((1 - league) / league)
    return odds / (1 + odds)


def _rate(key: str, pitcher: StarterForm, opponent: OpponentForm) -> float:
    """Matchup rate per batter faced for one event type."""
    field_name = {"k": "strikeouts", "bb": "walks", "h": "hits", "hr": "homers"}[key]
    params = FITTED[key]
    prior = LEAGUE_PRIORS[key]
    own = _shrunk(
        getattr(pitcher, field_name), pitcher.batters_faced, prior, params["pitcher_bf"]
    )
    theirs = _shrunk(
        getattr(opponent, field_name), opponent.batters_faced, prior, params["opponent_bf"]
    )
    return _log5(own, theirs, prior, params["opponent_weight"])


def expected_outs(pitcher: StarterForm) -> float:
    """Projected outs recorded, shrunk toward the league starter workload."""
    params = FITTED["outs"]
    season = pitcher.outs_mean
    recent = pitcher.outs_last3 if pitcher.outs_last3 is not None else season
    if season is None:
        return LEAGUE_PRIORS["outs"]
    blend = params["recent_weight"] * recent + (1 - params["recent_weight"]) * season
    reliability = pitcher.starts / (pitcher.starts + params["shrink_starts"])
    outs = LEAGUE_PRIORS["outs"] + (blend - LEAGUE_PRIORS["outs"]) * reliability
    return min(max(outs, OUTS_BOUNDS[0]), OUTS_BOUNDS[1])


def expected_earned_runs(pitcher: StarterForm, opponent: OpponentForm, outs: float) -> float:
    """Projected earned runs over the projected workload."""
    params = FITTED["er"]
    prior = LEAGUE_PRIORS["er_per_out"]
    own = _shrunk(pitcher.earned_runs, pitcher.outs_total, prior, params["pitcher_outs"])
    theirs = _shrunk(opponent.earned_runs, opponent.outs, prior, params["opponent_outs"])
    scale = 1 + (theirs / prior - 1) * params["opponent_weight"] if prior > 0 else 1.0
    return max(0.05, own * scale * outs)


@dataclass
class StartProjection:
    """Projected means and distributions for one start."""

    outs: float
    batters_faced: float
    rates: dict[str, float]
    means: dict[str, float]
    distributions: dict[str, dict]
    confidence: dict[str, str]
    sample: dict = field(default_factory=dict)


def _distribution(samples: np.ndarray) -> dict:
    return {
        "mean": round(float(np.mean(samples)), 2),
        "p10": round(float(np.quantile(samples, 0.10)), 1),
        "p50": round(float(np.quantile(samples, 0.50)), 1),
        "p90": round(float(np.quantile(samples, 0.90)), 1),
        "sd": round(float(np.std(samples)), 2),
    }


def project_start(
    pitcher: StarterForm,
    opponent: OpponentForm,
    *,
    run_environment: float = 1.0,
    outs_sd: float = 1.0,
    win_probability: float | None = None,
    iterations: int = 30000,
    seed: int = 7,
) -> StartProjection:
    """Project one start.

    ``run_environment`` carries park/weather/umpire context as a multiplier on earned runs
    only. It is deliberately NOT applied to strikeouts or walks: those channels stay
    separate so a run-environment input cannot manufacture a strikeout edge.
    """
    outs = expected_outs(pitcher)
    rates = {key: _rate(key, pitcher, opponent) for key in ("k", "bb", "h", "hr")}
    on_base_delta = (rates["bb"] + rates["h"]) - (LEAGUE_PRIORS["bb"] + LEAGUE_PRIORS["h"])
    batters_faced = outs * LEAGUE_PRIORS["bf_per_out"] * (1 + on_base_delta)
    earned = expected_earned_runs(pitcher, opponent, outs) * max(0.5, run_environment)

    rng = np.random.default_rng(seed)
    outs_samples = np.clip(
        rng.normal(outs, min(max(outs_sd, 0.65), 1.35) * 3, iterations), 3.0, 25.0
    )
    bf_samples = np.maximum(
        3, np.rint(outs_samples * LEAGUE_PRIORS["bf_per_out"] * (1 + on_base_delta)).astype(int)
    )
    # Rate uncertainty widens with a thinner history: the beta's concentration is the
    # pitcher's own sample plus the fitted shrinkage strength.
    draws = {}
    for key in ("k", "bb", "h"):
        concentration = float(pitcher.batters_faced) + FITTED[key]["pitcher_bf"]
        rate = rates[key]
        draws[key] = rng.beta(rate * concentration, (1 - rate) * concentration, iterations)
    strikeouts = rng.binomial(bf_samples, draws["k"])
    walks = rng.binomial(bf_samples, draws["bb"])
    hits = rng.binomial(bf_samples, draws["h"])
    earned_runs = rng.poisson(rng.gamma(4.5, earned / 4.5, iterations))

    quality_start = np.where((outs_samples >= 18) & (earned_runs <= 3), 4.0, 0.0)
    starter_win = (
        min(max(win_probability * 0.80, 0.15), 0.65) if win_probability is not None else 0.40
    )
    draftkings = (
        outs_samples * 0.75 + strikeouts * 2.0 - earned_runs * 2.0 - hits * 0.6 - walks * 0.6
    )
    prizepicks = (
        outs_samples + strikeouts * 3.0 - earned_runs * 3.0 + quality_start + 6.0 * starter_win
    )

    distributions = {
        "K": _distribution(strikeouts),
        "BB": _distribution(walks),
        "H": _distribution(hits),
        "ER": _distribution(earned_runs),
        "Outs": _distribution(outs_samples),
        "Fantasy": _distribution(draftkings),
        "PP_Fantasy": _distribution(prizepicks),
    }
    base = "high" if pitcher.starts >= 8 else "medium" if pitcher.starts >= 4 else "low"
    confidence = {
        market: "low" if market in LOW_CONFIDENCE_MARKETS else base for market in distributions
    }
    return StartProjection(
        outs=round(outs, 2),
        batters_faced=round(batters_faced, 2),
        rates={key: round(value, 4) for key, value in rates.items()},
        means={
            "K": round(rates["k"] * batters_faced, 2),
            "BB": round(rates["bb"] * batters_faced, 2),
            "H": round(rates["h"] * batters_faced, 2),
            "ER": round(earned, 2),
            "Outs": round(outs, 2),
        },
        distributions=distributions,
        confidence=confidence,
        sample={
            "prior_starts": pitcher.starts,
            "prior_batters_faced": round(float(pitcher.batters_faced), 1),
            "opponent_games": opponent.games,
            "iterations": iterations,
            "engine": "challenger-sp-2026.08",
        },
    )


def fit_constants(frame, priors: dict[str, float]) -> dict:
    """Re-fit the shrinkage strengths and opponent weights from a walk-forward frame.

    Expects the frame produced by ``mlbmodel.backtest.sp_backtest.build_dataset``.
    Returns a dict shaped like ``FITTED`` so the result can be diffed before adoption.
    """
    from scipy.optimize import minimize

    from mlbmodel.backtest.sp_backtest import shrunk_rate

    def bounded(value, low, high):
        return min(max(value, low), high)

    result: dict[str, dict] = {}
    for key, column in (("k", "K"), ("bb", "BB"), ("h", "H"), ("hr", "HR")):
        actual = (frame[column] / frame["bf"]).to_numpy(dtype=float)

        def loss(params):
            pk = bounded(params[0], 25.0, 1500.0)
            ok = bounded(params[1], 150.0, 3000.0)
            weight = bounded(params[2], 0.0, 1.0)
            own = shrunk_rate(frame[f"p_{key}_num"], frame["p_bf"], priors[key], pk)
            theirs = shrunk_rate(frame[f"o_{key}_num"], frame["o_bf"], priors[key], ok)
            blended = np.array(
                [_log5(a, b, priors[key], weight) for a, b in zip(own, theirs)]
            )
            return float(np.mean((blended - actual) ** 2))

        best = minimize(loss, x0=[150.0, 600.0, 0.4], method="Nelder-Mead",
                        options={"maxiter": 2000, "fatol": 1e-12})
        result[key] = {
            "pitcher_bf": round(bounded(best.x[0], 25.0, 1500.0), 1),
            "opponent_bf": round(bounded(best.x[1], 150.0, 3000.0), 1),
            "opponent_weight": round(bounded(best.x[2], 0.0, 1.0), 3),
        }

    best_outs = None
    for weight in np.linspace(0, 1, 41):
        blend = weight * frame["p_outs_l3"] + (1 - weight) * frame["p_outs_mean"]
        for strength in np.linspace(0.25, 20, 80):
            projected = priors["outs"] + (blend - priors["outs"]) * (
                frame["p_starts"] / (frame["p_starts"] + strength)
            )
            value = float(np.mean((projected - frame["outs"]) ** 2))
            if best_outs is None or value < best_outs[0]:
                best_outs = (value, float(weight), float(strength))
    result["outs"] = {
        "recent_weight": round(best_outs[1], 2),
        "shrink_starts": round(best_outs[2], 2),
    }
    return result


def form_from_frame_row(row) -> tuple[StarterForm, OpponentForm]:
    """Adapt one row of the backtest frame into the engine's inputs."""
    def value(name, default=0.0):
        item = row[name]
        return default if item is None or (isinstance(item, float) and math.isnan(item)) else item

    pitcher = StarterForm(
        starts=int(value("p_starts")),
        batters_faced=float(value("p_bf")),
        outs_total=float(value("p_outs_total")),
        outs_mean=float(value("p_outs_mean", LEAGUE_PRIORS["outs"])),
        outs_last3=float(value("p_outs_l3", LEAGUE_PRIORS["outs"])),
        strikeouts=float(value("p_k_num")),
        walks=float(value("p_bb_num")),
        hits=float(value("p_h_num")),
        homers=float(value("p_hr_num")),
        earned_runs=float(value("p_er_num")),
    )
    opponent = OpponentForm(
        games=int(value("o_games")),
        batters_faced=float(value("o_bf")),
        outs=float(value("o_outs")),
        strikeouts=float(value("o_k_num")),
        walks=float(value("o_bb_num")),
        hits=float(value("o_h_num")),
        homers=float(value("o_hr_num")),
        earned_runs=float(value("o_er_num")),
    )
    return pitcher, opponent
