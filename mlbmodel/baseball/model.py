"""Transparent expected-runs baseline and its exact factor attribution."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from mlbmodel import settings
from mlbmodel.baseball.context import (
    confidence_from_coverage,
    travel_offense_factor,
    umpire_run_factor,
    weather_run_factor,
)
from mlbmodel.baseball.metrics import (
    offense_depth_factor,
    platoon_metric_factor,
    signal_confidence_modifier,
    team_pitching_score_factor,
    trend_run_factor,
)
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
    abq_l7: float | None = None
    abq_l14: float | None = None
    rcv_l7: float | None = None
    rcv_l14: float | None = None
    oor: float | None = None
    woba: float | None = None
    platoon_osi: float | None = None
    abq_vs_lhp: float | None = None
    abq_vs_rhp: float | None = None
    rcv_vs_lhp: float | None = None
    rcv_vs_rhp: float | None = None
    obr_vs_lhp: float | None = None
    obr_vs_rhp: float | None = None
    bullpen_era: float | None = None
    bullpen_high_lev_era: float | None = None
    bullpen_osi_allowed: float | None = None
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
    mlb_game_pk: int | None = None
    live_context: dict = field(default_factory=dict)
    away_starter_features: dict = field(default_factory=dict)
    home_starter_features: dict = field(default_factory=dict)
    away_bullpen_features: dict = field(default_factory=dict)
    home_bullpen_features: dict = field(default_factory=dict)
    away_lineup_features: dict = field(default_factory=dict)
    home_lineup_features: dict = field(default_factory=dict)
    away_injury_features: dict = field(default_factory=dict)
    home_injury_features: dict = field(default_factory=dict)
    away_arsenal_features: dict = field(default_factory=dict)
    home_arsenal_features: dict = field(default_factory=dict)
    trend_features: dict = field(default_factory=dict)
    away_starter_profile: dict = field(default_factory=dict)
    home_starter_profile: dict = field(default_factory=dict)
    away_defense_factor: float = 1.0
    home_defense_factor: float = 1.0
    game_signals: list = field(default_factory=list)
    game_convergence: list = field(default_factory=list)
    context_coverage_pct: int = 0
    missing_context: list[str] = field(default_factory=list)


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
    data_coverage_pct: int = 0
    missing_context: list[str] = field(default_factory=list)
    confidence: str = "low"


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


def staff_factor(
    starter: dict,
    bullpen: dict,
    *,
    fallback_fip: float | None,
    fallback_pen_factor: float,
    team_pitching_score: float | None = None,
) -> float:
    if not starter and not bullpen:
        return pitch_factor(fallback_fip, fallback_pen_factor)
    starter_skill = float(starter.get("skill_fip") or fallback_fip or settings.LEAGUE_FIP)
    starter_innings = clip(float(starter.get("expected_ip") or 5.2), 3.0, 7.3)
    bullpen_skill = float(
        bullpen.get("skill_fip") or settings.LEAGUE_BULLPEN_ERA
    )
    workload = float(bullpen.get("workload_factor") or 1.0)
    starter_component = starter_skill / settings.LEAGUE_FIP
    bullpen_component = bullpen_skill / settings.LEAGUE_BULLPEN_ERA * workload
    starter_share = clip(starter_innings / 9, 0.38, 0.81)
    raw = starter_component * starter_share + bullpen_component * (1 - starter_share)
    skill_mult = float(starter.get("skill_multiplier") or 1.0)
    pen_mult = float(bullpen.get("pen_multiplier") or 1.0)
    raw *= skill_mult * pen_mult
    raw *= team_pitching_score_factor(team_pitching_score)
    return _regress(clip(raw, *settings.PITCH_FACTOR_CLIP))


def arsenal_factor(features: dict) -> float:
    """Fold the opposing starter's pitch-mix (arsenal-vs-lineup) response into team runs.

    The props engine already computes a bounded per-pitch response (usage-weighted whiff /
    xwOBA / chase edges vs a league per-pitch baseline) and zeroes it below 35% arsenal
    coverage, so a missing/low-coverage matchup arrives here as 1.0. We clip it tighter than
    the props value and regress it, because this signal partially overlaps the lineup/platoon
    value already applied to the same runs.
    """
    er_factor = (features or {}).get("er_factor")
    if not isinstance(er_factor, (int, float)):
        return 1.0
    return _regress(clip(float(er_factor), *settings.ARSENAL_FACTOR_CLIP))


def platoon_factor(context: TeamContext, baseline_osi: float | None) -> float:
    if context.platoon_osi is None or baseline_osi is None:
        return 1.0
    return clip(1 + (context.platoon_osi - baseline_osi) * 0.003, 0.94, 1.06)


def model_probabilities(gd: GameData, anchors: dict[str, float]) -> Probabilities:
    league = anchors["league_runs"]
    away_off = offense_factor(gd.away_osi)
    home_off = offense_factor(gd.home_osi)
    away_depth, _ = offense_depth_factor(gd.away_context, gd.away_osi)
    home_depth, _ = offense_depth_factor(gd.home_context, gd.home_osi)
    away_platoon = platoon_factor(gd.away_context, gd.away_osi)
    home_platoon = platoon_factor(gd.home_context, gd.home_osi)
    away_metric_platoon = platoon_metric_factor(gd.away_context, gd.home_hand)
    home_metric_platoon = platoon_metric_factor(gd.home_context, gd.away_hand)
    away_trend = trend_run_factor(gd.trend_features, "away")
    home_trend = trend_run_factor(gd.trend_features, "home")
    away_lineup = float(gd.away_lineup_features.get("factor") or 1.0)
    home_lineup = float(gd.home_lineup_features.get("factor") or 1.0)
    away_injury = float(gd.away_injury_features.get("factor") or 1.0)
    home_injury = float(gd.home_injury_features.get("factor") or 1.0)
    travel = gd.live_context.get("travel") or {}
    away_travel = travel_offense_factor(travel.get("away"))
    home_travel = travel_offense_factor(travel.get("home"))
    away_pitch = staff_factor(
        gd.home_starter_features,
        gd.home_bullpen_features,
        fallback_fip=gd.home_fip,
        fallback_pen_factor=gd.home_pen_factor,
        team_pitching_score=gd.home_context.avg_pitching_score,
    )
    home_pitch = staff_factor(
        gd.away_starter_features,
        gd.away_bullpen_features,
        fallback_fip=gd.away_fip,
        fallback_pen_factor=gd.away_pen_factor,
        team_pitching_score=gd.away_context.avg_pitching_score,
    )
    weather = weather_run_factor(gd.weather)
    umpire = umpire_run_factor(gd.live_context.get("umpire"))

    factors: list[FactorContribution] = []

    def apply_side(
        current: float,
        factor: float,
        *,
        name: str,
        side: str,
        markets: str,
        confidence: str,
        source: str,
        include: bool = True,
    ) -> float:
        updated = current * factor
        if include:
            factors.append(
                FactorContribution(
                    name, side, factor, updated - current, markets, confidence, source
                )
            )
        return updated

    exp_away = apply_side(
        league, away_off, name=f"{gd.away} season offense", side=gd.away,
        markets="Away runs / Total / ML", confidence="medium",
        source="MLBMA team offense strength",
    )
    exp_home_pre_hfa = apply_side(
        league, home_off, name=f"{gd.home} season offense", side=gd.home,
        markets="Home runs / Total / ML", confidence="medium",
        source="MLBMA team offense strength",
    )
    exp_away = apply_side(
        exp_away, away_depth, name=f"{gd.away} offense depth (ABQ/RCV/PALS/proj)",
        side=gd.away, markets="Away runs / Total / ML", confidence="medium",
        source="MLBMA composite offense metrics + recent form",
        include=away_depth != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_depth, name=f"{gd.home} offense depth (ABQ/RCV/PALS/proj)",
        side=gd.home, markets="Home runs / Total / ML", confidence="medium",
        source="MLBMA composite offense metrics + recent form",
        include=home_depth != 1.0,
    )
    exp_away = apply_side(
        exp_away, away_platoon, name=f"{gd.away} offense vs {gd.home_hand}HP",
        side=gd.away, markets="Away runs / pitcher props", confidence="medium",
        source="MLBMA team handedness split", include=away_platoon != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_platoon, name=f"{gd.home} offense vs {gd.away_hand}HP",
        side=gd.home, markets="Home runs / pitcher props", confidence="medium",
        source="MLBMA team handedness split", include=home_platoon != 1.0,
    )
    exp_away = apply_side(
        exp_away, away_metric_platoon, name=f"{gd.away} platoon metrics vs {gd.home_hand}HP",
        side=gd.away, markets="Away runs / pitcher props", confidence="medium",
        source="MLBMA ABQ/RCV/OBR handedness splits",
        include=away_metric_platoon != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_metric_platoon,
        name=f"{gd.home} platoon metrics vs {gd.away_hand}HP",
        side=gd.home, markets="Home runs / pitcher props", confidence="medium",
        source="MLBMA ABQ/RCV/OBR handedness splits",
        include=home_metric_platoon != 1.0,
    )
    exp_away = apply_side(
        exp_away, away_lineup, name=f"{gd.away} posted lineup vs {gd.home_hand}HP",
        side=gd.away, markets="Away runs / pitcher props", confidence="high",
        source="MLB lineup + MLBMA batter split value",
        include=gd.away_lineup_features.get("status") in {"confirmed", "projected"},
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_lineup, name=f"{gd.home} posted lineup vs {gd.away_hand}HP",
        side=gd.home, markets="Home runs / pitcher props", confidence="high",
        source="MLB lineup + MLBMA batter split value",
        include=gd.home_lineup_features.get("status") in {"confirmed", "projected"},
    )
    exp_away = apply_side(
        exp_away, away_injury, name=f"{gd.away} unavailable hitters",
        side=gd.away, markets="Away runs / Total / ML", confidence="medium",
        source="Official MLB injured list + MLBMA batter value",
        include=away_injury != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_injury, name=f"{gd.home} unavailable hitters",
        side=gd.home, markets="Home runs / Total / ML", confidence="medium",
        source="Official MLB injured list + MLBMA batter value",
        include=home_injury != 1.0,
    )
    exp_away = apply_side(
        exp_away, away_travel, name=f"{gd.away} rest and travel",
        side=gd.away, markets="Away runs / Total / ML", confidence="low",
        source="MLB schedule + venue distance/timezone", include=away_travel != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_travel, name=f"{gd.home} rest and travel",
        side=gd.home, markets="Home runs / Total / ML", confidence="low",
        source="MLB schedule + venue distance/timezone", include=home_travel != 1.0,
    )
    exp_away = apply_side(
        exp_away, away_trend, name=f"{gd.away} situational trends",
        side=gd.away, markets="Away runs / Total / ML", confidence="low",
        source="MLBMA trend detectors (form, pen fatigue, park)",
        include=away_trend != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_trend, name=f"{gd.home} situational trends",
        side=gd.home, markets="Home runs / Total / ML", confidence="low",
        source="MLBMA trend detectors (form, pen fatigue, park)",
        include=home_trend != 1.0,
    )
    exp_away = apply_side(
        exp_away, away_pitch, name=f"{gd.home} starter and bullpen",
        side=gd.away, markets="Away runs / Total / ML", confidence="medium",
        source="MLBMA starter season/L14 + bullpen quality/workload/roles",
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_pitch, name=f"{gd.away} starter and bullpen",
        side=gd.home, markets="Home runs / Total / ML", confidence="medium",
        source="MLBMA starter season/L14 + bullpen quality/workload/roles",
    )
    exp_away = apply_side(
        exp_away, gd.home_defense_factor, name=f"{gd.home} fielding / run prevention",
        side=gd.away, markets="Away runs / Total / ML", confidence="low",
        source="MLBMA team run prevention + optional defensive ratings",
        include=gd.home_defense_factor != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, gd.away_defense_factor, name=f"{gd.away} fielding / run prevention",
        side=gd.home, markets="Home runs / Total / ML", confidence="low",
        source="MLBMA team run prevention + optional defensive ratings",
        include=gd.away_defense_factor != 1.0,
    )
    away_arsenal = arsenal_factor(gd.away_arsenal_features)
    home_arsenal = arsenal_factor(gd.home_arsenal_features)
    exp_away = apply_side(
        exp_away, away_arsenal, name=f"{gd.home_sp} arsenal vs {gd.away} lineup",
        side=gd.away, markets="Away runs / Total / pitcher props", confidence="medium",
        source="MLBMA pitch-mix arsenal vs lineup per-pitch response",
        include=away_arsenal != 1.0,
    )
    exp_home_pre_hfa = apply_side(
        exp_home_pre_hfa, home_arsenal, name=f"{gd.away_sp} arsenal vs {gd.home} lineup",
        side=gd.home, markets="Home runs / Total / pitcher props", confidence="medium",
        source="MLBMA pitch-mix arsenal vs lineup per-pitch response",
        include=home_arsenal != 1.0,
    )

    def apply_shared(
        away_runs: float,
        home_runs: float,
        factor: float,
        *,
        name: str,
        confidence: str,
        source: str,
        include: bool = True,
    ) -> tuple[float, float]:
        updated_away = away_runs * factor
        updated_home = home_runs * factor
        if include:
            factors.append(
                FactorContribution(
                    name,
                    "Both",
                    factor,
                    (updated_away - away_runs) + (updated_home - home_runs),
                    "Total / Team totals",
                    confidence,
                    source,
                )
            )
        return updated_away, updated_home

    exp_away, exp_home_pre_hfa = apply_shared(
        exp_away, exp_home_pre_hfa, gd.park_factor,
        name="Ballpark run environment", confidence="medium",
        source="MLBMA park factors",
    )
    exp_away, exp_home_pre_hfa = apply_shared(
        exp_away, exp_home_pre_hfa, weather,
        name="First-pitch weather", confidence="medium",
        source="Open-Meteo forecast + MLB field orientation",
        include=weather != 1.0 or bool(gd.weather.get("dome")),
    )
    exp_away, exp_home_pre_hfa = apply_shared(
        exp_away, exp_home_pre_hfa, umpire,
        name="Home-plate umpire run environment", confidence="low",
        source="MLB official assignment + shrunk prior game totals",
        include=(gd.live_context.get("umpire") or {}).get("status") == "announced",
    )
    exp_home = exp_home_pre_hfa + settings.HFA_RUNS
    factors.append(
        FactorContribution(
            "Home field", gd.home, 1.0, settings.HFA_RUNS,
            "ML", "medium", "empirical home-field anchor",
        )
    )

    exp_total = exp_away + exp_home
    exp_margin = exp_home - exp_away
    p_home_model = normal_cdf(exp_margin / anchors["margin_sd"])
    base = anchors["home_winp"] / (anchors["home_winp"] + anchors["away_winp"])
    p_home = clip(0.85 * p_home_model + 0.15 * base, 0.05, 0.95)
    starts = min(
        int(gd.away_starter_features.get("starts") or 0),
        int(gd.home_starter_features.get("starts") or 0),
    )
    confidence = signal_confidence_modifier(
        gd.game_signals,
        gd.away,
        gd.home,
        confidence_from_coverage(gd.context_coverage_pct, starts),
        convergence=gd.game_convergence,
    )
    return Probabilities(
        exp_away_runs=round(exp_away, 2),
        exp_home_runs=round(exp_home, 2),
        exp_total=round(exp_total, 2),
        exp_margin=round(exp_margin, 2),
        p_home_win=round(p_home, 4),
        p_away_win=round(1 - p_home, 4),
        factors=factors,
        data_coverage_pct=gd.context_coverage_pct,
        missing_context=list(gd.missing_context),
        confidence=confidence,
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
