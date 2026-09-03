"""MLBMA metric → run-factor conversions (every synced coin turned)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from mlbmodel import settings
from mlbmodel.genesis.logic_matrix import (
    ALLOWED_METRIC_WEIGHTS,
    COMPOSITE_BASE_WEIGHT,
    CONVERGENCE_THRESHOLD,
    MODEL_SENSITIVITIES,
    composite_metric_weight,
    convergence_for_game,
    convergence_side_row,
)

if TYPE_CHECKING:
    from mlbmodel.baseball.model import TeamContext

LEAGUE_AVG = 50.0


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

    parts: list[tuple[float, float]] = [(base, COMPOSITE_BASE_WEIGHT)]
    if context.abq is not None:
        parts.append((context.abq, composite_metric_weight("abq")))
    if context.rcv is not None:
        parts.append((context.rcv, composite_metric_weight("rcv")))
    if context.obr is not None:
        parts.append((context.obr, composite_metric_weight("obr")))
    if context.pals is not None:
        parts.append((context.pals, settings.PALS_BLEND_WEIGHT))
    if context.proj_osi is not None:
        parts.append((context.proj_osi, settings.PROJ_OSI_BLEND_WEIGHT))
    if context.oor is not None:
        parts.append((context.oor, MODEL_SENSITIVITIES["oor_blend"]))

    weight_sum = sum(weight for _, weight in parts)
    score = sum(value * weight for value, weight in parts) / weight_sum

    recent_boost = 0.0
    if context.osi_l7 is not None and context.osi_l14 is not None:
        recent_boost += (context.osi_l7 - context.osi_l14) * MODEL_SENSITIVITIES["recent_osi"]
    if context.abq_l7 is not None and context.abq_l14 is not None:
        recent_boost += (context.abq_l7 - context.abq_l14) * MODEL_SENSITIVITIES["recent_abq"]
    if context.rcv_l7 is not None and context.rcv_l14 is not None:
        recent_boost += (context.rcv_l7 - context.rcv_l14) * MODEL_SENSITIVITIES["recent_rcv"]
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


# Weight applied to offence readings that re-measure hitters the primary index already
# covers. Measured across the 30 team profiles, the depth composite correlates -0.75 with
# the primary OSI delta — it is acting as regression to the mean, so it is left at full
# weight. The posted lineup and the situational-trend detectors are different: they score
# the same nine hitters and the same recent form the composite's L7/L14 term already reads,
# so at full weight they double-count.
#
# JUDGMENT, NOT A FIT: unlike the starter constants in mlbmodel.props.challenger, this
# cannot yet be fitted, because the warehouse holds no point-in-time team profiles to
# backtest the game model against. It is set to damp the known overlap without erasing the
# signal, and should be re-fit once a forward sample of stored game predictions exists.
SECONDARY_SIGNAL_WEIGHT = 0.60


def _factor_to_index_delta(factor: float) -> float:
    """Invert a run multiplier back into the OSI index points that produced it."""
    scale = settings.OSI_RUN_SENSITIVITY / 100 * (1 - settings.REGRESSION_TO_MEAN)
    if scale <= 0:
        return 0.0
    return (factor - 1.0) / scale


def combined_offense_factor(
    context: TeamContext,
    slate_osi: float | None,
    opposing_hand: str,
    *,
    lineup_factor: float = 1.0,
    trend_factor: float = 1.0,
) -> tuple[float, list[tuple[str, float]]]:
    """One run multiplier for everything that measures *this lineup's quality today*.

    The engine previously multiplied five separate offence factors together — season OSI,
    the ABQ/RCV/PALS/projOSI depth composite, a handedness factor, the handedness metric
    splits, the posted lineup, and situational trends. Those are not independent readings;
    they are six views of the same nine hitters, built from overlapping inputs. Each is
    individually clipped to a few percent, but compounding correlated terms inflates the
    spread far beyond what the underlying signal supports, and that shows up in the ledger
    as the model's confidence being anti-correlated with its results: leans claiming a 4–7
    point edge settled at 21.7%, and the 0.6–0.7 win-probability bucket came in at 0.222.

    Because every one of these terms is derived from a 50-centred index via the same
    sensitivity, the correct combination is to sum the index deltas ONCE and convert ONCE.
    Multiplying the already-converted factors is the error. This returns that single
    multiplier plus each contributor's share of the resulting run delta, so the report can
    still attribute the move honestly.

    `platoon_factor` is deliberately absent: the slate's OSI is already the split against
    the opposing starter's hand (`scrape_matchups.get_team_osi` picks the vs-RHP or vs-LHP
    table), so a separate handedness multiplier re-applied a signal the primary term
    already carried, and measured exactly 1.0000 (sd 0.0001) across a slate.
    """
    primary = slate_osi if slate_osi is not None else (context.osi or LEAGUE_AVG)
    contributions: list[tuple[str, float]] = [("season offense", primary - LEAGUE_AVG)]

    composite, _ = composite_offense_score(context, slate_osi)
    depth_delta = composite - primary
    if abs(depth_delta) >= 0.15:
        contributions.append(("offense depth", depth_delta))

    platoon_delta = _platoon_index_delta(context, opposing_hand)
    if platoon_delta:
        contributions.append(("platoon metrics", platoon_delta))

    for name, factor in (("posted lineup", lineup_factor), ("situational trends", trend_factor)):
        if factor != 1.0:
            contributions.append(
                (name, _factor_to_index_delta(factor) * SECONDARY_SIGNAL_WEIGHT)
            )

    total_delta = sum(delta for _, delta in contributions)
    raw = _clip(
        1 + total_delta / 100 * settings.OSI_RUN_SENSITIVITY, *settings.OFF_FACTOR_CLIP
    )
    return _regress(raw), contributions


def _platoon_index_delta(context: TeamContext, opposing_hand: str) -> float:
    """Handedness split of ABQ/RCV/OBR, as index points against the season average."""
    suffix = "lhp" if opposing_hand == "L" else "rhp"
    values = [
        value
        for value in (
            getattr(context, f"abq_vs_{suffix}", None),
            getattr(context, f"rcv_vs_{suffix}", None),
            getattr(context, f"obr_vs_{suffix}", None),
        )
        if value is not None
    ]
    if not values:
        return 0.0
    season = _season_metric_avg(context)
    if season is None:
        return 0.0
    # Damped: the handedness split is a slice of the same season sample it is compared to,
    # so it is a weaker reading than its raw gap suggests.
    return (sum(values) / len(values) - season) * 0.35


# `platoon_metric_factor` was removed 2026-08-30 and replaced by `_platoon_index_delta`,
# which contributes to the single offense conversion instead of being multiplied in as its
# own factor. Multiplying it compounded with the ABQ/RCV/OBR already inside the depth
# composite it was being compared against.


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
    for key, weight in ALLOWED_METRIC_WEIGHTS.items():
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
        factor *= team_pitching_score_factor(pitching_score)

    return _regress(_clip(factor, 0.90, 1.10))


def team_pitching_score_factor(pitching_score: float | None) -> float:
    """Convert MLBMA Pitching Score (50=avg) into a bounded staff run multiplier."""
    if pitching_score is None:
        return 1.0
    sensitivity = MODEL_SENSITIVITIES["pitching_score_run"]
    return _regress(_clip(1 - (pitching_score - LEAGUE_AVG) * sensitivity, 0.95, 1.05))


# League-average share of plate appearances taken by left-handed batters. Used only when the
# opposing lineup is not posted yet, so the platoon term degrades to the league split rather
# than silently vanishing.
LEAGUE_LHB_SHARE = 0.42
# `sp_metric_splits.csv` stores splits long-form: one row per (pitcher, dimension, value).
_BATTER_HAND_DIMENSION = "batter_hand"
_LHB_VALUES = {"LHH", "LHB", "L", "VS_LHB", "VS_LHH"}
_RHB_VALUES = {"RHH", "RHB", "R", "VS_RHB", "VS_RHH"}


def _split_hand(row: dict) -> str | None:
    """Which batter hand a `sp_metric_splits` row describes, or None if it is not a hand split.

    The file is long-form — `split_dimension` / `split_value` — but earlier revisions of this
    lookup asked for a `split` / `split_type` column that has never existed in it, so the
    match failed for every pitcher on every slate and the platoon term was a constant 1.0
    league-wide. Both spellings are accepted here so a schema change cannot silently disable
    the factor again; `tests/test_sp_platoon.py` asserts the file actually resolves.
    """
    dimension = str(row.get("split_dimension") or "").strip().lower()
    raw = row.get("split_value")
    if raw is None:
        raw = row.get("split") or row.get("split_type")
    value = str(raw or "").strip().upper()
    if dimension and dimension != _BATTER_HAND_DIMENSION:
        return None
    if value in _LHB_VALUES:
        return "L"
    if value in _RHB_VALUES:
        return "R"
    return None


def _player_key(value) -> str:
    """Normalise an MLB id for comparison across files.

    `sp_metric_splits.csv` stores `pitcher_id` as float64 (pandas promotes the column because
    some split rows carry no id), so it stringifies as "434378.0" while `sp_profiles.csv`
    gives "434378". Comparing the raw strings matched nothing on any slate — the third
    independent reason this lookup was returning a constant 1.0.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if number != number else str(int(number))  # NaN != NaN


