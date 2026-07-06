"""Point-in-time MLBMA CSV access with explicit freshness and fallbacks."""
from __future__ import annotations

import datetime as dt
import json
import math
import zlib
from pathlib import Path

import pandas as pd

from mlbmodel import settings
from mlbmodel.baseball.context import context_coverage
from mlbmodel.baseball.features import (
    bullpen_features,
    injury_features,
    lineup_features,
    normalize_name,
    starter_features,
)
from mlbmodel.baseball.arsenal import attach_arsenal
from mlbmodel.baseball.metrics import (
    bullpen_allowed_adjustment,
    bullpen_platoon_adjustment,
    opponent_offense_strength,
    pitcher_allowed_skill_adjustment,
    sp_split_skill_adjustment,
)
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

    def sync_manifest(self) -> dict:
        path = self.data_dir / "mlbma_sync.json"
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def live_context(self) -> dict:
        path = self.data_dir / "live_context.json"
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

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
            abq_l7=_number(row.get("abq_l7")),
            abq_l14=_number(row.get("abq_l14")),
            rcv_l7=_number(row.get("rcv_l7")),
            rcv_l14=_number(row.get("rcv_l14")),
            oor=_number(row.get("oor")),
            woba=_number(row.get(f"{venue}_woba")),
            platoon_osi=_number(row.get(f"osi_vs_{suffix}")),
            abq_vs_lhp=_number(row.get("abq_vs_lhp")),
            abq_vs_rhp=_number(row.get("abq_vs_rhp")),
            rcv_vs_lhp=_number(row.get("rcv_vs_lhp")),
            rcv_vs_rhp=_number(row.get("rcv_vs_rhp")),
            obr_vs_lhp=_number(row.get("obr_vs_lhp")),
            obr_vs_rhp=_number(row.get("obr_vs_rhp")),
            bullpen_era=_number(row.get("bullpen_era")),
            bullpen_high_lev_era=_number(row.get("bullpen_high_lev_era")),
            bullpen_osi_allowed=_number(row.get("bullpen_osi_allowed")),
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

    def load_game(self, away: str, home: str, *, pitcher_rows: list[dict] | None = None) -> GameData:
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
        mlb_game_pk = int(_number(game.get("MLB_Game_PK")) or 0) or None
        context_payload = self.live_context()
        context_games = context_payload.get("games") or {}
        live_context = context_games.get(str(mlb_game_pk), {}) if mlb_game_pk else {}
        if not live_context:
            live_context = next(
                (
                    value
                    for value in context_games.values()
                    if value.get("away") == away and value.get("home") == home
                ),
                {},
            )

        profiles, league_pen = self._team_profiles()
        away_profile, home_profile = profiles.get(away), profiles.get(home)
        away_hand = str(game.get("Away_Hand") or "R").upper()[:1]
        home_hand = str(game.get("Home_Hand") or "R").upper()[:1]

        weather = {}
        live_weather = live_context.get("weather") or {}
        if live_weather:
            weather = {
                "status": live_weather.get("status"),
                "source": live_weather.get("source"),
                "temp_f": _number(live_weather.get("temperature_f")),
                "humidity_pct": _number(live_weather.get("humidity_pct")),
                "precipitation_probability_pct": _number(
                    live_weather.get("precipitation_probability_pct")
                ),
                "pressure_hpa": _number(live_weather.get("pressure_hpa")),
                "wind_mph": _number(live_weather.get("wind_mph")),
                "wind_out_mph": _number(live_weather.get("wind_out_mph")),
                "wind_dir": str(live_weather.get("wind_direction_deg") or ""),
                "conditions": str(live_weather.get("status") or ""),
                "dome": bool(live_weather.get("dome", False)),
            }
        weather_frame = self.load("today_weather.csv")
        if not weather and weather_frame is not None and "home_team" in weather_frame.columns:
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

        sp_profiles = self.load("sp_profiles.csv")
        sp_rows = sp_profiles.to_dict("records") if sp_profiles is not None else []
        sp_by_name: dict[str, list[dict]] = {}
        for row in sp_rows:
            sp_by_name.setdefault(normalize_name(row.get("pitcher_name")), []).append(row)
        recent_frame = self.load("sp_l14.csv")
        recent_rows = recent_frame.to_dict("records") if recent_frame is not None else []
        recent_by_name: dict[str, list[dict]] = {}
        for row in recent_rows:
            recent_by_name.setdefault(normalize_name(row.get("Name")), []).append(row)
        game_log_frame = self.load("sp_game_log.csv")
        game_logs = game_log_frame.to_dict("records") if game_log_frame is not None else []
        game_logs_by_name: dict[str, list[dict]] = {}
        for row in game_logs:
            game_logs_by_name.setdefault(
                normalize_name(row.get("pitcher_name")), []
            ).append(row)
        for rows in game_logs_by_name.values():
            rows.sort(key=lambda value: str(value.get("date") or ""))

        def pitcher_inputs(name: str, team: str, side: str) -> tuple[dict, dict | None]:
            candidates = sp_by_name.get(normalize_name(name), [])
            team_candidates = [
                row for row in candidates
                if str(row.get("pitcher_team") or "").upper() == team
            ]
            profile = (team_candidates or candidates or [None])[0]
            fallback_profile = (
                ((live_context.get("probable_pitchers") or {}).get(side) or {})
                .get("profile")
                or None
            )
            profile = profile or fallback_profile
            recent_candidates = recent_by_name.get(normalize_name(name), [])
            recent = (
                max(
                    recent_candidates,
                    key=lambda value: _number(value.get("TBF")) or 0,
                )
                if recent_candidates
                else None
            )
            features = starter_features(
                profile,
                recent,
                game_logs_by_name.get(normalize_name(name), []),
            )
            if profile is fallback_profile and fallback_profile:
                features["source"] = "MLB Stats API season fallback"
            return features, profile

        bullpen_frame = self.load("bullpen_unit.csv")
        bullpen_rows = bullpen_frame.to_dict("records") if bullpen_frame is not None else []
        bullpen_index = {
            str(row.get("team") or "").upper(): row for row in bullpen_rows
        }
        reliever_frame = self.load("reliever_log.csv")
        reliever_rows = reliever_frame.to_dict("records") if reliever_frame is not None else []
        relievers_by_team: dict[str, list[dict]] = {}
        for row in reliever_rows:
            relievers_by_team.setdefault(
                str(row.get("pitcher_team") or "").upper(), []
            ).append(row)
        split_frame = self.load("sp_metric_splits.csv")
        split_rows = split_frame.to_dict("records") if split_frame is not None else []

        away_starter, away_sp_profile = pitcher_inputs(
            str(game.get("Away_SP") or ""), away, "away"
        )
        home_starter, home_sp_profile = pitcher_inputs(
            str(game.get("Home_SP") or ""), home, "home"
        )

        home_offense_strength = opponent_offense_strength(
            self._context(home_profile, "home", away_hand),
            _number(game.get("Home_OSI")),
        )
        away_offense_strength = opponent_offense_strength(
            self._context(away_profile, "away", home_hand),
            _number(game.get("Away_OSI")),
        )
        away_starter["skill_multiplier"] = round(
            pitcher_allowed_skill_adjustment(away_sp_profile, home_offense_strength)
            * sp_split_skill_adjustment(away_sp_profile, split_rows, away_hand),
            4,
        )
        home_starter["skill_multiplier"] = round(
            pitcher_allowed_skill_adjustment(home_sp_profile, away_offense_strength)
            * sp_split_skill_adjustment(home_sp_profile, split_rows, home_hand),
            4,
        )

        away_bullpen = bullpen_features(
            bullpen_index.get(away),
            relievers_by_team.get(away, []),
            venue="away",
            game_date=game_date,
        )
        home_bullpen = bullpen_features(
            bullpen_index.get(home),
            relievers_by_team.get(home, []),
            venue="home",
            game_date=game_date,
        )
        away_pen_row = bullpen_index.get(away)
        home_pen_row = bullpen_index.get(home)
        away_ctx = self._context(away_profile, "away", home_hand)
        home_ctx = self._context(home_profile, "home", away_hand)
        away_bullpen["pen_multiplier"] = round(
            bullpen_platoon_adjustment(away_pen_row, home_hand)
            * bullpen_allowed_adjustment(
                away_ctx.bullpen_osi_allowed, home_offense_strength
            ),
            4,
        )
        home_bullpen["pen_multiplier"] = round(
            bullpen_platoon_adjustment(home_pen_row, away_hand)
            * bullpen_allowed_adjustment(
                home_ctx.bullpen_osi_allowed, away_offense_strength
            ),
            4,
        )

        batter_frame = self.load("batter_profiles.csv")
        batter_rows = batter_frame.to_dict("records") if batter_frame is not None else []
        live_lineups = live_context.get("lineups") or {}
        live_injuries = live_context.get("injuries") or {}
        away_lineup = lineup_features(
            live_lineups.get("away"),
            batter_rows,
            team=away,
            opposing_hand=home_hand,
        )
        home_lineup = lineup_features(
            live_lineups.get("home"),
            batter_rows,
            team=home,
            opposing_hand=away_hand,
        )
        away_injuries = injury_features(
            live_injuries.get("away") or [],
            batter_rows,
            lineup_status=away_lineup["status"],
        )
        home_injuries = injury_features(
            live_injuries.get("home") or [],
            batter_rows,
            lineup_status=home_lineup["status"],
        )
        coverage, missing = context_coverage(live_context)

        gd = GameData(
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
            mlb_game_pk=mlb_game_pk,
            live_context=live_context,
            away_starter_features=away_starter,
            home_starter_features=home_starter,
            away_bullpen_features=away_bullpen,
            home_bullpen_features=home_bullpen,
            away_lineup_features=away_lineup,
            home_lineup_features=home_lineup,
            away_injury_features=away_injuries,
            home_injury_features=home_injuries,
            away_starter_profile=dict(away_sp_profile or {}),
            home_starter_profile=dict(home_sp_profile or {}),
            context_coverage_pct=coverage,
            missing_context=missing,
        )
        if pitcher_rows:
            attach_arsenal(gd, pitcher_rows)
        return gd
