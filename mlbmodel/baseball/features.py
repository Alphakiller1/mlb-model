"""Feature builders for the unified expected-runs engine."""
from __future__ import annotations

import datetime as dt
import math
import unicodedata
from typing import Any

from mlbmodel import settings


def number(value: Any) -> float | None:
    try:
        result = float(str(value).replace("%", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def percent(value: Any) -> float | None:
    result = number(value)
    if result is None:
        return None
    return result * 100 if result <= 1.5 else result


def innings(value: Any) -> float | None:
    result = number(value)
    if result is None:
        return None
    whole = int(result)
    partial = round((result - whole) * 10)
    return whole + partial / 3 if partial in (1, 2) else result


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    if "," in text:
        last, _, first = text.partition(",")
        text = f"{first} {last}"
    return " ".join(text.lower().replace(".", "").split())


def starter_features(
    profile: dict | None,
    recent: dict | None,
    logs: list[dict],
) -> dict:
    if not profile:
        return {
            "skill_fip": settings.LEAGUE_FIP,
            "expected_ip": 5.2,
            "starts": 0,
            "recent_weight": 0.0,
            "source": "league replacement prior",
        }
    starts = int(number(profile.get("starts")) or 0)
    season_fip = number(profile.get("FIP")) or settings.LEAGUE_FIP
    season_xfip = number(profile.get("xFIP")) or season_fip
    season_era = number(profile.get("ERA")) or season_fip
    season_skill = 0.45 * season_fip + 0.40 * season_xfip + 0.15 * season_era
    recent_starts = int(number(profile.get("l14_starts")) or 0)
    recent_tbf = number((recent or {}).get("TBF")) or 0
    recent_weight = (
        min(0.45, recent_tbf / (recent_tbf + 90))
        if recent and recent_starts >= 2
        else 0.0
    )
    recent_fip = number((recent or {}).get("FIP")) or season_fip
    recent_xfip = number((recent or {}).get("xFIP")) or recent_fip
    recent_skill = 0.45 * recent_fip + 0.55 * recent_xfip
    blended = season_skill * (1 - recent_weight) + recent_skill * recent_weight
    reliability = starts / (starts + 6) if starts else 0.0
    skill = settings.LEAGUE_FIP + (blended - settings.LEAGUE_FIP) * reliability
    expected_ip = number(profile.get("avg_IP")) or 5.2
    recent_ip = [
        value for value in (innings(row.get("IP")) for row in logs[-3:])
        if value is not None
    ]
    if recent_ip:
        expected_ip = expected_ip * 0.65 + sum(recent_ip) / len(recent_ip) * 0.35
    return {
        "skill_fip": round(max(2.0, min(7.0, skill)), 3),
        "expected_ip": round(max(3.0, min(7.3, expected_ip)), 3),
        "starts": starts,
        "recent_starts": recent_starts,
        "recent_weight": round(recent_weight, 3),
        "source": "MLBMA SP profile + L14 + game log",
    }


def bullpen_features(
    row: dict | None,
    reliever_logs: list[dict],
    *,
    venue: str,
    game_date: str,
) -> dict:
    if not row:
        return {
            "skill_fip": settings.LEAGUE_BULLPEN_ERA,
            "workload_factor": 1.0,
            "pitches_1d": None,
            "pitches_2d": None,
            "source": "league bullpen prior",
        }
    overall = number(row.get("overall_FIP")) or settings.LEAGUE_BULLPEN_ERA
    high = number(row.get("high_leverage_FIP")) or overall
    location = number(row.get(f"{venue}_FIP")) or overall
    apps = number(row.get("overall_apps")) or number(row.get("appearances")) or 0
    composite = 0.55 * overall + 0.25 * high + 0.20 * location
    reliability = apps / (apps + 50) if apps else 0.0
    skill = (
        settings.LEAGUE_BULLPEN_ERA
        + (composite - settings.LEAGUE_BULLPEN_ERA) * reliability
    )
    slate = dt.date.fromisoformat(game_date)
    pitches_1d = 0.0
    pitches_2d = 0.0
    for log in reliever_logs:
        try:
            age = (slate - dt.date.fromisoformat(str(log.get("date"))[:10])).days
        except ValueError:
            continue
        pitches = number(log.get("pitches")) or 0.0
        if age == 1:
            pitches_1d += pitches
        if age in (1, 2):
            pitches_2d += pitches
    workload = (
        1
        + max(0.0, pitches_1d - 45) * 0.0004
        + max(0.0, pitches_2d - 90) * 0.0002
    )
    workload = max(1.0, min(1.04, workload))
    inherited = number(row.get("overall_inherited_runners_scored_pct"))
    if inherited is not None:
        skill *= max(0.97, min(1.03, 1 + (inherited - 28) * 0.001))
    return {
        "skill_fip": round(max(2.3, min(6.5, skill)), 3),
        "workload_factor": round(workload, 4),
        "pitches_1d": round(pitches_1d),
        "pitches_2d": round(pitches_2d),
        "source": "MLBMA bullpen unit + reliever workload",
    }


def lineup_features(
    lineup: dict | None,
    batter_profiles: list[dict],
    *,
    team: str,
    opposing_hand: str,
) -> dict:
    lineup = lineup or {}
    split = "vs_LHP" if opposing_hand == "L" else "vs_RHP"
    team_rows = [
        row for row in batter_profiles
        if str(row.get("team") or "").upper() == team
        and str(row.get("split_type") or "") == split
    ]

    def weighted(rows: list[tuple[float, float]]) -> float | None:
        if not rows:
            return None
        denominator = sum(weight for _, weight in rows)
        return sum(value * weight for value, weight in rows) / denominator

    baseline = weighted(
        [
            (
                number(row.get("projOSI")) or number(row.get("OSI")) or 50.0,
                max(1.0, number(row.get("PA")) or 1.0),
            )
            for row in team_rows
        ]
    ) or 50.0
    by_name: dict[str, list[dict]] = {}
    for row in batter_profiles:
        by_name.setdefault(normalize_name(row.get("player_name")), []).append(row)
    values = []
    for index, player in enumerate(lineup.get("players") or []):
        candidates = by_name.get(normalize_name(player.get("player")), [])
        row = next(
            (candidate for candidate in candidates if candidate.get("split_type") == split),
            None,
        ) or next(
            (
                candidate
                for candidate in candidates
                if candidate.get("split_type") == "overall"
            ),
            None,
        )
        if row is None:
            continue
        score = number(row.get("projOSI")) or number(row.get("OSI"))
        if score is None:
            continue
        order_weight = max(0.88, 1.11 - index * 0.025)
        reliability = min(1.0, max(0.25, (number(row.get("PA")) or 0) / 80))
        values.append((score, order_weight * reliability))
    projected = weighted(values)
    factor = (
        max(0.90, min(1.10, 1 + (projected - baseline) * 0.004))
        if projected is not None and len(values) >= 6
        else 1.0
    )
    return {
        "status": lineup.get("status", "unavailable"),
        "projected_osi": round(projected, 1) if projected is not None else None,
        "team_baseline_osi": round(baseline, 1),
        "matched_batters": len(values),
        "factor": round(factor, 4),
        "source": lineup.get("source"),
    }


def injury_features(
    injuries: list[dict],
    batter_profiles: list[dict],
    *,
    lineup_status: str,
) -> dict:
    if lineup_status == "confirmed":
        return {
            "factor": 1.0,
            "impact_players": [],
            "source": "absorbed by confirmed lineup",
        }
    by_name: dict[str, list[dict]] = {}
    for row in batter_profiles:
        by_name.setdefault(normalize_name(row.get("player_name")), []).append(row)
    impacts = []
    penalty = 0.0
    for injury in injuries:
        candidates = by_name.get(normalize_name(injury.get("player")), [])
        row = next(
            (
                candidate
                for candidate in candidates
                if candidate.get("split_type") == "overall"
            ),
            None,
        )
        if row is None:
            continue
        osi = number(row.get("projOSI")) or number(row.get("OSI")) or 50.0
        pa = number(row.get("PA")) or 0.0
        value = max(0.0, osi - 50) * min(1.0, pa / 250) * 0.0015
        if value <= 0:
            continue
        penalty += value
        impacts.append(
            {
                "player": injury.get("player"),
                "injury": injury.get("injury"),
                "run_factor_delta": round(-value, 4),
            }
        )
    impacts.sort(key=lambda row: row["run_factor_delta"])
    return {
        "factor": round(max(0.93, 1 - penalty), 4),
        "impact_players": impacts,
        "source": "official MLB 40-man IL + MLBMA batter value",
    }