# Batters faced at which a handedness split earns half weight against the pitcher's own
# season line. FIP is a K/BB/HR composite, and those components stabilise at ~113, ~193 and
# ~923 batters faced respectively (mlbmodel.props.challenger.FITTED), so a FIP-shaped split
# sits in the low hundreds. JUDGMENT, not a fit — but the direction is not optional: without
# it a one-start split saturates the factor at its clip.
SPLIT_SHRINK_BF = 250.0
_BF_PER_INNING = 4.3


def _split_sample_bf(row: dict) -> float:
    """Batters faced behind a handedness split row: starts x avg innings x batters/inning."""
    starts = _number(row.get("starts")) or 0.0
    innings = _number(row.get("avg_IP")) or 0.0
    return max(0.0, starts * innings * _BF_PER_INNING)


def _split_factor(profile: dict, row: dict) -> float:
    """Platoon factor from one split row, shrunk toward the pitcher's own season line.

    The split is a small sample by construction — half a pitcher's batters, sometimes a
    single start. Unshrunk it saturates: Justin Verlander's vs-LHH row on 2026-08-31 was one
    start and 2.33 innings (~10 batters) showing a 10.40 FIP against a 7.75 season FIP, which
    pinned the factor at its 1.06 ceiling. Four unrelated starters returned byte-identical
    factors because all four were clipped, which is the signature of noise, not platoon skill.
    """
    season_fip = _number(profile.get("FIP")) or settings.LEAGUE_FIP
    split_fip = _number(row.get("FIP"))
    split_k = _percent(row.get("K%")) or _percent(row.get("K_pct"))
    season_k = _percent(profile.get("K_pct"))
    weight = _split_sample_bf(row) / (_split_sample_bf(row) + SPLIT_SHRINK_BF)
    factor = 1.0
    if split_fip and season_fip:
        shrunk_fip = season_fip + (split_fip - season_fip) * weight
        factor *= _clip(shrunk_fip / season_fip, 0.92, 1.08)
    if split_k is not None and season_k is not None:
        shrunk_k = season_k + (split_k - season_k) * weight
        factor *= _clip(1 - (shrunk_k - season_k) * 0.004, 0.97, 1.03)
    return _clip(factor, 0.94, 1.06)


