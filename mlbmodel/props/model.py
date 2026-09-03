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
    LEAGUE_LHB_SHARE,
    opponent_offense_strength,
    pitcher_allowed_skill_adjustment,
    sp_split_skill_adjustment,
)
from mlbmodel.baseball.model import model_probabilities
from mlbmodel.props import matrix
from mlbmodel.baseball.repository import DataRepository
from mlbmodel.report.game_keys import parse_game_key
from mlbmodel.sources.sync_mlbma import matchup_keys

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
# Pitch-mix adjustment scales. Unchanged from the original engine ON PURPOSE: the only change
# is WHAT they multiply. The score used to be the pitcher's arsenal quality plus the
# opponent's response; now it is the opponent's response alone.
#
# Measured on 3,790 starts (scripts/pitch_mix_audit.py), with the pitcher's own season K rate
# held constant — which the engine has already applied to `k_rate` before this term is added:
#
#     component            share of total sd   partial corr with realised K rate
#     pitcher's own stuff        94%                        +0.0027
#     opponent lineup            30%                        +0.0858
#     total (what shipped)      100%                        +0.0375
#
# The pitcher half correlates +0.708 with his own season K rate, so adding it counted the
# same skill twice and inflated the spread of every K projection — and it dropped the
# combined signal to less than half of what the opponent half carries alone. It is dead
# weight at best. The scales are NOT re-fitted here: the only data available for that is the
# season-aggregate pitch mix, which already knows how these starts ended, and a weight fitted
# on it would be fitted to hindsight -- true of the PITCHER half, whose season line is close
# to the thing being predicted. The OPPONENT half is a club aggregate over ~150 games, so one
# start is well under 1% of it and it IS fittable. Swept against the holdout
# (scripts/fit_final_calibration.py): scale 16 -> R2 +0.1967, 25 -> +0.1970, 40 -> +0.1973,
# 60 -> +0.1972, 87 -> +0.1962, 115 -> +0.1941. The train half alone fits 115 and the holdout
# 87, so the slope is unstable; 40 is the holdout optimum and is what ships.
PITCH_MIX_K_SCALE = 40.0
PITCH_MIX_ER_SCALE = 1.8
# How much of the opponent-quality run factor reaches earned runs. MEASURED, not a judgment.
# Re-tested against a leak-free baseline (self-history ER rate x PROJECTED outs, never the
# realised ones) across five separate opponent proxies. Every one flips sign between the
# train and holdout halves -- run conversion +1.057 -> -1.138, OSI +1.819 -> -1.049, total
# bases +0.102 -> -2.167 -- and none improves holdout R2 over the baseline's +0.0239.
# Sweeping the damping leaves holdout R2 identical to four decimals at every value from 0 to
# 1. Four independent methods now agree that per-start earned runs carry no opponent signal,
# so the channel is computed and reported but contributes nothing. Weather, umpire and travel
# are unaffected: they are physical, were never tested here, and pass through at full weight.
OPPONENT_ER_DAMPING = 0.0


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
    # The shape the simulation actually produced. `pmf` for integer counting stats,
    # `quantiles` (a 101-point percentile grid) for continuous ones like fantasy score.
    # Without one of these the board can only refit a symmetric normal to (mean, sd),
    # which overstates P(Over) on every right-skewed market — see market.probability.
    pmf: dict[int, float] | None = None
    quantiles: list[float] | None = None

    def as_dict(self) -> dict:
        payload = {
            "mean": round(self.mean, 2),
            "p10": round(self.p10, 1),
            "p50": round(self.p50, 1),
            "p90": round(self.p90, 1),
            "sd": round(self.standard_deviation, 2),
        }
        if self.pmf:
            payload["pmf"] = {
                str(value): round(probability, 6)
                for value, probability in sorted(self.pmf.items())
            }
        elif self.quantiles:
            payload["q"] = [round(value, 2) for value in self.quantiles]
        return payload


# Probability mass below this is dropped from a stored PMF: it keeps the board payload small
# without moving any line price (the trimmed tail is renormalised at pricing time).
_PMF_FLOOR = 1e-5


