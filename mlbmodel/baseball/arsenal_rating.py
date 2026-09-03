"""Arsenal rating — how an offense has fared against the pitch types a starter throws.

Two things are computed here and they answer different questions, so they are kept apart:

  * `hand_split()` — a club's real vs-LHP / vs-RHP line over a recent window. Every plate
    appearance against a pitcher of that hand, relievers included.
  * `rate()` — a 0-100 rating of the club against ONE pitcher's arsenal, built from the four
    axes that make up run scoring: run creation (wOBA), power (ISO), average (AVG) and
    walks (BB%), each usage-weighted across the pitches he actually throws.

## What the rating is, and what it is not

It is a **descriptive form read**: what this offense has done against these pitch types, in
the window shown on the card, ranked against the other 29 clubs facing the same arsenal.
Everything in it is measured; nothing is projected.

It is NOT a forecast, and the repository should not start treating it as one. Measured on a
strict time split (pitch-type table built through 2026-07-15, outcomes from 2026-07-16 to
08-30, 1,068 starts), the pitch-SPECIFIC part of these numbers does not carry forward:

    train -> test correlation of a club's edge over the league on one pitch type
        K%  +0.238   BB%  +0.142   ISO  +0.037   AVG  -0.035   wOBA  -0.094

and the arsenal-weighted value never beat simply using the club's overall level on the same
axis (K% 0.458 vs 0.556 flat; ISO 0.157 vs 0.256 flat). So a club that has crushed sliders
for four months is not thereby likely to crush the next slider. Feeding this rating into the
run model as a predictor would be adding noise — it is a scouting panel, deliberately kept
out of `baseball/model.py`.

## Why it is still built the way it is

Two design choices follow from that measurement rather than from taste:

  * **The prior is the club's own level, not the league's.** A club's overall walk rate is a
    real, wide trait (sd 0.72 BB points across clubs); its walk rate *against sliders
    specifically* is not distinguishable from sampling noise. So each cell is shrunk toward
    "league rate for this pitch type, plus this club's own overall edge", which keeps the
    real signal and damps the wiggle.
  * **The shrinkage constants are fitted, not chosen.** Regressing squared residuals on 1/PA
    over 278 team-by-pitch cells splits observed spread into sampling noise (c/n) and true
    spread (a); k = c/a is the PA count at which a cell earns half its own weight. BB% came
    out with a <= 0 — its entire between-cell spread is explained by sampling noise — so its
    pitch-specific term is shrunk away completely and the axis reports the club's own walk
    profile against the arsenal's league walk profile, which is the honest reading.

The composite weights (wOBA .26 / ISO .36 / AVG .25 / BB% .13) are a ridge fit of team runs
per plate appearance on the four standardized axes across the 30 clubs; the resulting
composite correlates +0.910 with actual runs per PA, and the weights are stable under
leave-one-out (ISO .30-.41, BB% .10-.15). They are collinear by construction — wOBA is
itself a run-value blend of the other three — so read them as an apportionment, not as
causal coefficients.
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field

AXES: tuple[str, ...] = ("woba", "iso", "avg", "bb_pct")
CONTEXT_AXES: tuple[str, ...] = ("k_pct",)
ALL_AXES = AXES + CONTEXT_AXES

AXIS_LABEL = {
    "woba": "Run creation",
    "iso": "Power",
    "avg": "Average",
    "bb_pct": "Walks",
    "k_pct": "Strikeouts",
}
AXIS_SHORT = {"woba": "wOBA", "iso": "ISO", "avg": "AVG", "bb_pct": "BB%", "k_pct": "K%"}
AXIS_DIGITS = {"woba": 3, "iso": 3, "avg": 3, "bb_pct": 1, "k_pct": 1}
AXIS_SUFFIX = {"bb_pct": "%", "k_pct": "%"}
# A high K% is bad for the offense; every other axis reads better when higher.
AXIS_HIGHER_IS_BETTER = {"woba": True, "iso": True, "avg": True, "bb_pct": True,
                         "k_pct": False}

WEIGHTS = {"woba": 0.26, "iso": 0.36, "avg": 0.25, "bb_pct": 0.13}

# PA at which a team-by-pitch-type cell earns half its own weight against the prior.
# Fitted (see module docstring); None means the pitch-specific term is pure noise and the
# cell is replaced by the prior outright.
SHRINK_PA: dict[str, float | None] = {
    "woba": 420.0, "iso": 420.0, "avg": 1320.0, "bb_pct": None, "k_pct": 230.0,
}

# A pitch thrown this rarely is not part of the plan; including it just adds thin cells.
MIN_USAGE_PCT = 3.0
# Usage points that must resolve to a scored cell before a rating is issued.
MIN_COVERAGE_PCT = 55.0
MIN_TEAMS_FOR_RANK = 20
RATING_SPREAD = 15.0

_LEAGUE_KEY = "LGE"


def norm_name(value: object) -> str:
    """'Skubal, Tarik' and 'Tarik Skubal' have to land on the same key."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    if "," in text:
        last, _, first = text.partition(",")
        text = f"{first} {last}"
    return " ".join(text.lower().replace(".", "").split())


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


