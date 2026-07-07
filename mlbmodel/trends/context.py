"""Resolve the full situational context for one upcoming game.

``SituationalContext`` pulls today's matchup (teams, probable starters + handedness, park)
and lazily loads the historical tables the detectors need, normalized to plain helpers so a
detector never has to know how a CSV is shaped. Tables are cached on the context so a daily
batch over the whole slate parses each file once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import pandas as pd

from mlbmodel.baseball.repository import DataRepository


def _f(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        out = float(value)
        return None if math.isnan(out) else out
    except (TypeError, ValueError):
        return None


@dataclass
class TeamSituation:
    """The half of a matchup belonging to one team."""

    team: str
    side: str                       # "away" | "home"
    starter: str                    # this team's probable starter
    starter_hand: str               # this team's starter hand
    opp_team: str
    opp_starter: str                # the starter this team's bats face
    opp_starter_hand: str           # hand this team's bats face (drives platoon/form lookups)


@dataclass
class SituationalContext:
    """Everything the detectors need for one game, with cached table access."""

    repo: DataRepository
    slate_date: str
    away: str
    home: str
    away_situation: TeamSituation
    home_situation: TeamSituation
    park_factor: float | None
    stadium: str | None
    _cache: dict[str, pd.DataFrame] = field(default_factory=dict)

    # ── table access (parsed once, cached) ─────────────────────────────────
    def table(self, name: str) -> pd.DataFrame:
        if name not in self._cache:
            df = self.repo.load(f"{name}.csv")
            self._cache[name] = df if df is not None else pd.DataFrame()
        return self._cache[name]

    @cached_property
    def reliever_log(self) -> pd.DataFrame:
        return self.table("reliever_log")

    @cached_property
    def l10_sp_hand(self) -> pd.DataFrame:
        return self.table("team_l10_sp_hand")

    @cached_property
    def team_profiles(self) -> pd.DataFrame:
        return self.table("team_profiles")

    @cached_property
    def sp_profiles(self) -> pd.DataFrame:
        return self.table("sp_profiles")

    @cached_property
    def bullpen_unit(self) -> pd.DataFrame:
        return self.table("bullpen_unit")

    def situations(self) -> list[TeamSituation]:
        return [self.away_situation, self.home_situation]

    # ── construction ───────────────────────────────────────────────────────
    @classmethod
    def resolve(cls, repo: DataRepository, away: str, home: str) -> "SituationalContext":
        slate = repo.slate()
        row: dict[str, Any] = {}
        slate_date = ""
        if slate is not None and not slate.empty:
            match = slate[(slate.get("Away") == away) & (slate.get("Home") == home)]
            if not match.empty:
                row = match.iloc[0].to_dict()
                slate_date = str(row.get("Slate_Date") or "")[:10]

        away_hand = str(row.get("Away_Hand") or "R").upper()[:1] or "R"
        home_hand = str(row.get("Home_Hand") or "R").upper()[:1] or "R"
        away_sp = str(row.get("Away_SP") or "TBD")
        home_sp = str(row.get("Home_SP") or "TBD")

        away_sit = TeamSituation(
            team=away, side="away", starter=away_sp, starter_hand=away_hand,
            opp_team=home, opp_starter=home_sp, opp_starter_hand=home_hand,
        )
        home_sit = TeamSituation(
            team=home, side="home", starter=home_sp, starter_hand=home_hand,
            opp_team=away, opp_starter=away_sp, opp_starter_hand=away_hand,
        )

        park_factor: float | None = None
        stadium: str | None = None
        try:
            game = repo.load_game(away, home)
            park_factor = _f(getattr(game, "park_factor", None))
            weather = getattr(game, "weather", None) or {}
            stadium = weather.get("stadium") if isinstance(weather, dict) else None
        except Exception:
            pass

        return cls(
            repo=repo, slate_date=slate_date, away=away, home=home,
            away_situation=away_sit, home_situation=home_sit,
            park_factor=park_factor, stadium=stadium,
        )