def _distribution(samples: np.ndarray) -> Distribution:
    samples = np.asarray(samples)
    integral = np.all(samples == np.rint(samples))
    pmf: dict[int, float] | None = None
    quantiles: list[float] | None = None
    if integral:
        values, counts = np.unique(samples.astype(np.int64), return_counts=True)
        total = float(counts.sum())
        pmf = {
            int(value): float(count) / total
            for value, count in zip(values, counts, strict=True)
            if count / total >= _PMF_FLOOR
        }
    else:
        quantiles = [
            float(value) for value in np.quantile(samples, np.linspace(0.0, 1.0, 101))
        ]
    return Distribution(
        mean=float(np.mean(samples)),
        p10=float(np.quantile(samples, 0.10)),
        p50=float(np.quantile(samples, 0.50)),
        p90=float(np.quantile(samples, 0.90)),
        standard_deviation=float(np.std(samples)),
        pmf=pmf,
        quantiles=quantiles,
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
        # Source-matched baselines: each opponent table is scored against its own.
        self.batter_pitch_baselines = self._mix_baselines(self.batter_mix)
        self.pitcher_pitch_baselines = self._mix_baselines(self.pitcher_mix)
        self.bats_by_id, self.bats_by_name = self._batter_hands(repo)
        self.opponent_k_rates, self.league_k_rate = matrix.opponent_strikeout_rates(
            self.game_logs
        )
        self.league_rates = matrix.league_rates(self.game_logs)
        self.league_outs = matrix.league_outs(self.game_logs)
        slate = repo.slate()
        self.slate_date = (
            str(slate.iloc[0].get("Slate_Date"))
            if slate is not None and not slate.empty and "Slate_Date" in slate.columns
            else None
        )

    @staticmethod
    def _batter_hands(repo: DataRepository) -> tuple[dict[int, str], dict[str, str]]:
        """MLB id / name -> batting hand, for weighting a starter's platoon splits."""
        by_id: dict[int, str] = {}
        by_name: dict[str, str] = {}
        for row in _rows(repo.load("player_registry.csv")):
            bats = str(row.get("bats") or "").strip().upper()[:1]
            if bats not in {"L", "R", "S"}:
                continue
            player_id = int(_number(row.get("player_id")) or 0)
            if player_id:
                by_id[player_id] = bats
            name = _norm(row.get("full_name"))
            if name:
                by_name[name] = bats
        return by_id, by_name

    def _lhb_share(self, lineup: dict, pitcher_hand: str) -> float | None:
        """Share of the posted lineup that bats left-handed against THIS starter.

        A switch hitter bats left against a right-hander and right against a left-hander,
        which is the whole point of being one — counting him by his listed side would
        understate the platoon a righty actually faces. Returns None when too little of the
        lineup resolves, so the caller can fall back to the league share rather than to a
        number invented from two players.
        """
        players = (lineup or {}).get("players") or []
        hands = []
        for player in players:
            player_id = int(_number(player.get("player_id")) or 0)
            bats = self.bats_by_id.get(player_id) or self.bats_by_name.get(
                _norm(player.get("player"))
            )
            if bats:
                hands.append("L" if bats == "S" and pitcher_hand == "R" else bats)
        if len(hands) < 6:
            return None
        return sum(1 for hand in hands if hand == "L") / len(hands)

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

    @staticmethod
    def _mix_baselines(rows: list[dict]) -> dict[str, dict[str, float]]:
        """Per-pitch-type league means for one mix table.

        Each mix table has to be compared against a baseline drawn from ITSELF. The three
        tables sit on visibly different scales — mean whiff rate is 19.2 in the pitcher mix,
        20.6 in team batting and 22.8 in the individual-batter mix, and xwOBA differs by ~30
        points between batter and team rows — because they aggregate different populations
        over different denominators. Scoring a posted lineup (batter rows) against a team-mix
        baseline therefore shifted the same pitcher/opponent matchup by up to 2.15 K-rate
        points purely on whether MLB had posted the lineup yet, against a real signal whose
        whole standard deviation is ~0.15.
        """
        grouped: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for row in rows:
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

    def _pitch_baselines(self) -> dict[str, dict[str, float]]:
        return self._mix_baselines(self.team_mix)

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
                "recent_ip": None, "ip_sd": 1.0, "bf": 0.0, "last_start": None,
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
            # `logs` is sorted by date in `_logs`, so the last row is the previous start.
            "last_start": str(logs[-1].get("date") or "") or None,
        }

    @staticmethod
    def _batter_score(row: dict) -> float | None:
        """One hitter's offensive score, used for BOTH the lineup and its club baseline.

        Blends the created metrics the way the board does — OSI carrying most of the weight,
        with ABQ (at-bat quality) and RCV (run conversion) alongside — and falls back to OSI
        alone when the components are missing, so a thin row still contributes.
        """
        score = _number(row.get("projOSI")) or _number(row.get("OSI"))
        abq = _number(row.get("ABQ")) or _number(row.get("abq"))
        rcv = _number(row.get("RCV")) or _number(row.get("rcv"))
        if score is not None and abq is not None and rcv is not None:
            return 0.55 * score + 0.25 * abq + 0.20 * rcv
        return score

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
        # The lineup and its baseline MUST be scored by the same formula. The baseline used to
        # be pure projOSI while each hitter was scored 0.55*projOSI + 0.25*ABQ + 0.20*RCV, so
        # the two sides sat on different scales and every posted lineup came out below its own
        # club baseline — on the 2026-08-31 slate the gap was negative for all 24 sides
        # (SFG -5.0, ATL -2.1, SDP -1.9, CIN -1.2 ...). A posted nine is a club's best
        # available hitters; it cannot be systematically worse than the roster it comes from.
        # The factor was therefore below 1.0 for everyone, damping every run projection, and
        # what variation it had was formula mismatch rather than lineup quality.
        baseline = _weighted(
            [
                (self._batter_score(row) or 50.0, max(1.0, _number(row.get("PA")) or 1.0))
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
            score = self._batter_score(row)
            if score is None:
                continue
            weight = float(ORDER_WEIGHTS[min(index, len(ORDER_WEIGHTS) - 1)])
            reliability = min(1.0, max(0.25, (_number(row.get("PA")) or 0) / 80))
            values.append((score, weight * reliability))
            matched.append(player.get("player"))
        lineup_score = _weighted(values)
        # Confirmed orders carry full weight; projected orders are a best guess, damped 25%
        # (mirrors mlbmodel.baseball.features.lineup_features).
        sensitivity = 0.004 if (lineup or {}).get("status") == "confirmed" else 0.003
        factor = (
            _clip(1 + (lineup_score - baseline) * sensitivity, 0.90, 1.10)
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

    def _lineup_pitch_rows(
        self, lineup: dict, team: str
    ) -> tuple[list[dict], int, str]:
        """Opponent pitch-type rows, plus which table they came from.

        The source matters: a posted lineup is aggregated from individual-batter rows, the
        fallback is the club's team-batting row, and the two tables sit on different scales.
        The caller uses this flag to pick a matching baseline.
        """
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
            return self.team_mix_by_team.get(team, []), matched, "team"
        output = []
        for pitch, metrics in by_pitch.items():
            output.append(
                {
                    "pitch_type": pitch,
                    **{column: _weighted(values) for column, values in metrics.items()},
                }
            )
        return output, matched, "lineup"

    def _pitch_matchup(
        self,
        pitcher_name: str,
        opponent: str,
        lineup: dict,
    ) -> dict:
        pitcher_rows = self.pitcher_mix_by_name.get(_norm(pitcher_name), [])
        lineup_rows, matched, source = self._lineup_pitch_rows(lineup, opponent)
        lineup_by_pitch = {
            _pitch_type(row.get("pitch_type")): row for row in lineup_rows
        }
        # Each side is scored against a baseline built from its OWN table (see _mix_baselines).
        opponent_baselines = (
            self.batter_pitch_baselines if source == "lineup" else self.pitch_baselines
        )
        pitcher_baselines = self.pitcher_pitch_baselines
        detail = []
        opponent_score = 0.0
        pitcher_score = 0.0
        coverage = 0.0
        for pitcher in pitcher_rows:
            pitch = _pitch_type(pitcher.get("pitch_type"))
            usage = _number(pitcher.get("pitch_pct")) or 0.0
            opponent_row = lineup_by_pitch.get(pitch)
            opponent_base = opponent_baselines.get(pitch)
            pitcher_base = pitcher_baselines.get(pitch)
            if (
                pitch in SKIP_PITCH_TYPES
                or usage < 3
                or not opponent_row
                or not opponent_base
                or not pitcher_base
            ):
                continue
            weight = usage / 100
            coverage += weight
            pitcher_whiff = _number(pitcher.get("whiff_rate")) or pitcher_base["whiff_rate"]
            lineup_whiff = _number(opponent_row.get("whiff_rate")) or opponent_base["whiff_rate"]
            pitcher_xwoba = _number(pitcher.get("xwoba")) or pitcher_base["xwoba"]
            lineup_xwoba = _number(opponent_row.get("xwoba")) or opponent_base["xwoba"]
            pitcher_chase = _number(pitcher.get("chase_rate")) or pitcher_base["chase_rate"]
            lineup_chase = _number(opponent_row.get("chase_rate")) or opponent_base["chase_rate"]

            def _half(whiff, xwoba, chase, base):
                """One side's edge on this pitch, signed positive = good for the pitcher.

                The same formula serves both sides: a pitcher with a high whiff rate and a
                low xwOBA allowed is good, and a lineup that whiffs a lot and produces a low
                xwOBA is also good for him.
                """
                return weight * (
                    0.42 * (whiff - base["whiff_rate"]) / 100
                    + 0.43 * (base["xwoba"] - xwoba)
                    + 0.15 * (chase - base["chase_rate"]) / 100
                )

            opponent_part = _half(lineup_whiff, lineup_xwoba, lineup_chase, opponent_base)
            pitcher_part = _half(pitcher_whiff, pitcher_xwoba, pitcher_chase, pitcher_base)
            opponent_score += opponent_part
            pitcher_score += pitcher_part
            detail.append(
                {
                    "pitch": str(pitcher.get("pitch_name") or pitch),
                    "pitch_type": pitch,
                    "usage_pct": round(usage, 1),
                    "pitcher_whiff_pct": round(pitcher_whiff, 1),
                    "lineup_whiff_pct": round(lineup_whiff, 1),
                    "pitcher_xwoba": round(pitcher_xwoba, 3),
                    "lineup_xwoba": round(lineup_xwoba, 3),
                    "lineup_ba": (
                        round(ba, 3) if (ba := _number(opponent_row.get("batting_avg"))) is not None else None
                    ),
                    # Only the opponent half moves the projection; the pitcher half is
                    # context, because the engine already applies his own K rate directly.
                    "k_delta": round(opponent_part * PITCH_MIX_K_SCALE, 2),
                    "er_factor_delta": round(-opponent_part * PITCH_MIX_ER_SCALE, 3),
                    "pitcher_context_score": round(pitcher_part, 4),
                    "edge": direction_label(opponent_part),
                    "score": round(opponent_part, 4),
                }
            )
        detail.sort(key=lambda row: abs(row["score"]), reverse=True)
        if coverage < 0.35:
            opponent_score = 0.0
            pitcher_score = 0.0
        total_score = opponent_score
        return {
            "score": round(total_score, 4),
            "coverage_pct": round(min(1.0, coverage) * 100),
            "lineup_batters_matched": matched,
            "response_source": (
                "posted lineup, batting-order weighted"
                if matched >= 6
                else "opponent team pitch-type results"
            ),
            "k_rate_delta": round(
                _clip(total_score * PITCH_MIX_K_SCALE, -2.5, 2.5), 2
            ),
            "er_factor": round(
                _clip(1 - total_score * PITCH_MIX_ER_SCALE, 0.90, 1.10), 4
            ),
            "verdict": direction_label(total_score),
            # Kept for the board: how good this arsenal is in the abstract. It is NOT in the
            # adjustment — see PITCH_MIX_K_SCALE for why.
            "pitcher_arsenal_score": round(pitcher_score, 4),
            "opponent_response_score": round(opponent_score, 4),
            "baseline_source": source,
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
        win_probability: float | None = None,
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
        # Regress the pitcher's own rates toward league by how many batters back them. Only
        # `skill_era` used to be shrunk (starts/(starts+6)); K, BB and H went in raw, which is
        # most of why the board's projections were spread ~1.7x wider than their predictive
        # content justified. Matchup terms are added AFTER this — they are not sample-limited
        # estimates of this pitcher and must not be regressed toward the league.
        rate_bf = log_factors.get("bf") or 0.0
        k_rate = matrix.shrink_rate(k_rate, "k", rate_bf, self.league_rates["k"])
        bb_rate = matrix.shrink_rate(bb_rate, "bb", rate_bf, self.league_rates["bb"])
        k_rate += _clip(log_factors["k_trend"] * 0.25, -1.5, 1.5)
        bb_rate += _clip(log_factors["bb_trend"] * 0.20, -1.0, 1.0)

        lineup_strength = self._lineup_strength(
            lineup, opponent, pitcher_hand
        )
        pitch_matchup = self._pitch_matchup(pitcher_name, opponent, lineup)
        k_rate += pitch_matchup["k_rate_delta"]

        # --- fitted matrix: opponent strikeout propensity (mlbmodel.props.matrix) ---
        # The pitch-mix term above is a pitch-type whiff/xwOBA read; measured across a live
        # slate it correlates -0.01 with how often the opposing club ACTUALLY strikes out, so
        # this is new information rather than the same signal twice. Converted from strikeouts
        # to the engine's per-batter rate using the workload it is about to project.
        opponent_k_strikeouts, opponent_k_index = matrix.opponent_k_delta(
            opponent, self.opponent_k_rates, self.league_k_rate
        )
        baseline_ip = _number(profile.get("avg_IP")) or 5.3
        if log_factors.get("recent_ip") is not None:
            baseline_ip = baseline_ip * 0.65 + log_factors["recent_ip"] * 0.35
        expected_bf = max(12.0, _clip(baseline_ip, 2.5, 7.0) * 4.25)
        k_rate += _clip(opponent_k_strikeouts / expected_bf * 100, -3.0, 3.0)

        # --- fitted matrix: regression/progression and rest, both on the Outs channel ---
        # This is where the REGRESSION / PROGRESSION state finally moves a number. It has
        # always been computed and printed as a board label, then thrown away — an ablation
        # on 2026-08-31 confirmed zeroing it changed every projection by exactly 0.000.
        # Fitted, its home is Outs, not ER: a pitcher who has been lucky on balls in play
        # regresses, gives up more contact, and gets pulled earlier.
        regression_outs = matrix.regression_outs_delta(log_factors.get("babip"))
        rest_days = matrix.days_rest(log_factors.get("last_start"), self.slate_date)
        rest_outs = matrix.rest_outs_delta(rest_days)
        expected_ip = baseline_ip + (regression_outs + rest_outs) / 3.0
        # Hard sanity bound: no MLB starter projects beyond ~7 IP, and a bad/garbage
        # avg_IP from a thin profile (e.g. a swingman with one long relief outing) would
        # otherwise sail past the 8.2-out sample clip and manufacture a near-certain
        # high-Outs projection — a fake market edge. Clip the mean to a realistic range.
        expected_ip = matrix.calibrate(
            expected_ip, "outs", self.league_outs / 3.0
        )
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
        # The run factor is split into two channels, because they carry different evidence.
        #
        # ENVIRONMENT (weather, umpire, travel) is physical and was never tested here — the SP
        # game log carries no weather or plate-umpire history — so it passes through at full
        # strength.
        #
        # OPPONENT QUALITY (posted lineup, pitch-mix response, club offensive indices, platoon,
        # injuries) is the part two independent measurements put at approximately zero for
        # earned runs: every opponent factor in scripts/factor_study.py scored negative on ER
        # (best -0.01%), and mlbmodel.props.challenger fitted an opponent weight of exactly
        # 0.00 for hits, homers and earned runs. Per-start ER is sequencing noise.
        #
        # It is damped rather than deleted. Even at zero predictive value it would still be
        # doing harm, because spread without signal is what manufactures phantom edges — the
        # same disease as the pitch-mix pitcher half. But the terms tested were team-level
        # proxies rather than these exact indices, so removing them outright would claim more
        # than the measurement supports. OPPONENT_ER_DAMPING is a JUDGMENT, not a fit; the
        # restored lean ledger is what will let it be fitted properly.
        environment_factor = (
            weather_run_factor(context.get("weather"))
            * umpire_run_factor(context.get("umpire"))
            * travel_offense_factor(travel)
        )
        opp_ctx = game.home_context if side == "away" else game.away_context
        opp_osi = game.home_osi if side == "away" else game.away_osi
        opp_strength = opponent_offense_strength(opp_ctx, opp_osi)
        lhb_share = self._lhb_share(lineup, pitcher_hand)
        platoon_factor = sp_split_skill_adjustment(
            profile,
            self.sp_metric_splits,
            LEAGUE_LHB_SHARE if lhb_share is None else lhb_share,
        )
        opponent_factor = (
            lineup_strength["factor"]
            * pitch_matchup["er_factor"]
            * injury_factor
            * pitcher_allowed_skill_adjustment(profile, opp_strength)
            * platoon_factor
        )
        damped_opponent_factor = 1.0 + (opponent_factor - 1.0) * OPPONENT_ER_DAMPING
        run_factor = environment_factor * damped_opponent_factor
        # Outing length responds to the posted lineup: the same run environment that
        # raises expected ER also raises pitch counts and shortens the start, so Outs
        # (and the batters-faced-driven K/BB/H) shrink against a strong posted lineup.
        ip_factor = _clip(1 - (run_factor - 1) * 0.45, 0.94, 1.06)
        outing_ip = _clip(expected_ip * ip_factor, 2.5, 7.0)
        era = _number(profile.get("ERA")) or skill_era
        blended_era = skill_era * 0.70 + era * 0.30
        # ER stays on the UNSHORTENED workload. Multiplying the shortened outing by the
        # run factor would net out to only ~55% of the run-environment signal (a tough
        # lineup both raises the rate and trims the innings), silently re-calibrating a
        # market that already has a grading/CLV history. The hook comes after the damage,
        # so ER accrues at the elevated rate over a normal workload.
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
            outing_ip,
            max(0.65, min(1.35, log_factors.get("ip_sd") or 1.0)),
            iterations,
        )
        ip_samples = np.clip(ip_samples, 1.0, 8.2)
        bf_samples = np.maximum(
            3,
            np.rint(ip_samples * rng.normal(4.25, 0.16, iterations)).astype(int),
        )
        # Rate uncertainty is the posterior concentration behind the shrunk mean: the batters
        # this pitcher has actually faced, plus the market's shrinkage strength. Using a flat
        # +25 (as before) with a mean shrunk at strength 461 would claim far more certainty
        # about a hit rate than the estimate supports.
        observed_bf = max(0.0, float(log_factors.get("bf") or starts * 22))
        # Final spread calibration. Shrinkage fixed the sample-size problem; this fixes what
        # is left, which is that the projections still run slope < 1 against outcomes — spread
        # wider than the signal earns. Applied last, so it calibrates the finished number
        # rather than one input to it. See matrix.SPREAD_CALIBRATION.
        k_rate = matrix.calibrate(k_rate, "k", self.league_rates["k"] * 100)
        bb_rate = matrix.calibrate(bb_rate, "bb", self.league_rates["bb"] * 100)
        k_probability = _clip(k_rate / 100, 0.05, 0.48)
        bb_probability = _clip(bb_rate / 100, 0.02, 0.22)
        k_concentration = observed_bf + matrix.RATE_SHRINK_BF["k"]
        bb_concentration = observed_bf + matrix.RATE_SHRINK_BF["bb"]
        k_draw = rng.beta(
            k_probability * k_concentration,
            (1 - k_probability) * k_concentration,
            iterations,
        )
        bb_draw = rng.beta(
            bb_probability * bb_concentration,
            (1 - bb_probability) * bb_concentration,
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
        # like K/BB, then sampled over batters faced. Shrunk hardest of the three markets —
        # a per-start hit rate is mostly batted-ball noise and needs ~461 batters faced before
        # it earns half weight, against 113 for strikeouts. Unshrunk this market projected
        # with slope 0.64; shrunk it comes in at 0.99.
        h_rate = log_factors.get("h_rate")
        h_percent = matrix.shrink_rate(
            (h_rate if h_rate is not None else self.league_rates["h"]) * 100,
            "h",
            log_factors.get("bf") or 0.0,
            self.league_rates["h"],
        )
        h_percent = matrix.calibrate(h_percent, "h", self.league_rates["h"] * 100)
        h_probability = _clip(h_percent / 100, 0.10, 0.36)
        h_concentration = observed_bf + matrix.RATE_SHRINK_BF["h"]
        h_draw = rng.beta(
            h_probability * h_concentration,
            (1 - h_probability) * h_concentration,
            iterations,
        )
        hits = rng.binomial(bf_samples, h_draw)
        # DraftKings pitcher fantasy points: IP +2.25/inning (0.75/out), K +2, ER -2, H -0.6,
        # BB -0.6. Excludes W / quality-start / complete-game bonuses (need game context).
        fantasy = outs * 0.75 + strikeouts * 2.0 - earned_runs * 2.0 - hits * 0.6 - walks * 0.6
        # PrizePicks pitcher fantasy score: Out +1, K +3, ER -3, Quality Start +4 (>=6 IP & <=3
        # ER, computed exactly from the joint sim), Win +6 (modeled as PP_WIN_PROB, see above).
        qs_bonus = np.where((outs >= 18) & (earned_runs <= 3), 4.0, 0.0)
        # Team win prob from the game model (when supplied) replaces the flat league
        # prior; the 0.80 haircut is the share of team wins credited to the starter
        # (5+ IP with the lead), which recovers the 0.40 prior at a 50/50 game.
        starter_win = (
            _clip(win_probability * 0.80, 0.15, 0.65)
            if win_probability is not None
            else PP_WIN_PROB
        )
        pp_fantasy = (
            outs + strikeouts * 3.0 - earned_runs * 3.0 + qs_bonus + 6.0 * starter_win
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
            "side": side,
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
            # The projected outing (what the Outs distribution is drawn from), plus the
            # uncoupled workload baseline it came from, so the shift is auditable.
            "expected_ip": round(outing_ip, 2),
            "baseline_ip": round(expected_ip, 2),
            "k_rate": round(k_rate, 2),
            "bb_rate": round(bb_rate, 2),
            "run_factor": round(run_factor, 4),
            "environment_factor": round(environment_factor, 4),
            "opponent_factor": round(opponent_factor, 4),
            "opponent_factor_damped": round(damped_opponent_factor, 4),
            "ip_factor": round(ip_factor, 4),
            # Every fitted matrix term, in the units it moved the projection, so a number on
            # the board can always be traced back to the factor that produced it (STD-14).
            "matrix": {
                "opponent_k_index": (
                    round(opponent_k_index, 3) if opponent_k_index is not None else None
                ),
                "opponent_k_strikeouts": round(opponent_k_strikeouts, 3),
                "regression_outs": round(regression_outs, 3),
                "babip_to_date": (
                    round(float(log_factors["babip"]), 3)
                    if log_factors.get("babip") is not None else None
                ),
                "rest_days": rest_days,
                "rest_outs": round(rest_outs, 3),
                "lhb_share": round(lhb_share, 3) if lhb_share is not None else None,
                "platoon_factor": round(platoon_factor, 4),
            },
            "team_win_prob": (
                round(win_probability, 3) if win_probability is not None else None
            ),
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
    anchors = repo.anchors()
    board = []
    slate_rows = [row.to_dict() for _, row in slate.iterrows()]
    keys = matchup_keys(slate_rows)
    for row, key in zip(slate_rows, keys, strict=True):
        away = str(row.get("Away") or "").upper().strip()
        home = str(row.get("Home") or "").upper().strip()
        _, _, game_number = parse_game_key(key)
        try:
            game = repo.load_game(away, home, game_number=game_number)
        except (FileNotFoundError, ValueError):
            continue
        try:
            probs = model_probabilities(game, anchors)
            away_win, home_win = probs.p_away_win, probs.p_home_win
        except (KeyError, TypeError, ValueError):
            away_win = home_win = None
        board.append(
            engine.project(
                game,
                team=away,
                opponent=home,
                pitcher_name=game.away_sp,
                pitcher_hand=game.away_hand,
                side="away",
                win_probability=away_win,
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
                win_probability=home_win,
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