@dataclass
class AxisRead:
    axis: str
    team_value: float
    league_value: float
    z: float
    rank: int | None = None
    teams_ranked: int = 0

    @property
    def label(self) -> str:
        return AXIS_LABEL[self.axis]

    @property
    def short(self) -> str:
        return AXIS_SHORT[self.axis]

    @property
    def delta(self) -> float:
        return self.team_value - self.league_value

    @property
    def score(self) -> float:
        """0-100 placement of this axis against the league facing the same arsenal."""
        signed = self.z if AXIS_HIGHER_IS_BETTER[self.axis] else -self.z
        return max(1.0, min(99.0, 50.0 + RATING_SPREAD * signed))


@dataclass
class ArsenalRead:
    team: str
    pitcher: str
    rating: float
    rank: int | None
    teams_ranked: int
    coverage_pct: float
    pa: int
    axes: dict[str, AxisRead] = field(default_factory=dict)
    pitches: list[dict] = field(default_factory=list)
    window: tuple[str, str] = ("", "")

    @property
    def verdict(self) -> str:
        """Same Pitcher / Lineup / Neutral vocabulary the pitch-mix board already uses."""
        if self.rating >= 60:
            return "Lineup"
        if self.rating <= 40:
            return "Pitcher"
        return "Neutral"


