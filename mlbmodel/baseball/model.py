"""Transparent expected-runs baseline and its exact factor attribution."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from mlbmodel import settings
from mlbmodel.market.oddsmath import prob_to_american


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


@dataclass
class TeamContext:
    osi: float | None = None
    abq: float | None = None
    rcv: float | None = None
    obr: float | None = None
    pals: float | None = None
    proj_osi: float | None = None
    osi_l7: float | None = None
    osi_l14: float | None = None
    woba: float | None = None
    platoon_osi: float | None = None
    bullpen_era: float | None = None
    bullpen_high_lev_era: float | None = None
    avg_pitching_score: float | None = None
    window_direction: str | None = None


@dataclass
class GameData:
    game_pk: int
    game_date: str
    start_time: str
    away: str
    home: str
    away_sp: str
    home_sp: str
    away_hand: str
    home_hand: str
    away_osi: float | None
    home_osi: float | None
    away_fip: float | None
    home_fip: float | None
    away_hr9: float | None
    home_hr9: float | None
    away_k: float | None
    home_k: float | None
    park_factor: float
    weather: dict = field(default_factory=dict)
    away_pen_factor: float = 1.0
    home_pen_factor: float = 1.0
    away_context: TeamContext = field(default_factory=TeamContext)
    home_context: TeamContext = field(default_factory=TeamContext)
    source_updated_at: str | None = None


@dataclass(frozen=True)
class FactorContribution:
    name: str
    side: str
    multiplier: float
    run_delta: float
    markets: str
    confidence: str
    source: str


@dataclass
class Probabilities:
    exp_away_runs: float
    exp_home_runs: float
    exp_total: float
    exp_margin: float
    p_home_win: float
    p_away_win: float
    factors: list[FactorContribution]


def _regress(factor: float) -> float:
    return 1 + (factor - 1) * (1 - settings.REGRESSION_TO_MEAN)


def offense_factor(osi: float | None) -> float:
    if osi is None:
        return 1.0
    raw = clip(
        1 + (osi - 50) / 100 * settings.OSI_RUN_SENSITIVITY,
        *settings.OFF_FACTOR_CLIP,
    )
    return _regress(raw)


def pitch_factor(opp_sp_fip: float | None, opp_pen_factor: float = 1.0) -> float:
    sp = (
        1.0
        if opp_sp_fip is None
        else clip(opp_sp_fip / settings.LEAGUE_FIP, *settings.PITCH_FACTOR_CLIP)
    )
    pen = clip(opp_pen_factor, *settings.PITCH_FACTOR_CLIP)
    blended = settings.SP_FIP_WEIGHT * sp + (1 - settings.SP_FIP_WEIGHT) * pen
    return _regress(blended)


def model_probabilities(gd: GameData, anchors: dict[str, float]) -> Probabilities:
    league = anchors["league_runs"]
    away_off = offense_factor(gd.away_osi)
    home_off = offense_factor(gd.home_osi)
    away_pitch = pitch_factor(gd.home_fip, gd.home_pen_factor)
    home_pitch = pitch_factor(gd.away_fip, gd.away_pen_factor)

    exp_away = league * away_off * away_pitch * gd.park_factor
    exp_home_pre_hfa = league * home_off * home_pitch * gd.park_factor
    exp_home = exp_home_pre_hfa + settings.HFA_RUNS

    factors = [
        FactorContribution(
            f"{gd.away} offense (OSI)", gd.away, away_off,
            league * (away_off - 1), "Away TT / Total / ML", "medium",
            "MLBMA team_profiles.osi",
        ),
        FactorContribution(
            f"{gd.home} offense (OSI)", gd.home, home_off,
            league * (home_off - 1), "Home TT / Total / ML", "medium",
            "MLBMA team_profiles.osi",
        ),
        FactorContribution(
            f"{gd.home} staff run allowance", gd.away, away_pitch,
            league * away_off * (away_pitch - 1), "Away TT / Total / ML", "medium",
            "MLBMA sp_profiles.FIP + team_profiles bullpen",
        ),
        FactorContribution(
            f"{gd.away} staff run allowance", gd.home, home_pitch,
            league * home_off * (home_pitch - 1), "Home TT / Total / ML", "medium",
            "MLBMA sp_profiles.FIP + team_profiles bullpen",
        ),
        FactorContribution(
            "Park environment", "Both", gd.park_factor,
            (exp_away + exp_home_pre_hfa) * (gd.park_factor - 1) / gd.park_factor,
            "Total / Team totals", "medium", "MLBMA park factors",
        ),
        FactorContribution(
            "Home field", gd.home, 1.0,
            settings.HFA_RUNS, "ML", "medium", "empirical home-field anchor",
        ),
    ]

    exp_total = exp_away + exp_home
    exp_margin = exp_home - exp_away
    p_home_model = normal_cdf(exp_margin / anchors["margin_sd"])
    base = anchors["home_winp"] / (anchors["home_winp"] + anchors["away_winp"])
    p_home = clip(0.85 * p_home_model + 0.15 * base, 0.05, 0.95)
    return Probabilities(
        exp_away_runs=round(exp_away, 2),
        exp_home_runs=round(exp_home, 2),
        exp_total=round(exp_total, 2),
        exp_margin=round(exp_margin, 2),
        p_home_win=round(p_home, 4),
        p_away_win=round(1 - p_home, 4),
        factors=factors,
    )


def _resolve_side_team(side: str, gd: GameData) -> str:
    value = side.strip().upper()
    if value in ("HOME", gd.home):
        return gd.home
    if value in ("AWAY", gd.away):
        return gd.away
    raise ValueError(f"side must be {gd.away}, {gd.home}, home, or away")


def market_probability(
    market: str,
    side: str,
    line: float | None,
    gd: GameData,
    probs: Probabilities,
    anchors: dict[str, float],
    ou: str | None = None,
) -> tuple[float, str]:
    market = market.lower()
    if market == "ml":
        team = _resolve_side_team(side, gd)
        probability = probs.p_home_win if team == gd.home else probs.p_away_win
        return probability, f"{team} ML"
    if market == "total":
        if line is None:
            raise ValueError("total requires a line")
        p_over = 1 - normal_cdf((line - probs.exp_total) / anchors["total_sd"])
        return (p_over, f"Over {line:g}") if side.lower() == "over" else (
            1 - p_over,
            f"Under {line:g}",
        )
    if market == "team_total":
        if line is None:
            raise ValueError("team total requires a line")
        team = _resolve_side_team(side, gd)
        expected = probs.exp_home_runs if team == gd.home else probs.exp_away_runs
        p_over = 1 - normal_cdf((line - expected) / anchors["team_sd"])
        direction = (ou or "over").lower()
        return (p_over, f"{team} TT Over {line:g}") if direction == "over" else (
            1 - p_over,
            f"{team} TT Under {line:g}",
        )
    if market == "runline":
        if line is None:
            raise ValueError("run line requires a line")
        team = _resolve_side_team(side, gd)
        margin = probs.exp_margin if team == gd.home else -probs.exp_margin
        p_cover = 1 - normal_cdf((-line - margin) / anchors["margin_sd"])
        return p_cover, f"{team} {line:+g}"
    raise ValueError(f"unsupported market: {market}")


def fair_price(probability: float) -> int:
    return prob_to_american(clip(probability, 0.02, 0.98))
