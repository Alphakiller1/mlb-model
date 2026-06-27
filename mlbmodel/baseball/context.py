"""Bounded context priors shared by the game and pitcher models."""
from __future__ import annotations

import math


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def weather_run_factor(weather: dict | None) -> float:
    """Translate first-pitch conditions into a conservative run multiplier."""
    value = weather or {}
    if value.get("dome") or value.get("status") == "dome":
        return 1.0
    temperature = value.get("temp_f", value.get("temperature_f"))
    wind_out = value.get("wind_out_mph")
    humidity = value.get("humidity_pct")
    pressure = value.get("pressure_hpa")
    factor = 1.0
    if isinstance(temperature, (int, float)):
        factor += (temperature - 72.0) * 0.0012
    if isinstance(wind_out, (int, float)):
        factor += wind_out * 0.0025
    if isinstance(humidity, (int, float)):
        factor += (humidity - 55.0) * 0.00015
    if isinstance(pressure, (int, float)):
        factor -= (pressure - 1013.25) * 0.00025
    return clip(factor, 0.93, 1.08)


def travel_offense_factor(travel: dict | None) -> float:
    """Bound the effect of short rest, distance, timezone change, and density."""
    value = travel or {}
    if value.get("status") != "available":
        return 1.0
    rest = value.get("rest_hours")
    miles = value.get("travel_miles")
    shift = value.get("timezone_shift_hours")
    games = value.get("games_last_7_days")
    penalty = 0.0
    if isinstance(rest, (int, float)):
        if rest < 18:
            penalty += 0.025
        elif rest < 22:
            penalty += 0.012
    if isinstance(miles, (int, float)) and isinstance(rest, (int, float)) and rest < 30:
        penalty += min(0.015, miles / 100000.0)
    if isinstance(shift, (int, float)) and isinstance(rest, (int, float)) and rest < 36:
        penalty += min(0.012, abs(shift) * 0.004)
    if isinstance(games, (int, float)) and games >= 7:
        penalty += min(0.01, (games - 6) * 0.004)
    return clip(1.0 - penalty, 0.94, 1.0)


def umpire_run_factor(umpire: dict | None) -> float:
    profile = (umpire or {}).get("profile") or {}
    factor = profile.get("run_factor")
    return clip(float(factor), 0.96, 1.04) if isinstance(factor, (int, float)) else 1.0


def context_coverage(context: dict | None) -> tuple[int, list[str]]:
    value = context or {}
    lineups = value.get("lineups") or {}
    present = 0
    missing = []
    for side in ("away", "home"):
        if (lineups.get(side) or {}).get("status") in {"confirmed", "projected"}:
            present += 1
        else:
            missing.append(f"{side} lineup")
    weather = value.get("weather") or {}
    if weather.get("status") in {"forecast", "dome"}:
        present += 1
    else:
        missing.append("weather")
    if (value.get("umpire") or {}).get("status") == "announced":
        present += 1
    else:
        missing.append("plate umpire")
    travel = value.get("travel") or {}
    for side in ("away", "home"):
        if (travel.get(side) or {}).get("status") in {"available", "no_recent_game"}:
            present += 1
        else:
            missing.append(f"{side} travel")
    if "injuries" in value:
        present += 1
    else:
        missing.append("injuries")
    return round(present / 7 * 100), missing


def confidence_from_coverage(coverage: int, sample_starts: int) -> str:
    score = coverage + min(15, max(0, sample_starts) * 1.5)
    if score >= 100:
        return "high"
    if score >= 78:
        return "medium"
    return "low"


def normal_interval(mean: float, standard_deviation: float) -> tuple[float, float]:
    width = 1.2815515655446004 * max(0.0, standard_deviation)
    return max(0.0, mean - width), max(0.0, mean + width)


def direction_label(value: float, good_threshold: float = 0.006) -> str:
    if value >= good_threshold:
        return "pitcher edge"
    if value <= -good_threshold:
        return "lineup edge"
    return "neutral"


def finite(value: float | None, default: float) -> float:
    return value if isinstance(value, (int, float)) and math.isfinite(value) else default