def sp_split_skill_adjustment(
    profile: dict | None,
    split_rows: list[dict],
    lhb_share: float | str | None,
) -> float:
    """Platoon skill factor: the pitcher's own vs-LHB/vs-RHB splits, weighted by the lineup.

    ``lhb_share`` is the fraction of the opposing lineup that bats left-handed (switch
    hitters count as left against a right-hander and vice versa). A pitcher's split is a
    property of the *batters he faces*, so keying it on his own throwing hand — which this
    did before — asks the wrong question: it looked up a lefty's record against left-handed
    batters regardless of whether the club posting against him started one lefty or six.
    A bare hand string is still accepted for older callers and resolves to the league share.
    """
    if not profile or not split_rows:
        return 1.0
    if isinstance(lhb_share, str) or lhb_share is None:
        share = LEAGUE_LHB_SHARE
    else:
        share = _clip(float(lhb_share), 0.0, 1.0)
    pitcher_id = _player_key(profile.get("pitcher_id"))
    name = str(profile.get("pitcher_name") or "").strip().lower()
    by_hand: dict[str, dict] = {}
    for candidate in split_rows:
        hand = _split_hand(candidate)
        if hand is None or hand in by_hand:
            continue
        candidate_id = _player_key(candidate.get("pitcher_id"))
        if candidate_id and pitcher_id:
            same_pitcher = candidate_id == pitcher_id
        else:
            # Some split rows carry no id at all; fall back to the name for those only.
            same_pitcher = (
                bool(name)
                and str(candidate.get("pitcher_name") or "").strip().lower() == name
            )
        if same_pitcher:
            by_hand[hand] = candidate
    if not by_hand:
        return 1.0
    versus_left = _split_factor(profile, by_hand["L"]) if "L" in by_hand else None
    versus_right = _split_factor(profile, by_hand["R"]) if "R" in by_hand else None
    if versus_left is None:
        blended = versus_right
    elif versus_right is None:
        blended = versus_left
    else:
        blended = share * versus_left + (1 - share) * versus_right
    return _regress(_clip(float(blended), 0.94, 1.06))


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
                _clip(1 - (value - LEAGUE_AVG) * MODEL_SENSITIVITIES["defense"], *settings.DEFENSE_FACTOR_CLIP)
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


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def signal_edge_adjustment(
    signals: list[dict],
    *,
    side: str,
    convergence: list[dict] | None = None,
    away: str | None = None,
    home: str | None = None,
) -> float:
    """Additive edge boost from fired MLBMA signals for a lineup side."""
    boost = 0.0
    for row in signals:
        if not row.get("fired"):
            continue
        if str(row.get("side") or "").lower() != side:
            continue
        magnitude = float(row.get("magnitude") or 0.0)
        direction = str(row.get("direction") or "").lower()
        sign = 1.0 if direction in {"boost", "over", "up", "positive", "bullish", "lineup", "hot"} else (
            -1.0 if direction in {"fade", "under", "down", "negative", "bearish", "pitching", "cold"} else 0.0
        )
        boost += sign * magnitude * settings.SIGNAL_EDGE_SCALE

    if convergence and away and home:
        row = convergence_side_row(convergence, away=away, home=home, side=side)
        if row and _is_truthy(row.get("is_convergence_play")):
            count = float(row.get("convergence_count") or 0.0)
            scale = min(count / CONVERGENCE_THRESHOLD, 1.5)
            direction = str(row.get("convergence_direction") or "").lower()
            sign = 1.0 if direction in {"lineup", "hot", "boost", "over", "up", "positive", "bullish"} else (
                -1.0 if direction in {"pitching", "cold", "fade", "under", "down", "negative", "bearish"} else 0.0
            )
            if sign:
                boost += sign * scale * MODEL_SENSITIVITIES["convergence_edge_scale"] * 100

    return _clip(
        boost,
        -settings.SIGNAL_EDGE_CAP - MODEL_SENSITIVITIES["convergence_edge_cap"],
        settings.SIGNAL_EDGE_CAP + MODEL_SENSITIVITIES["convergence_edge_cap"],
    )


def signal_confidence_modifier(
    signals: list[dict],
    away: str,
    home: str,
    confidence: str,
    *,
    convergence: list[dict] | None = None,
) -> str:
    """Bump model confidence when MLBMA signal convergence supports the projection."""
    if convergence:
        side_rows = convergence_for_game(convergence, away, home)
        if any(_is_truthy(row.get("is_convergence_play")) for row in side_rows):
            if confidence == "medium":
                return "high"
        elif confidence == "high" and not signals:
            return "medium"

    if not signals:
        return confidence
    fired = sum(1 for row in signals if row.get("fired"))
    if fired >= CONVERGENCE_THRESHOLD and confidence == "medium":
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
