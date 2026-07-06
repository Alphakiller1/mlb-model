"""Matchup-aware pitcher prop distributions.

This advances the Sharp Money pitcher logic while keeping its useful channel
separation: strikeout/walk inputs do not get re-applied to earned runs, and
run-environment inputs do not manufacture strikeout edges.
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from mlbmodel.baseball.context import (
    confidence_from_coverage,
    context_coverage,
    direction_label,
    travel_offense_factor,
    umpire_run_factor,
    weather_run_factor,
)
from mlbmodel.baseball.metrics import (
    opponent_offense_strength,
    pitcher_allowed_skill_adjustment,
    sp_split_skill_adjustment,
)
from mlbmodel.baseball.repository import DataRepository

LG_BABIP = 0.295
LG_LOB = 0.72
LG_K = 0.225
LG_BB = 0.082
LG_H = 0.23
# Expected starter win contribution for PrizePicks fantasy score (Win = +6 pts). Win depends on
# team offense + bullpen, not just the pitcher, so it's modeled as a flat league-average starter
# win rate rather than sampled; the other components (outs/K/ER/QS) are exact per iteration.
PP_WIN_PROB = 0.40
LG_XWOBA = 0.320
SKIP_PITCH_TYPES = {"UNK", "PO", "EP", "FA"}
ORDER_WEIGHTS = np.array([1.10, 1.08, 1.07, 1.05, 1.02, 0.99, 0.96, 0.93, 0.90])


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace("%", ""))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _percent(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number * 100 if number <= 1.5 else number


def _innings(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    whole = int(number)
    partial = round((number - whole) * 10)
    if partial in (1, 2):
        return whole + partial / 3
    return number


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    if "," in text:
        last, _, first = text.partition(",")
        text = f"{first} {last}"
    return " ".join(text.lower().replace(".", "").split())


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _rows(frame: pd.DataFrame | None) -> list[dict]:
    return frame.to_dict("records") if frame is not None and not frame.empty else []


def _index(rows: list[dict], column: str) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for row in rows:
        key = _norm(row.get(column))
        if key:
            result.setdefault(key, []).append(row)
    return result


def _pitch_type(value: Any) -> str:
    return str(value or "UNK").strip().upper()[:4]


def _weighted(values: list[tuple[float, float]]) -> float | None:
    clean = [(value, weight) for value, weight in values if weight > 0]
    if not clean:
        return None
    total = sum(weight for _, weight in clean)
    return sum(value * weight for value, weight in clean) / total


@dataclass(frozen=True)
class Distribution:
    mean: float
    p10: float
    p50: float
    p90: float
    standard_deviation: float

    def as_dict(self) -> dict:
        return {
            "mean": round(self.mean, 2),
            "p10": round(self.p10, 1),
            "p50": round(self.p50, 1),
            "p90": round(self.p90, 1),
            "sd": round(self.standard_deviation, 2),
        }


def _distribution(samples: np.ndarray) -> Distribution:
    return Distribution(
        mean=float(np.mean(samples)),
        p10=float(np.quantile(samples, 0.10)),
        p50=float(np.quantile(samples, 0.50)),
        p90=float(np.quantile(samples, 0.90)),
        standard_deviation=float(np.std(samples)),
    )


class PitcherProjectionEngine:
    def __init__(self, repo: DataRepository):
        self.repo = repo
        self.profiles = _rows(repo.load("sp_profiles.csv"))
        self.profile_by_name = _index(self.profiles, "pitcher_name")
        self.l14_by_name = _index(_rows(repo.load("sp_l14.csv")), "Name")
        self.game_logs = _rows(repo.load("sp_game_log.csv"))
        self.logs_by_name = _index(self.game_logs, "pitcher_name")
        self.batter_profiles = _rows(repo.load("batter_profiles.csv"))
        self.batter_by_name = _index(self.batter_profiles, "player_name")
        self.pitcher_mix = self._preferred_mix(
            "pitch_mix_pitcher_l14.csv", "pitch_mix_pitcher.csv", "full_name"
        )
        self.batter_mix = self._preferred_mix(
            "pitch_mix_batter_l14.csv", "pitch_mix_batter.csv", "full_name"
        )
        self.team_mix = self._preferred_mix(
            "pitch_mix_team_batting_l14.csv",
            "pitch_mix_team_batting.csv",
            "team_abbr",
        )
        self.pitcher_mix_by_name = _index(self.pitcher_mix, "full_name")
        self.batter_mix_by_name = _index(self.batter_mix, "full_name")
        self.batter_mix_by_id: dict[int, list[dict]] = {}
        for row in self.batter_mix:
            player_id = int(_number(row.get("player_id")) or 0)
            if player_id:
                self.batter_mix_by_id.setdefault(player_id, []).append(row)
        self.team_mix_by_team: dict[str, list[dict]] = {}
        for row in self.team_mix:
            team = str(row.get("team_abbr") or "").upper()
            self.team_mix_by_team.setdefault(team, []).append(row)
        self.sp_metric_splits = _rows(repo.load("sp_metric_splits.csv"))
        self.pitch_baselines = self._pitch_baselines()

    def _preferred_mix(self, recent: str, season: str, key: str) -> list[dict]:
        recent_rows = _rows(self.repo.load(recent))
        season_rows = _rows(self.repo.load(season))
        if not recent_rows:
            return season_rows
        recent_keys = {
            (_norm(row.get(key)), _pitch_type(row.get("pitch_type")))
            for row in recent_rows
        }
        return recent_rows + [
            row
            for row in season_rows
            if (_norm(row.get(key)), _pitch_type(row.get("pitch_type"))) not in recent_keys
        ]

    def _pitch_baselines(self) -> dict[str, dict[str, float]]:
        grouped: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for row in self.team_mix:
            pitch = _pitch_type(row.get("pitch_type"))
            if pitch in SKIP_PITCH_TYPES:
                continue
            weight = max(1.0, _number(row.get("pitches")) or 1.0)
            metrics = grouped.setdefault(
                pitch, {"xwoba": [], "whiff_rate": [], "chase_rate": []}
            )
            for column in metrics:
                value = _number(row.get(column))
                if value is not None:
                    metrics[column].append((value, weight))
        return {
            pitch: {
                column: _weighted(values) or (
                    LG_XWOBA if column == "xwoba" else 25.0
                )
                for column, values in metrics.items()
            }
            for pitch, metrics in grouped.items()
        }

    def _profile(self, name: str, team: str) -> dict | None:
        candidates = self.profile_by_name.get(_norm(name), [])
        team_matches = [
            row for row in candidates
            if str(row.get("pitcher_team") or "").upper() == team
        ]
        return (team_matches or candidates or [None])[0]

    def _l14(self, name: str) -> dict | None:
        candidates = self.l14_by_name.get(_norm(name), [])
        return max(candidates, key=lambda row: _number(row.get("TBF")) or 0) if candidates else None

    def _logs(self, name: str) -> list[dict]:
        return sorted(
            self.logs_by_name.get(_norm(name), []),
            key=lambda row: str(row.get("date") or ""),
        )

    @staticmethod
    def _game_log_factors(logs: list[dict]) -> dict:
        if not logs:
            return {
                "babip": None, "lob": None, "k_trend": 0.0, "bb_trend": 0.0,
                "recent_ip": None, "ip_sd": 1.0, "bf": 0.0,
            }
        frame = pd.DataFrame(logs)
        numeric = {
            column: pd.to_numeric(frame.get(column), errors="coerce")
            for column in ("H", "BB", "HR", "K", "R", "batters_faced", "pitches")
        }
        # (hits/batters computed below is the empirical H/BF rate used to project hits allowed)
        hits, walks, homers, strikeouts, runs = (
            float(numeric[column].sum()) for column in ("H", "BB", "HR", "K", "R")
        )
        batters = float(numeric["batters_faced"].sum())
        balls_in_play = batters - strikeouts - homers - walks
        babip = (hits - homers) / balls_in_play if balls_in_play > 0 else None
        lob_denominator = hits + walks - 1.4 * homers
        lob = (hits + walks - runs) / lob_denominator if lob_denominator > 0 else None
        recent = frame.tail(3)

        def rate(data: pd.DataFrame, column: str) -> float | None:
            events = pd.to_numeric(data.get(column), errors="coerce").sum()
            faced = pd.to_numeric(data.get("batters_faced"), errors="coerce").sum()
            return float(events / faced * 100) if faced > 0 else None

        season_k, recent_k = rate(frame, "K"), rate(recent, "K")
        season_bb, recent_bb = rate(frame, "BB"), rate(recent, "BB")
        innings = np.array(
            [value for value in (_innings(row.get("IP")) for row in logs) if value is not None]
        )
        recent_innings = innings[-3:] if len(innings) else innings
        return {
            "babip": babip,
            "lob": lob,
            "h_rate": (hits / batters) if batters > 0 else None,
            "k_trend": (recent_k - season_k) if None not in (recent_k, season_k) else 0.0,
            "bb_trend": (recent_bb - season_bb) if None not in (recent_bb, season_bb) else 0.0,
            "recent_ip": float(np.mean(recent_innings)) if len(recent_innings) else None,
            "ip_sd": float(np.std(innings)) if len(innings) >= 3 else 1.0,
            "bf": batters,
        }

    def _lineup_strength(
        self,
        lineup: dict,
        team: str,
        pitcher_hand: str,
    ) -> dict:
        split = "vs_LHP" if pitcher_hand == "L" else "vs_RHP"
        team_rows = [
            row for row in self.batter_profiles
            if str(row.get("team") or "").upper() == team
            and str(row.get("split_type") or "") == split
        ]
        baseline = _weighted(
            [
                (_number(row.get("projOSI")) or _number(row.get("OSI")) or 50.0,
                 max(1.0, _number(row.get("PA")) or 1.0))
                for row in team_rows
            ]
        ) or 50.0
        values = []
        matched = []
        for index, player in enumerate((lineup or {}).get("players") or []):
            candidates = self.batter_by_name.get(_norm(player.get("player")), [])
            row = next(
                (item for item in candidates if str(item.get("split_type")) == split),
                None,
            ) or next(
                (item for item in candidates if str(item.get("split_type")) == "overall"),
                None,
            )
            if row is None:
                continue
            score = _number(row.get("projOSI")) or _number(row.get("OSI"))
            abq = _number(row.get("ABQ")) or _number(row.get("abq"))
            rcv = _number(row.get("RCV")) or _number(row.get("rcv"))
            if score is not None and abq is not None and rcv is not None:
                score = 0.55 * score + 0.25 * abq + 0.20 * rcv
            if score is None:
                continue
            weight = float(ORDER_WEIGHTS[min(index, len(ORDER_WEIGHTS) - 1)])
            reliability = min(1.0, max(0.25, (_number(row.get("PA")) or 0) / 80))
            values.append((score, weight * reliability))
            matched.append(player.get("player"))
        lineup_score = _weighted(values)
        factor = (
            _clip(1 + (lineup_score - baseline) * 0.004, 0.90, 1.10)
            if lineup_score is not None and len(matched) >= 6
            else 1.0
        )
        return {
            "status": (lineup or {}).get("status", "unavailable"),
            "score": round(lineup_score, 1) if lineup_score is not None else None,
            "team_baseline": round(baseline, 1),
            "matched": len(matched),
            "factor": round(factor, 4),
        }

    def _lineup_pitch_rows(self, lineup: dict, team: str) -> tuple[list[dict], int]:
        players = (lineup or {}).get("players") or []
        by_pitch: dict[str, dict[str, list[tuple[float, float]]]] = {}
        matched = 0
        for index, player in enumerate(players):
            player_id = int(_number(player.get("player_id")) or 0)
            rows = self.batter_mix_by_id.get(player_id) if player_id else None
            rows = rows or self.batter_mix_by_name.get(_norm(player.get("player")), [])
            if not rows:
                continue
            matched += 1
            order_weight = float(ORDER_WEIGHTS[min(index, len(ORDER_WEIGHTS) - 1)])
            for row in rows:
                pitch = _pitch_type(row.get("pitch_type"))
                metrics = by_pitch.setdefault(
                    pitch, {"xwoba": [], "whiff_rate": [], "chase_rate": []}
                )
                sample = min(1.0, max(0.2, (_number(row.get("pitches")) or 0) / 35))
                for column in metrics:
                    value = _number(row.get(column))
                    if value is not None:
                        metrics[column].append((value, order_weight * sample))
        if matched < 6:
            return self.team_mix_by_team.get(team, []), matched
        output = []
        for pitch, metrics in by_pitch.items():
            output.append(
                {
                    "pitch_type": pitch,
                    **{column: _weighted(values) for column, values in metrics.items()},
                }
            )
        return output, matched

    def _pitch_matchup(
        self,
        pitcher_name: str,
        opponent: str,
        lineup: dict,
    ) -> dict:
        pitcher_rows = self.pitcher_mix_by_name.get(_norm(pitcher_name), [])
        lineup_rows, matched = self._lineup_pitch_rows(lineup, opponent)
        lineup_by_pitch = {
            _pitch_type(row.get("pitch_type")): row for row in lineup_rows
        }
        detail = []
        total_score = 0.0
        coverage = 0.0
        for pitcher in pitcher_rows:
            pitch = _pitch_type(pitcher.get("pitch_type"))
            usage = _number(pitcher.get("pitch_pct")) or 0.0
            opponent_row = lineup_by_pitch.get(pitch)
            baseline = self.pitch_baselines.get(pitch)
            if (
                pitch in SKIP_PITCH_TYPES
                or usage < 3
                or not opponent_row
                or not baseline
            ):
                continue
            weight = usage / 100
            coverage += weight
            pitcher_whiff = _number(pitcher.get("whiff_rate")) or baseline["whiff_rate"]
            lineup_whiff = _number(opponent_row.get("whiff_rate")) or baseline["whiff_rate"]
            pitcher_xwoba = _number(pitcher.get("xwoba")) or baseline["xwoba"]
            lineup_xwoba = _number(opponent_row.get("xwoba")) or baseline["xwoba"]
            pitcher_chase = _number(pitcher.get("chase_rate")) or baseline["chase_rate"]
            lineup_chase = _number(opponent_row.get("chase_rate")) or baseline["chase_rate"]
            whiff_edge = (
                (pitcher_whiff - baseline["whiff_rate"])
                + (lineup_whiff - baseline["whiff_rate"])
            ) / 100
            contact_edge = (
                (baseline["xwoba"] - pitcher_xwoba)
                + (baseline["xwoba"] - lineup_xwoba)
            )
            chase_edge = (
                (pitcher_chase - baseline["chase_rate"])
                + (lineup_chase - baseline["chase_rate"])
            ) / 100
            score = weight * (0.42 * whiff_edge + 0.43 * contact_edge + 0.15 * chase_edge)
            total_score += score
            detail.append(
                {
                    "pitch": str(pitcher.get("pitch_name") or pitch),
                    "pitch_type": pitch,
                    "usage_pct": round(usage, 1),
                    "pitcher_whiff_pct": round(pitcher_whiff, 1),
                    "lineup_whiff_pct": round(lineup_whiff, 1),
                    "pitcher_xwoba": round(pitcher_xwoba, 3),
                    "lineup_xwoba": round(lineup_xwoba, 3),
                    "k_delta": round(score * 16, 2),
                    "er_factor_delta": round(-score * 1.8, 3),
                    "edge": direction_label(score),
                    "score": round(score, 4),
                }
            )
        detail.sort(key=lambda row: abs(row["score"]), reverse=True)
        if coverage < 0.35:
            total_score = 0.0
        return {
            "score": round(total_score, 4),
            "coverage_pct": round(min(1.0, coverage) * 100),
            "lineup_batters_matched": matched,
            "response_source": (
                "posted lineup, batting-order weighted"
                if matched >= 6
                else "opponent team pitch-type results"
            ),
            "k_rate_delta": round(_clip(total_score * 16, -2.5, 2.5), 2),
            "er_factor": round(_clip(1 - total_score * 1.8, 0.90, 1.10), 4),
            "verdict": direction_label(total_score),
            "pitches": detail,
        }

    @staticmethod
    def _injury_factor(injuries: list[dict], batter_by_name: dict) -> float:
        penalty = 0.0
        for injury in injuries:
            candidates = batter_by_name.get(_norm(injury.get("player")), [])
            row = next(
                (item for item in candidates if str(item.get("split_type")) == "overall"),
                None,
            )
            if row is None:
                continue
            osi = _number(row.get("projOSI")) or _number(row.get("OSI")) or 50.0
            pa = _number(row.get("PA")) or 0.0
            penalty += max(0.0, osi - 50.0) * min(1.0, pa / 250) * 0.0015
        return _clip(1 - penalty, 0.93, 1.0)

    @staticmethod
    def _performance_state(
        profile: dict,
        log_factors: dict,
        skill_era: float,
    ) -> tuple[str, float]:
        if int(_number(profile.get("starts")) or 0) < 2:
            return "LIMITED SAMPLE", 0.0
        era = _number(profile.get("ERA")) or skill_era
        fip = _number(profile.get("FIP")) or skill_era
        xfip = _number(profile.get("xFIP")) or fip
        luck = 0.35 * (fip - era) + 0.20 * (xfip - era) + 0.10 * (xfip - fip)
        babip = log_factors.get("babip")
        lob = log_factors.get("lob")
        if isinstance(babip, (int, float)):
            luck += 0.18 * (LG_BABIP - babip) * 12
        if isinstance(lob, (int, float)):
            luck += 0.12 * (lob - LG_LOB) * 6
        if luck >= 0.60:
            return "REGRESSION", round(luck, 2)
        if luck <= -0.60:
            return "PROGRESSION", round(luck, 2)
        return "STABLE", round(luck, 2)

    def project(
        self,
        game,
        *,
        team: str,
        opponent: str,
        pitcher_name: str,
        pitcher_hand: str,
        side: str,
    ) -> dict:
        profile = self._profile(pitcher_name, team)
        fallback_profile = (
            (((game.live_context.get("probable_pitchers") or {}).get(side) or {})
             .get("profile"))
            or None
        )
        profile = profile or fallback_profile
        lineup = (((game.live_context.get("lineups") or {}).get(
            "home" if side == "away" else "away"
        )) or {})
        if profile is None:
            return {
                "pitcher": pitcher_name,
                "team": team,
                "opponent": opponent,
                "state": "DATA GAP",
                "market_state": "NO MARKET",
                "confidence": "low",
                "reason": "No MLBMA starter profile matched the official probable pitcher.",
            }
        logs = self._logs(pitcher_name)
        log_factors = self._game_log_factors(logs)
        l14 = self._l14(pitcher_name)
        starts = int(_number(profile.get("starts")) or 0)
        l14_starts = int(_number(profile.get("l14_starts")) or 0)
        recent_weight = (
            min(0.50, (_number((l14 or {}).get("TBF")) or 0) / 140)
            if l14 and l14_starts >= 2
            else 0.0
        )

        season_fip = _number(profile.get("FIP")) or 4.20
        season_xfip = _number(profile.get("xFIP")) or season_fip
        recent_fip = _number((l14 or {}).get("FIP")) or season_fip
        recent_xfip = _number((l14 or {}).get("xFIP")) or recent_fip
        season_skill = season_fip * 0.52 + season_xfip * 0.48
        recent_skill = recent_fip * 0.45 + recent_xfip * 0.55
        skill_era = (
            season_skill * (1 - recent_weight) + recent_skill * recent_weight
        )
        shrink = starts / (starts + 6) if starts > 0 else 0.0
        skill_era = 4.20 + (skill_era - 4.20) * shrink

        season_k = (_percent(profile.get("K_pct")) or LG_K * 100)
        season_bb = (_percent(profile.get("BB_pct")) or LG_BB * 100)
        recent_k = _percent((l14 or {}).get("K%")) or season_k
        recent_bb = _percent((l14 or {}).get("BB%")) or season_bb
        k_rate = season_k * (1 - recent_weight) + recent_k * recent_weight
        bb_rate = season_bb * (1 - recent_weight) + recent_bb * recent_weight
        k_rate += _clip(log_factors["k_trend"] * 0.25, -1.5, 1.5)
        bb_rate += _clip(log_factors["bb_trend"] * 0.20, -1.0, 1.0)

        lineup_strength = self._lineup_strength(
            lineup, opponent, pitcher_hand
        )
        pitch_matchup = self._pitch_matchup(pitcher_name, opponent, lineup)
        k_rate += pitch_matchup["k_rate_delta"]
        expected_ip = _number(profile.get("avg_IP")) or 5.3
        if log_factors.get("recent_ip") is not None:
            expected_ip = expected_ip * 0.65 + log_factors["recent_ip"] * 0.35
        # Hard sanity bound: no MLB starter projects beyond ~7 IP, and a bad/garbage
        # avg_IP from a thin profile (e.g. a swingman with one long relief outing) would
        # otherwise sail past the 8.2-out sample clip and manufacture a near-certain
        # high-Outs projection — a fake market edge. Clip the mean to a realistic range.
        expected_ip = _clip(expected_ip, 2.5, 7.0)

        opponent_side = "home" if side == "away" else "away"
        context = game.live_context
        travel = ((context.get("travel") or {}).get(opponent_side) or {})
        injuries = ((context.get("injuries") or {}).get(opponent_side) or [])
        injury_factor = (
            1.0
            if lineup.get("status") == "confirmed"
            else self._injury_factor(injuries, self.batter_by_name)
        )
        run_factor = (
            lineup_strength["factor"]
            * pitch_matchup["er_factor"]
            * weather_run_factor(context.get("weather"))
            * umpire_run_factor(context.get("umpire"))
            * travel_offense_factor(travel)
            * injury_factor
        )
        opp_ctx = game.home_context if side == "away" else game.away_context
        opp_osi = game.home_osi if side == "away" else game.away_osi
        opp_strength = opponent_offense_strength(opp_ctx, opp_osi)
        run_factor *= pitcher_allowed_skill_adjustment(profile, opp_strength)
        run_factor *= sp_split_skill_adjustment(
            profile, self.sp_metric_splits, pitcher_hand
        )
        era = _number(profile.get("ERA")) or skill_era
        blended_era = skill_era * 0.70 + era * 0.30
        er_mean = max(0.2, blended_era / 9 * expected_ip * run_factor)
        f5_mean = max(0.1, blended_era / 9 * min(5.0, expected_ip) * run_factor)

        coverage, missing = context_coverage(context)
        confidence = confidence_from_coverage(coverage, starts)
        seed = int(game.mlb_game_pk or game.game_pk) + int(
            _number(profile.get("pitcher_id")) or 0
        )
        rng = np.random.default_rng(seed)
        iterations = 30000
        ip_samples = rng.normal(
            expected_ip,
            max(0.65, min(1.35, log_factors.get("ip_sd") or 1.0)),
            iterations,
        )
        ip_samples = np.clip(ip_samples, 1.0, 8.2)
        bf_samples = np.maximum(
            3,
            np.rint(ip_samples * rng.normal(4.25, 0.16, iterations)).astype(int),
        )
        effective_bf = max(60.0, float(log_factors.get("bf") or starts * 22))
        k_probability = _clip(k_rate / 100, 0.05, 0.48)
        bb_probability = _clip(bb_rate / 100, 0.02, 0.22)
        k_draw = rng.beta(
            k_probability * effective_bf + LG_K * 25,
            (1 - k_probability) * effective_bf + (1 - LG_K) * 25,
            iterations,
        )
        bb_draw = rng.beta(
            bb_probability * effective_bf + LG_BB * 25,
            (1 - bb_probability) * effective_bf + (1 - LG_BB) * 25,
            iterations,
        )
        strikeouts = rng.binomial(bf_samples, k_draw)
        walks = rng.binomial(bf_samples, bb_draw)
        er_lambda = rng.gamma(shape=4.5, scale=er_mean / 4.5, size=iterations)
        earned_runs = rng.poisson(er_lambda)
        f5_lambda = rng.gamma(shape=5.0, scale=f5_mean / 5.0, size=iterations)
        f5_er = rng.poisson(f5_lambda)
        outs = np.rint(ip_samples * 3)
        # Hits allowed: a per-batter hit rate (the pitcher's empirical H/BF, else league) drawn
        # like K/BB, then sampled over batters faced.
        h_rate = log_factors.get("h_rate")
        h_probability = _clip(h_rate if h_rate is not None else LG_H, 0.10, 0.36)
        h_draw = rng.beta(
            h_probability * effective_bf + LG_H * 25,
            (1 - h_probability) * effective_bf + (1 - LG_H) * 25,
            iterations,
        )
        hits = rng.binomial(bf_samples, h_draw)
        # DraftKings pitcher fantasy points: IP +2.25/inning (0.75/out), K +2, ER -2, H -0.6,
        # BB -0.6. Excludes W / quality-start / complete-game bonuses (need game context).
        fantasy = outs * 0.75 + strikeouts * 2.0 - earned_runs * 2.0 - hits * 0.6 - walks * 0.6
        # PrizePicks pitcher fantasy score: Out +1, K +3, ER -3, Quality Start +4 (>=6 IP & <=3
        # ER, computed exactly from the joint sim), Win +6 (modeled as PP_WIN_PROB, see above).
        qs_bonus = np.where((outs >= 18) & (earned_runs <= 3), 4.0, 0.0)
        pp_fantasy = (
            outs + strikeouts * 3.0 - earned_runs * 3.0 + qs_bonus + 6.0 * PP_WIN_PROB
        )
        state, luck = self._performance_state(profile, log_factors, skill_era)

        # Projection trust gates the edge board. The real signal is sample size, not which
        # table the profile came from: an established arm on the MLB-Stats-API fallback
        # (e.g. Yamamoto, 14 starts) is reliable, while a 0-4 start swingman projects
        # overconfidently and manufactures phantom edges. Those thin rows are shown but
        # never surfaced as actionable edges.
        projection_trust = "trusted" if starts >= 5 else "thin"

        return {
            "pitcher": pitcher_name,
            "pitcher_id": int(_number(profile.get("pitcher_id")) or 0) or None,
            "team": team,
            "opponent": opponent,
            "hand": pitcher_hand,
            "state": state,
            "luck_runs": luck,
            "market_state": "NO MARKET",
            "confidence": confidence,
            "projection_trust": projection_trust,
            "data_coverage_pct": coverage,
            "missing_context": missing,
            "lineup_status": lineup.get("status", "unavailable"),
            "lineup": lineup_strength,
            "pitch_matchup": pitch_matchup,
            "skill_era": round(skill_era, 2),
            "expected_ip": round(expected_ip, 2),
            "k_rate": round(k_rate, 2),
            "bb_rate": round(bb_rate, 2),
            "run_factor": round(run_factor, 4),
            "projections": {
                "K": _distribution(strikeouts).as_dict(),
                "BB": _distribution(walks).as_dict(),
                "ER": _distribution(earned_runs).as_dict(),
                "Outs": _distribution(outs).as_dict(),
                "H": _distribution(hits).as_dict(),
                "Fantasy": _distribution(fantasy).as_dict(),
                "PP_Fantasy": _distribution(pp_fantasy).as_dict(),
                "F5_ER": _distribution(f5_er).as_dict(),
            },
            "sample": {
                "season_starts": starts,
                "recent_starts": l14_starts,
                "recent_weight": round(recent_weight, 3),
                "simulation_iterations": iterations,
                "source": (
                    "MLB Stats API season fallback"
                    if profile is fallback_profile
                    else "MLBMA starter model"
                ),
            },
        }


def build_pitcher_board(repo: DataRepository) -> list[dict]:
    engine = PitcherProjectionEngine(repo)
    slate = repo.slate()
    if slate is None:
        return []
    board = []
    for _, row in slate.iterrows():
        away = str(row.get("Away") or "").upper().strip()
        home = str(row.get("Home") or "").upper().strip()
        try:
            game = repo.load_game(away, home)
        except (FileNotFoundError, ValueError):
            continue
        board.append(
            engine.project(
                game,
                team=away,
                opponent=home,
                pitcher_name=game.away_sp,
                pitcher_hand=game.away_hand,
                side="away",
            )
        )
        board.append(
            engine.project(
                game,
                team=home,
                opponent=away,
                pitcher_name=game.home_sp,
                pitcher_hand=game.home_hand,
                side="home",
            )
        )
    state_order = {
        "REGRESSION": 0,
        "PROGRESSION": 1,
        "STABLE": 2,
        "LIMITED SAMPLE": 3,
        "DATA GAP": 4,
    }
    return sorted(
        board,
        key=lambda row: (
            state_order.get(row.get("state"), 9),
            -abs(float(row.get("luck_runs") or 0)),
            row.get("pitcher") or "",
        ),
    )
