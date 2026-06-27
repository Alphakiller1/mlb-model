"""Point-in-time MLBMA CSV access with explicit freshness and fallbacks."""
from __future__ import annotations

import datetime as dt
import math
import zlib
from pathlib import Path

import pandas as pd

from mlbmodel import settings
from mlbmodel.baseball.model import GameData, TeamContext, clip


def _number(value) -> float | None:
    try:
        if value is None or value == "" or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _percent(value) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number * 100 if number <= 1.5 else number


def canonical_game_pk(game_date: str, away: str, home: str, game_number: int = 1) -> int:
    suffix = "" if game_number == 1 else f"|{game_number}"
    payload = f"{game_date}|{away}|{home}{suffix}".encode()
    return zlib.crc32(payload)


class DataRepository:
    def __init__(self, data_dir: Path | str | None = None):
        self.data_dir = Path(data_dir or settings.DATA_DIR)
        self._cache: dict[str, pd.DataFrame | None] = {}

    def load(self, filename: str) -> pd.DataFrame | None:
        if filename not in self._cache:
            path = self.data_dir / filename
            self._cache[filename] = pd.read_csv(path) if path.exists() and path.stat().st_size else None
        value = self._cache[filename]
        return value.copy() if value is not None else None

    def file_timestamp(self, filename: str) -> str | None:
        path = self.data_dir / filename
        if not path.exists():
            return None
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(
            timespec="seconds"
        )

    def freshness_hours(self, filename: str) -> float | None:
        path = self.data_dir / filename
        if not path.exists():
            return None
        modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - modified).total_seconds() / 3600

    def slate(self) -> pd.DataFrame | None:
        return self.load("today_matchups.csv")

    def anchors(self) -> dict[str, float]:
        anchors = {
            "home_winp": settings.HOME_BASE_WINP,
            "away_winp": settings.AWAY_BASE_WINP,
            "league_runs": settings.LEAGUE_RUNS_PER_TEAM,
            "total_sd": settings.TOTAL_RUNS_SD,
            "team_sd": settings.TEAM_RUNS_SD,
            "margin_sd": settings.MARGIN_SD,
            "blown_save": 0.172,
        }
        games = self.load("game_results.csv")
        if games is None or games.empty:
            return anchors
        try:
            home = games[games["home_away"] == "home"]
            if home.empty:
                return anchors
            anchors["home_winp"] = round(float(home["result"].eq("W").mean()), 4)
            away = games[games["home_away"] == "away"]
            anchors["away_winp"] = round(float(away["result"].eq("W").mean()), 4)
            anchors["league_runs"] = round(float(games["team_runs"].mean()), 3)
            total = home["team_runs"] + home["opp_runs"]
            anchors["total_sd"] = round(float(total.std()), 3)
            anchors["team_sd"] = round(float(games["team_runs"].std()), 3)
            anchors["margin_sd"] = round(
                float((home["team_runs"] - home["opp_runs"]).std()), 3
            )
        except (KeyError, TypeError, ValueError):
            return anchors
        return {
            key: value
            for key, value in anchors.items()
            if not isinstance(value, float) or math.isfinite(value)
        }

    def _team_profiles(self) -> tuple[dict[str, pd.Series], float]:
        profiles = self.load("team_profiles.csv")
        if profiles is None or "team" not in profiles.columns:
            return {}, settings.LEAGUE_BULLPEN_ERA
        profiles["team"] = profiles["team"].astype(str).str.upper().str.strip()
        index = {str(row["team"]): row for _, row in profiles.iterrows()}
        eras = pd.to_numeric(profiles.get("bullpen_era"), errors="coerce")
        league_pen = float(eras.mean()) if eras.notna().any() else settings.LEAGUE_BULLPEN_ERA
        return index, league_pen

    @staticmethod
    def _context(row: pd.Series | None, venue: str, opposing_hand: str) -> TeamContext:
        if row is None:
            return TeamContext()
        suffix = "lhp" if opposing_hand == "L" else "rhp"
        return TeamContext(
            osi=_number(row.get("osi")),
            abq=_number(row.get("abq")),
            rcv=_number(row.get("rcv")),
            obr=_number(row.get("obr")),
            pals=_number(row.get("pals")),
            proj_osi=_number(row.get("proj_osi")),
            osi_l7=_number(row.get("osi_l7")),
            osi_l14=_number(row.get("osi_l14")),
            woba=_number(row.get(f"{venue}_woba")),
            platoon_osi=_number(row.get(f"osi_vs_{suffix}")),
            bullpen_era=_number(row.get("bullpen_era")),
            bullpen_high_lev_era=_number(row.get("bullpen_high_lev_era")),
            avg_pitching_score=_number(row.get("avg_pitching_score")),
            window_direction=str(row.get("window_direction") or "").strip() or None,
        )

    @staticmethod
    def _pen_factor(row: pd.Series | None, league_pen: float) -> float:
        if row is None or league_pen <= 0:
            return 1.0
        era = _number(row.get("bullpen_era"))
        if era is None:
            return 1.0
        factor = era / league_pen
        ir = _number(row.get("bullpen_ir_scored_pct"))
        if ir is not None:
            factor *= 1 + settings.BULLPEN_IR_SENSITIVITY * (ir - 28.0)
        return clip(factor, *settings.PITCH_FACTOR_CLIP)

    def load_game(self, away: str, home: str) -> GameData:
        away, home = away.upper().strip(), home.upper().strip()
        slate = self.slate()
        if slate is None:
            raise FileNotFoundError(
                f"{self.data_dir / 'today_matchups.csv'} is missing; run the MLBMA refresh"
            )
        slate["Away"] = slate["Away"].astype(str).str.upper().str.strip()
        slate["Home"] = slate["Home"].astype(str).str.upper().str.strip()
        selected = slate[(slate["Away"] == away) & (slate["Home"] == home)]
        if selected.empty:
            raise ValueError(f"{away}@{home} is not on the loaded slate")
        game = selected.iloc[0]
        game_date = str(game.get("Slate_Date") or dt.date.today().isoformat())
        game_number = int(_number(game.get("Game_Number")) or 1)
        game_pk = int(
            _number(game.get("Game_PK"))
            or canonical_game_pk(game_date, away, home, game_number)
        )

        profiles, league_pen = self._team_profiles()
        away_profile, home_profile = profiles.get(away), profiles.get(home)
        away_hand = str(game.get("Away_Hand") or "R").upper()[:1]
        home_hand = str(game.get("Home_Hand") or "R").upper()[:1]

        weather = {}
        weather_frame = self.load("today_weather.csv")
        if weather_frame is not None and "home_team" in weather_frame.columns:
            weather_frame["home_team"] = (
                weather_frame["home_team"].astype(str).str.upper().str.strip()
            )
            row = weather_frame[weather_frame["home_team"] == home]
            if not row.empty:
                current = row.iloc[0]
                weather = {
                    "temp_f": _number(current.get("temperature_f")),
                    "wind_mph": _number(current.get("wind_speed_mph")),
                    "wind_dir": str(current.get("wind_direction") or ""),
                    "conditions": str(current.get("conditions") or ""),
                    "dome": bool(current.get("is_dome", False)),
                }

        return GameData(
            game_pk=game_pk,
            game_date=game_date,
            start_time=str(game.get("Time") or ""),
            away=away,
            home=home,
            away_sp=str(game.get("Away_SP") or "TBD"),
            home_sp=str(game.get("Home_SP") or "TBD"),
            away_hand=away_hand,
            home_hand=home_hand,
            away_osi=_number(game.get("Away_OSI")),
            home_osi=_number(game.get("Home_OSI")),
            away_fip=_number(game.get("Away_FIP")),
            home_fip=_number(game.get("Home_FIP")),
            away_hr9=_number(game.get("Away_HR9")),
            home_hr9=_number(game.get("Home_HR9")),
            away_k=_percent(game.get("Away_K%")),
            home_k=_percent(game.get("Home_K%")),
            park_factor=settings.PARK_FACTORS.get(home, 1.0),
            weather=weather,
            away_pen_factor=self._pen_factor(away_profile, league_pen),
            home_pen_factor=self._pen_factor(home_profile, league_pen),
            away_context=self._context(away_profile, "away", home_hand),
            home_context=self._context(home_profile, "home", away_hand),
            source_updated_at=self.file_timestamp("today_matchups.csv"),
        )