class ArsenalRatingEngine:
    """Reads `team_pitch_type_splits.csv` + `team_hand_splits.csv` and scores matchups."""

    def __init__(self, repo) -> None:
        self.repo = repo
        self.ok = False
        self._league: dict[str, dict[str, float]] = {}
        self._league_pa: dict[str, float] = {}
        self._cells: dict[tuple[str, str], dict[str, float]] = {}
        self._cell_pa: dict[tuple[str, str], float] = {}
        self._club: dict[str, dict[str, float]] = {}
        self._league_overall: dict[str, float] = {}
        self.teams: list[str] = []
        self.window: tuple[str, str] = ("", "")
        self._hand: dict[tuple[str, str], dict] = {}
        self.hand_window: tuple[str, str] = ("", "")
        self._arsenals: dict[str, list[tuple[str, float, str]]] = {}
        self._load_mix()
        self._load_hand()
        self._load_arsenals()

    # ── loading ────────────────────────────────────────────────────────────────────
    def _load_mix(self) -> None:
        frame = self.repo.load("team_pitch_type_splits.csv")
        if frame is None or frame.empty:
            return
        team_pa: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for row in frame.to_dict("records"):
            team = str(row.get("team") or "").upper()
            pitch = str(row.get("pitch_type") or "").upper()
            pa = _number(row.get("pa")) or 0.0
            if not team or not pitch or pa <= 0:
                continue
            values = {axis: _number(row.get(axis)) for axis in ALL_AXES}
            values = {axis: value for axis, value in values.items() if value is not None}
            if not values:
                continue
            if team == _LEAGUE_KEY:
                self._league[pitch] = values
                self._league_pa[pitch] = pa
                continue
            self._cells[(team, pitch)] = values
            self._cell_pa[(team, pitch)] = pa
            for axis, value in values.items():
                team_pa.setdefault(team, {}).setdefault(axis, []).append((value, pa))
            if not self.window[0]:
                self.window = (str(row.get("window_start") or ""),
                               str(row.get("window_end") or ""))
        if not self._league or not self._cells:
            return
        self._league_overall = {
            axis: _weighted_mean([(values[axis], self._league_pa[pitch])
                                  for pitch, values in self._league.items()
                                  if axis in values])
            for axis in ALL_AXES
        }
        self._league_overall = {a: v for a, v in self._league_overall.items() if v is not None}
        for team, per_axis in team_pa.items():
            club = {axis: _weighted_mean(pairs) for axis, pairs in per_axis.items()}
            self._club[team] = {a: v for a, v in club.items() if v is not None}
        self.teams = sorted(self._club)
        self.ok = len(self.teams) >= MIN_TEAMS_FOR_RANK

    def _load_hand(self) -> None:
        frame = self.repo.load("team_hand_splits.csv")
        if frame is None or frame.empty:
            return
        for row in frame.to_dict("records"):
            team = str(row.get("team") or "").upper()
            hand = str(row.get("pitcher_hand") or "").upper()
            if not team or hand not in {"L", "R"}:
                continue
            self._hand[(team, hand)] = row
            if not self.hand_window[0]:
                self.hand_window = (str(row.get("window_start") or ""),
                                    str(row.get("window_end") or ""))

    def _load_arsenals(self) -> None:
        """Prefer the 14-day arsenal; fall back per pitcher to the season table."""
        for filename in ("pitch_mix_pitcher.csv", "pitch_mix_pitcher_l14.csv"):
            frame = self.repo.load(filename)
            if frame is None or frame.empty:
                continue
            grouped: dict[str, list[tuple[str, float, str]]] = {}
            for row in frame.to_dict("records"):
                usage = _number(row.get("pitch_pct")) or 0.0
                pitch = str(row.get("pitch_type") or "").upper()
                if usage < MIN_USAGE_PCT or not pitch:
                    continue
                key = norm_name(row.get("full_name"))
                if not key:
                    continue
                grouped.setdefault(key, []).append(
                    (pitch, usage, str(row.get("pitch_name") or pitch))
                )
            # Later file wins per pitcher, so the L14 arsenal replaces the season one only
            # for arms that actually have recent rows.
            for key, mix in grouped.items():
                self._arsenals[key] = sorted(mix, key=lambda item: -item[1])

    # ── scoring ────────────────────────────────────────────────────────────────────
    def arsenal(self, pitcher_name: str) -> list[tuple[str, float, str]]:
        return self._arsenals.get(norm_name(pitcher_name), [])

    def _prior(self, team: str, pitch: str, axis: str) -> float | None:
        league = (self._league.get(pitch) or {}).get(axis)
        if league is None:
            return None
        edge = (self._club.get(team, {}).get(axis))
        overall = self._league_overall.get(axis)
        if edge is None or overall is None:
            return league
        return league + (edge - overall)

    def _cell_value(self, team: str, pitch: str, axis: str) -> float | None:
        prior = self._prior(team, pitch, axis)
        if prior is None:
            return None
        constant = SHRINK_PA.get(axis)
        if constant is None:
            # Whole between-cell spread on this axis is sampling noise (see docstring).
            return prior
        observed = (self._cells.get((team, pitch)) or {}).get(axis)
        if observed is None:
            return prior
        pa = self._cell_pa.get((team, pitch), 0.0)
        return (pa * observed + constant * prior) / (pa + constant)

    def _weighted(self, team: str, arsenal, axis: str) -> tuple[float, float, float] | None:
        """(team value, league value, usage covered) for one axis against one arsenal."""
        num = league_num = covered = 0.0
        for pitch, usage, _ in arsenal:
            league = (self._league.get(pitch) or {}).get(axis)
            value = self._cell_value(team, pitch, axis)
            if league is None or value is None:
                continue
            num += usage * value
            league_num += usage * league
            covered += usage
        if covered < MIN_COVERAGE_PCT:
            return None
        return num / covered, league_num / covered, covered

    def rate(self, team: str, pitcher_name: str) -> ArsenalRead | None:
        team = str(team or "").upper()
        arsenal = self.arsenal(pitcher_name)
        if not self.ok or not arsenal or team not in self._club:
            return None

        # Every axis is scored across all 30 clubs facing THIS arsenal, so the structural
        # bias of attributing a plate appearance to its final pitch — a sinker rarely ends
        # one in a strikeout, ball four is usually a fastball — cancels out of the comparison.
        across: dict[str, dict[str, tuple[float, float, float]]] = {}
        for axis in ALL_AXES:
            scored = {}
            for other in self.teams:
                got = self._weighted(other, arsenal, axis)
                if got is not None:
                    scored[other] = got
            if team in scored and len(scored) >= MIN_TEAMS_FOR_RANK:
                across[axis] = scored
        if not set(AXES).issubset(across):
            return None

        axes: dict[str, AxisRead] = {}
        zs: dict[str, dict[str, float]] = {}
        coverage = 0.0
        for axis, scored in across.items():
            values = [value for value, _, _ in scored.values()]
            mean, spread = _mean_sd(values)
            team_value, league_value, covered = scored[team]
            coverage = max(coverage, covered)
            zs[axis] = {
                other: (0.0 if spread <= 0 else (value - mean) / spread)
                for other, (value, _, _) in scored.items()
            }
            ordered = sorted(values, reverse=AXIS_HIGHER_IS_BETTER[axis])
            axes[axis] = AxisRead(
                axis=axis, team_value=team_value, league_value=league_value,
                z=zs[axis][team], rank=ordered.index(team_value) + 1,
                teams_ranked=len(values),
            )

        rated = [other for other in self.teams if all(other in zs[axis] for axis in AXES)]
        blends = {
            other: sum(
                WEIGHTS[axis] * zs[axis][other]
                * (1.0 if AXIS_HIGHER_IS_BETTER[axis] else -1.0)
                for axis in AXES
            )
            for other in rated
        }
        # Standardise the blend empirically rather than assuming independence: these axes
        # are strongly correlated (wOBA is a run-value blend of the other three), so the
        # weighted sum's spread is much narrower than sqrt(sum of squared weights).
        blend_mean, blend_sd = _mean_sd(list(blends.values()))
        normalised = 0.0 if blend_sd <= 0 else (blends[team] - blend_mean) / blend_sd
        rating = max(2.0, min(98.0, 50.0 + RATING_SPREAD * normalised))
        ranking = sorted(blends, key=lambda name: -blends[name])
        rank = ranking.index(team) + 1

        pitches = []
        for pitch, usage, name in arsenal:
            league = (self._league.get(pitch) or {}).get("woba")
            value = self._cell_value(team, pitch, "woba")
            if league is None or value is None:
                continue
            pitches.append({
                "pitch_type": pitch,
                "pitch_name": name,
                "usage_pct": usage,
                "pa": int(self._cell_pa.get((team, pitch), 0)),
                "woba": value,
                "league_woba": league,
                "avg": self._cell_value(team, pitch, "avg"),
                "iso": self._cell_value(team, pitch, "iso"),
                "k_pct": self._cell_value(team, pitch, "k_pct"),
            })

        return ArsenalRead(
            team=team, pitcher=str(pitcher_name or ""), rating=rating, rank=rank,
            teams_ranked=len(ranking), coverage_pct=coverage,
            pa=sum(int(self._cell_pa.get((team, pitch), 0)) for pitch, _, _ in arsenal),
            axes=axes, pitches=pitches, window=self.window,
        )

    # ── hand splits ────────────────────────────────────────────────────────────────
    def hand_split(self, team: str, hand: str) -> dict | None:
        row = self._hand.get((str(team or "").upper(), str(hand or "").upper()))
        return dict(row) if row else None

    def league_hand_split(self, hand: str) -> dict | None:
        return self.hand_split(_LEAGUE_KEY, hand)


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return None
    return sum(value * weight for value, weight in pairs) / total


def _mean_sd(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)
    return mean, math.sqrt(variance)
