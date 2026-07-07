"""MLBMA metric → run-factor conversions (every synced coin turned)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from mlbmodel import settings

if TYPE_CHECKING:
    from mlbmodel.baseball.model import TeamContext

LEAGUE_AVG = 50.0
OSI_W_ABQ = 0.25
OSI_W_RCV = 0.35
OSI_W_OBR = 0.40


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _regress(factor: float) -> float:
    return 1 + (factor - 1) * (1 - settings.REGRESSION_TO_MEAN)


def _metric_delta(value: float | None, *, sensitivity: float) -> float:
    if value is None:
        return 0.0
    return (float(value) - LEAGUE_AVG) * sensitivity


def metric_run_factor(value: float | None, *, sensitivity: float = 0.004) -> float:
    """Convert a 50=avg MLBMA index into a bounded run multiplier."""
    if value is None:
        return 1.0
    raw = _clip(1 + _metric_delta(value, sensitivity=sensitivity), 0.94, 1.06)
    return _regress(raw)


def composite_offense_score(
    context: TeamContext,
    slate_osi: float | None,
) -> tuple[float, dict[str, float]]:
    """Blend season OSI with ABQ/RCV/OBR/PALS/projOSI and recent windows."""
    base = slate_osi if slate_osi is not None else context.osi
    if base is None:
        base = LEAGUE_AVG

    parts: list[tuple[float, float]] = [(base, 0.55)]
    if context.abq is not None:
        parts.append((context.abq, OSI_W_ABQ * 0.45))
    if context.rcv is not None:
        parts.append((context.rcv, OSI_W_RCV * 0.45))
    if context.obr is not None:
        parts.append((context.obr, OSI_W_OBR * 0.45))
    if context.pals is not None:
        parts.append((context.pals, settings.PALS_BLEND_WEIGHT))
    if context.proj_osi is not None:
        parts.append((context.proj_osi, settings.PROJ_OSI_BLEND_WEIGHT))
    if context.oor is not None:
        parts.append((context.oor, 0.06))

    weight_sum = sum(weight for _, weight in parts)
    score = sum(value * weight for value, weight in parts) / weight_sum

    recent_boost = 0.0
    if context.osi_l7 is not None and context.osi_l14 is not None:
        recent_boost += (context.osi_l7 - context.osi_l14) * 0.12
    if context.abq_l7 is not None and context.abq_l14 is not None:
        recent_boost += (context.abq_l7 - context.abq_l14) * 0.06
    if context.rcv_l7 is not None and context.rcv_l14 is not None:
        recent_boost += (context.rcv_l7 - context.rcv_l14) * 0.06
    score = _clip(score + recent_boost, 35.0, 65.0)

    detail = {
        "base_osi": base,
        "composite": score,
        "recent_boost": recent_boost,
    }
    return score, detail


def offense_depth_factor(
    context: TeamContext,
    slate_osi: float | None,
) -> tuple[float, dict[str, float]]:
    """Incremental offense adjustment beyond the primary OSI step."""
    score, detail = composite_offense_score(context, slate_osi)
    primary = slate_osi if slate_osi is not None else context.osi or LEAGUE_AVG
    delta = score - primary
    if abs(delta) < 0.15:
        return 1.0, detail
    raw = _clip(1 + delta * settings.METRIC_RUN_SENSITIVITY, *settings.OFF_DEPTH_CLIP)
    detail["factor"] = _regress(raw)
    return detail["factor"], detail


def platoon_metric_factor(context: TeamContext, opposing_hand: str) -> float:
    """Handedness-specific ABQ/RCV/OBR platoon splits when available."""
    suffix = "lhp" if opposing_hand == "L" else "rhp"
    metrics = (
        getattr(context, f"abq_vs_{suffix}", None),
        getattr(context, f"rcv_vs_{suffix}", None),
        getattr(context, f"obr_vs_{suffix}", None),
    )
    values = [value for value in metrics if value is not None]
    if not values:
        return 1.0
    platoon_avg = sum(values) / len(values)
    season_avg = _season_metric_avg(context)
    if season_avg is None:
        return metric_run_factor(platoon_avg, sensitivity=0.0025)
    return _clip(
        1 + (platoon_avg - season_avg) * 0.003,
        0.97,
        1.03,
    )


def _season_metric_avg(context: TeamContext) -> float | None:
    parts = [context.abq, context.rcv, context.obr]
    values = [value for value in parts if value is not None]
    return sum(values) / len(values) if values else None


def opponent_offense_strength(context: TeamContext, slate_osi: float | None) -> float:
    score, _ = composite_offense_score(context, slate_osi)
    return score


def pitcher_allowed_skill_adjustment(
    profile: dict | None,
    opponent_strength: float,
) -> float:
    """Scale opposing staff skill from OSI/ABQ/RCV/OBR allowed + tier ERAs."""
    if not profile:
        return 1.0
    allowed_parts: list[tuple[float, float]] = []
    for key, weight in (
        ("OSI_allowed", 0.35),
        ("ABQ_allowed", 0.25),
        ("RCV_allowed", 0.25),
        ("OBR_allowed", 0.15),
    ):
        value = _number(profile.get(key))
        if value is not None:
            allowed_parts.append((value, weight))
    factor = 1.0
    if allowed_parts:
        allowed = sum(value * weight for value, weight in allowed_parts) / sum(
            weight for _, weight in allowed_parts
        )
        tier = (opponent_strength - LEAGUE_AVG) / 50.0
        factor *= _clip(
            1 + tier * (allowed - LEAGUE_AVG) * settings.ALLOWED_METRIC_SENSITIVITY,
            0.94,
            1.06,
        )

    low_era = _number(profile.get("low_osi_ERA"))
    high_era = _number(profile.get("high_osi_ERA"))
    if low_era is not None and high_era is not None:
        if opponent_strength >= 53:
            tier_era = high_era
        elif opponent_strength <= 47:
            tier_era = low_era
        else:
            tier_era = (low_era + high_era) / 2
        league_era = settings.LEAGUE_FIP * 0.95
        factor *= _clip(tier_era / league_era, 0.92, 1.08)

    oor = _number(profile.get("OOR_faced"))
    if oor is not None:
        factor *= _clip(1 + (oor - LEAGUE_AVG) * 0.002, 0.97, 1.03)

    pitching_score = _number(profile.get("Pitching_Score")) or _number(
        profile.get("pitching_score")
    )
    if pitching_score is not None:
        factor *= _clip(1 - (pitching_score - LEAGUE_AVG) * 0.002, 0.95, 1.05)

    return _regress(_clip(factor, 0.90, 1.10))


def sp_split_skill_adjustment(
    profile: dict | None,
    split_rows: list[dict],
    opposing_hand: str,
) -> float:
    """Handedness metric splits (K%, BB%, HR9, FIP) from sp_metric_splits."""
    if not profile or not split_rows:
        return 1.0
    pitcher_id = str(profile.get("pitcher_id") or "")
    split_key = "vs_LHB" if opposing_hand == "L" else "vs_RHB"
    row = next(
        (
            candidate
            for candidate in split_rows
            if str(candidate.get("pitcher_id") or "") == pitcher_id
            and str(candidate.get("split") or candidate.get("split_type") or "")
            .upper()
            .startswith(split_key[:5])
        ),
        None,
    )
    if row is None:
        row = next(
            (
                candidate
                for candidate in split_rows
                if str(candidate.get("pitcher_name") or "").lower()
                == str(profile.get("pitcher_name") or "").lower()
                and split_key[:5] in str(candidate.get("split") or "").upper()
            ),
            None,
        )
    if row is None:
        return 1.0

    season_fip = _number(profile.get("FIP")) or settings.LEAGUE_FIP
    split_fip = _number(row.get("FIP")) or season_fip
    split_k = _percent(row.get("K%")) or _percent(row.get("K_pct"))
    season_k = _percent(profile.get("K_pct"))
    factor = 1.0
    if split_fip and season_fip:
        factor *= _clip(split_fip / season_fip, 0.92, 1.08)
    if split_k is not None and season_k is not None:
        factor *= _clip(1 - (split_k - season_k) * 0.004, 0.97, 1.03)
    return _regress(_clip(factor, 0.94, 1.06))


def bullpen_platoon_adjustment(row: dict | None, opposing_hand: str) -> float:
    """Bullpen FIP vs LHB/RHB when split columns exist."""
    if not row:
        return 1.0
    key = "vs_lhp_FIP" if opposing_hand == "L" else "vs_rhp_FIP"
    alt = "vs_LHP_FIP" if opposing_hand == "L" else "vs_RHP_FIP"
    split_fip = _number(row.get(key)) or _number(row.get(alt))
    overall = _number(row.get("overall_FIP")) or settings.LEAGUE_BULLPEN_ERA
    if split_fip is None:
        return 1.0
    return _regress(_clip(split_fip / overall, 0.94, 1.06))


def bullpen_allowed_adjustment(
    bullpen_osi_allowed: float | None,
    opponent_strength: float,
) -> float:
    if bullpen_osi_allowed is None:
        return 1.0
    tier = (opponent_strength - LEAGUE_AVG) / 50.0
    return _regress(
        _clip(
            1 + tier * (bullpen_osi_allowed - LEAGUE_AVG) * settings.ALLOWED_METRIC_SENSITIVITY,
            0.97,
            1.03,
        )
    )


def trend_run_factor(features: dict | None, side: str) -> float:
    """Map situational-trend feature row to a bounded run multiplier."""
    if not features:
        return 1.0
    prefix = "away" if side == "away" else "home"
    opp = "home" if side == "away" else "away"
    offense = float(features.get(f"{prefix}_offense_trend_signal") or 0.0)
    pen_fatigue = float(features.get(f"{opp}_bullpen_fatigue_signal") or 0.0)
    interaction = float(features.get(f"{prefix}_off_vs_{opp}_pen_interaction") or 0.0)
    park = float(features.get("park_total_signal") or 0.0) * 0.5
    raw = (
        1
        + offense * settings.TREND_RUN_SENSITIVITY
        + pen_fatigue * settings.TREND_PEN_SENSITIVITY
        + interaction * settings.TREND_INTERACTION_SENSITIVITY
        + park * settings.TREND_PARK_SENSITIVITY
    )
    return _regress(_clip(raw, *settings.TREND_FACTOR_CLIP))


def fielding_defense_factor(team_row) -> float:
    """Runs allowed multiplier from fielding / run-prevention profile (<1 = elite defense)."""
    if team_row is None:
        return 1.0
    get = team_row.get if hasattr(team_row, "get") else lambda _k, _d=None: None
    for col in ("defense_rating", "team_oaa", "oaa", "fld_pct"):
        value = _number(get(col))
        if value is not None:
            if col in {"oaa", "team_oaa"}:
                value = LEAGUE_AVG + value * 5.0
            return _regress(
                _clip(1 - (value - LEAGUE_AVG) * 0.003, *settings.DEFENSE_FACTOR_CLIP)
            )
    era = _number(get("team_era"))
    if era is not None:
        return _regress(_clip(era / settings.LEAGUE_TEAM_ERA, *settings.DEFENSE_FACTOR_CLIP))
    allowed = _number(get("bullpen_osi_allowed"))
    if allowed is not None:
        return _regress(
            _clip(1 + (allowed - LEAGUE_AVG) * 0.0015, *settings.DEFENSE_FACTOR_CLIP)
        )
    return 1.0


def signal_edge_adjustment(signals: list[dict], *, side: str) -> float:
    """Additive edge boost from fired MLBMA signals for a lineup side."""
    boost = 0.0
    for row in signals:
        if not row.get("fired"):
            continue
        if str(row.get("side") or "").lower() != side:
            continue
        magnitude = float(row.get("magnitude") or 0.0)
        direction = str(row.get("direction") or "").lower()
        sign = 1.0 if direction in {"boost", "over", "up", "positive", "bullish"} else (
            -1.0 if direction in {"fade", "under", "down", "negative", "bearish"} else 0.0
        )
        boost += sign * magnitude * settings.SIGNAL_EDGE_SCALE
    return _clip(boost, -settings.SIGNAL_EDGE_CAP, settings.SIGNAL_EDGE_CAP)


def signal_confidence_modifier(
    signals: list[dict],
    away: str,
    home: str,
    confidence: str,
) -> str:
    """Bump model confidence when MLBMA signal convergence supports the projection."""
    if not signals:
        return confidence
    fired = sum(1 for row in signals if row.get("fired"))
    if fired >= settings.SIGNAL_HIGH_CONVERGENCE and confidence == "medium":
        return "high"
    if fired == 0 and confidence == "high":
        return "medium"
    return confidence


def _number(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(str(value).replace("%", ""))
        return result if result == result else None  # NaN check
    except (TypeError, ValueError):
        return None


def _percent(value) -> float | None:
    result = _number(value)
    if result is None:
        return None
    return result * 100 if result <= 1.5 else result
