"""Collect point-in-time game context from MLB and Open-Meteo.

The output is deliberately explicit about availability. Pregame lineups and umpires
are not always announced, so absent observations stay neutral instead of being
inferred from a crew rotation or an old lineup.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from mlbmodel import settings

MLB_API = "https://statsapi.mlb.com/api"
WEATHER_API = "https://api.open-meteo.com/v1/forecast"
INJURED_CODES = {"D7", "D10", "D15", "D60", "ILF"}


def _request_json(url: str, timeout: int = 45) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ChaseAnalytics-MLBModel/3.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _haversine_miles(
    latitude_a: float | None,
    longitude_a: float | None,
    latitude_b: float | None,
    longitude_b: float | None,
) -> float | None:
    if None in (latitude_a, longitude_a, latitude_b, longitude_b):
        return None
    radius = 3958.8
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    d_lat = lat_b - lat_a
    d_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _venue(venue_id: int, cache: dict[int, dict]) -> dict:
    if venue_id in cache:
        return cache[venue_id]
    url = (
        f"{MLB_API}/v1/venues/{venue_id}"
        "?hydrate=location,timezone,fieldInfo"
    )
    payload = _request_json(url)
    value = (payload.get("venues") or [{}])[0]
    cache[venue_id] = value
    return value


def _venue_fields(value: dict) -> dict:
    location = value.get("location") or {}
    coordinates = location.get("defaultCoordinates") or {}
    timezone = value.get("timeZone") or {}
    field = value.get("fieldInfo") or {}
    return {
        "venue_id": value.get("id"),
        "venue": value.get("name"),
        "latitude": _number(coordinates.get("latitude")),
        "longitude": _number(coordinates.get("longitude")),
        "field_azimuth": _number(location.get("azimuthAngle")),
        "elevation_ft": _number(location.get("elevation")),
        "timezone": timezone.get("id"),
        "utc_offset": _number(timezone.get("offsetAtGameTime")),
        "roof_type": field.get("roofType"),
        "turf_type": field.get("turfType"),
    }


def _official_lineup(feed: dict, side: str) -> list[dict]:
    team = (((feed.get("liveData") or {}).get("boxscore") or {}).get("teams") or {}).get(
        side, {}
    )
    order = team.get("battingOrder") or []
    players = team.get("players") or {}
    rows = []
    for slot, player_id in enumerate(order, start=1):
        player = players.get(f"ID{player_id}", {})
        person = player.get("person") or {}
        position = player.get("position") or {}
        rows.append(
            {
                "order": slot,
                "player_id": int(player_id),
                "player": person.get("fullName") or "",
                "position": position.get("abbreviation") or "",
            }
        )
    return rows


def _pipeline_lineup(rows: list[dict], team: str) -> list[dict]:
    selected = [
        row
        for row in rows
        if settings.team_abbr(row.get("Team", "")) == team
    ]
    selected.sort(key=lambda row: int(_number(row.get("Bat_Order")) or 99))
    return [
        {
            "order": int(_number(row.get("Bat_Order")) or index),
            "player_id": None,
            "player": str(row.get("Player") or "").strip(),
            "position": str(row.get("Position") or "").strip(),
            "bats": str(row.get("Bats") or "").strip(),
        }
        for index, row in enumerate(selected, start=1)
        if str(row.get("Player") or "").strip()
    ]


def _weather(
    venue: dict,
    game_time: str,
) -> dict:
    roof = str(venue.get("roof_type") or "").lower()
    if roof == "dome":
        return {
            "status": "dome",
            "source": "MLB venue roof",
            "dome": True,
            "run_factor": 1.0,
        }
    latitude = venue.get("latitude")
    longitude = venue.get("longitude")
    start = _iso(game_time)
    if latitude is None or longitude is None or start is None:
        return {"status": "unavailable", "source": "Open-Meteo", "dome": False}
    day = start.date().isoformat()
    hourly_fields = (
        "temperature_2m,relative_humidity_2m,precipitation_probability,"
        "precipitation,pressure_msl,wind_speed_10m,wind_direction_10m,"
        "wind_gusts_10m"
    )
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": hourly_fields,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "start_date": day,
            "end_date": day,
        }
    )
    payload = _request_json(f"{WEATHER_API}?{query}")
    hourly = payload.get("hourly") or {}
    times = [_iso(value) for value in hourly.get("time") or []]
    candidates = [
        (abs((value - start).total_seconds()), index)
        for index, value in enumerate(times)
        if value is not None
    ]
    if not candidates:
        return {"status": "unavailable", "source": "Open-Meteo", "dome": False}
    _, index = min(candidates)

    def at(name: str) -> float | None:
        values = hourly.get(name) or []
        return _number(values[index]) if index < len(values) else None

    wind_speed = at("wind_speed_10m")
    wind_direction = at("wind_direction_10m")
    azimuth = venue.get("field_azimuth")
    wind_out = None
    if None not in (wind_speed, wind_direction, azimuth):
        toward = (wind_direction + 180.0) % 360.0
        wind_out = wind_speed * math.cos(math.radians(toward - azimuth))
    return {
        "status": "forecast",
        "source": "Open-Meteo hourly best-match",
        "forecast_time": (times[index] or start).isoformat(),
        "dome": False,
        "temperature_f": at("temperature_2m"),
        "humidity_pct": at("relative_humidity_2m"),
        "precipitation_probability_pct": at("precipitation_probability"),
        "precipitation_in": at("precipitation"),
        "pressure_hpa": at("pressure_msl"),
        "wind_mph": wind_speed,
        "wind_direction_deg": wind_direction,
        "wind_gust_mph": at("wind_gusts_10m"),
        "wind_out_mph": round(wind_out, 2) if wind_out is not None else None,
    }


def _injuries(team_id: int) -> list[dict]:
    url = (
        f"{MLB_API}/v1/teams/{team_id}/roster"
        "?rosterType=40Man&hydrate=person"
    )
    payload = _request_json(url)
    rows = []
    for entry in payload.get("roster") or []:
        status = entry.get("status") or {}
        code = str(status.get("code") or "")
        if code not in INJURED_CODES:
            continue
        person = entry.get("person") or {}
        position = entry.get("position") or {}
        rows.append(
            {
                "player_id": person.get("id"),
                "player": person.get("fullName"),
                "position": position.get("abbreviation"),
                "status_code": code,
                "status": status.get("description"),
                "injury": entry.get("note"),
            }
        )
    return rows


def _pitcher_profile(player_id: int, season: int) -> dict:
    url = (
        f"{MLB_API}/v1/people/{player_id}/stats"
        f"?stats=season&group=pitching&season={season}"
    )
    payload = _request_json(url)
    stats = (
        (((payload.get("stats") or [{}])[0].get("splits") or [{}])[0]).get("stat")
        or {}
    )
    innings = _number(stats.get("inningsPitched"))
    if innings is not None:
        whole = int(innings)
        partial = round((innings - whole) * 10)
        innings = whole + partial / 3 if partial in (1, 2) else innings
    strikeouts = _number(stats.get("strikeOuts")) or 0.0
    walks = _number(stats.get("baseOnBalls")) or 0.0
    hit_batters = _number(stats.get("hitBatsmen")) or 0.0
    home_runs = _number(stats.get("homeRuns")) or 0.0
    batters = _number(stats.get("battersFaced")) or 0.0
    starts = int(_number(stats.get("gamesStarted")) or 0)
    fip = None
    if innings and innings > 0:
        fip = (
            (13 * home_runs + 3 * (walks + hit_batters) - 2 * strikeouts)
            / innings
            + 3.20
        )
    return {
        "pitcher_id": player_id,
        "starts": starts,
        "ERA": _number(stats.get("era")),
        "FIP": round(fip, 3) if fip is not None else None,
        "xFIP": round(fip, 3) if fip is not None else None,
        "K_pct": round(strikeouts / batters * 100, 2) if batters else None,
        "BB_pct": round(walks / batters * 100, 2) if batters else None,
        "HR9": _number(stats.get("homeRunsPer9")),
        "avg_IP": round(innings / starts, 3) if innings and starts else None,
        "avg_pitches": (
            round((_number(stats.get("numberOfPitches")) or 0) / starts, 1)
            if starts else None
        ),
        "batters_faced": int(batters),
        "innings": round(innings, 3) if innings is not None else None,
        "data_source": "MLB Stats API season fallback",
    }


def _umpire_profiles(slate_date: str) -> tuple[dict[int, dict], dict]:
    end = dt.date.fromisoformat(slate_date) - dt.timedelta(days=1)
    start = max(dt.date(end.year, 3, 15), end - dt.timedelta(days=120))
    query = urllib.parse.urlencode(
        {
            "sportId": 1,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "hydrate": "officials,linescore",
        }
    )
    payload = _request_json(f"{MLB_API}/v1/schedule?{query}")
    samples: dict[int, list[float]] = defaultdict(list)
    names = {}
    all_totals = []
    for date_block in payload.get("dates") or []:
        for game in date_block.get("games") or []:
            linescore = game.get("linescore") or {}
            teams = linescore.get("teams") or {}
            total = _number((teams.get("home") or {}).get("runs"))
            away = _number((teams.get("away") or {}).get("runs"))
            if total is None or away is None:
                continue
            total += away
            plate = next(
                (
                    item.get("official") or {}
                    for item in game.get("officials") or []
                    if item.get("officialType") == "Home Plate"
                ),
                None,
            )
            if not plate or not plate.get("id"):
                continue
            umpire_id = int(plate["id"])
            names[umpire_id] = plate.get("fullName")
            samples[umpire_id].append(total)
            all_totals.append(total)
    league = sum(all_totals) / len(all_totals) if all_totals else 9.0
    prior_games = 30
    profiles = {}
    for umpire_id, totals in samples.items():
        raw = sum(totals) / len(totals)
        adjusted = (sum(totals) + league * prior_games) / (len(totals) + prior_games)
        profiles[umpire_id] = {
            "umpire_id": umpire_id,
            "umpire": names.get(umpire_id),
            "games": len(totals),
            "raw_runs_per_game": round(raw, 2),
            "adjusted_runs_per_game": round(adjusted, 2),
            "run_factor": round(max(0.96, min(1.04, adjusted / league)), 4),
        }
    return profiles, {
        "games": len(all_totals),
        "league_runs_per_game": round(league, 3),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "prior_games": prior_games,
    }


def _schedule_window(slate_date: str) -> list[dict]:
    day = dt.date.fromisoformat(slate_date)
    query = urllib.parse.urlencode(
        {
            "sportId": 1,
            "startDate": (day - dt.timedelta(days=8)).isoformat(),
            "endDate": slate_date,
            "hydrate": "team",
        }
    )
    payload = _request_json(f"{MLB_API}/v1/schedule?{query}")
    return [
        game
        for date_block in payload.get("dates") or []
        for game in date_block.get("games") or []
    ]


def _travel(
    game: dict,
    team_id: int,
    current_venue: dict,
    history: list[dict],
    venue_cache: dict[int, dict],
) -> dict:
    current_start = _iso(game.get("gameDate"))
    previous = []
    played_dates = set()
    for old_game in history:
        old_start = _iso(old_game.get("gameDate"))
        team_ids = {
            int(side["team"]["id"])
            for side in (old_game.get("teams") or {}).values()
            if (side.get("team") or {}).get("id")
        }
        if (
            team_id not in team_ids
            or old_start is None
            or current_start is None
            or old_start >= current_start
        ):
            continue
        previous.append(old_game)
        played_dates.add(old_start.date())
    previous.sort(key=lambda item: _iso(item.get("gameDate")) or dt.datetime.min.replace(
        tzinfo=dt.timezone.utc
    ))
    if not previous:
        return {
            "status": "no_recent_game",
            "rest_hours": None,
            "travel_miles": 0.0,
            "timezone_shift_hours": 0.0,
            "games_last_7_days": 0,
        }
    last = previous[-1]
    last_start = _iso(last.get("gameDate"))
    last_venue_id = int((last.get("venue") or {}).get("id") or 0)
    previous_venue = (
        _venue_fields(_venue(last_venue_id, venue_cache))
        if last_venue_id
        else {}
    )
    miles = _haversine_miles(
        previous_venue.get("latitude"),
        previous_venue.get("longitude"),
        current_venue.get("latitude"),
        current_venue.get("longitude"),
    )
    previous_offset = previous_venue.get("utc_offset")
    current_offset = current_venue.get("utc_offset")
    shift = (
        abs(current_offset - previous_offset)
        if None not in (previous_offset, current_offset)
        else None
    )
    return {
        "status": "available",
        "previous_game_pk": last.get("gamePk"),
        "previous_game_time": last.get("gameDate"),
        "previous_venue": previous_venue.get("venue"),
        "rest_hours": round((current_start - last_start).total_seconds() / 3600, 1),
        "travel_miles": round(miles, 1) if miles is not None else None,
        "timezone_shift_hours": shift,
        "games_last_7_days": len(played_dates),
    }


def collect(
    out: Path,
    slate_date: str,
    games: list[dict],
    pipeline_lineups: list[dict] | None = None,
) -> dict:
    """Write ``live_context.json`` and return its payload."""
    pipeline_lineups = pipeline_lineups or []
    fetched_at = dt.datetime.now(dt.timezone.utc)
    venue_cache: dict[int, dict] = {}
    try:
        history = _schedule_window(slate_date)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        history = []
    try:
        umpire_profiles, umpire_meta = _umpire_profiles(slate_date)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        umpire_profiles, umpire_meta = {}, {}

    team_injuries: dict[str, list[dict]] = {}
    probable_profiles: dict[int, dict] = {}
    for game in games:
        for side in ("away", "home"):
            team = game["teams"][side]["team"]
            abbr = settings.team_abbr(team.get("name", ""))
            if abbr in team_injuries:
                continue
            try:
                team_injuries[abbr] = _injuries(int(team["id"]))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                team_injuries[abbr] = []
        for side in ("away", "home"):
            pitcher = game["teams"][side].get("probablePitcher") or {}
            player_id = int(pitcher.get("id") or 0)
            if not player_id or player_id in probable_profiles:
                continue
            try:
                probable_profiles[player_id] = _pitcher_profile(
                    player_id,
                    dt.date.fromisoformat(slate_date).year,
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                probable_profiles[player_id] = {"pitcher_id": player_id}

    context_games = {}
    for game in games:
        game_pk = int(game["gamePk"])
        away_team = game["teams"]["away"]["team"]
        home_team = game["teams"]["home"]["team"]
        away = settings.team_abbr(away_team.get("name", ""))
        home = settings.team_abbr(home_team.get("name", ""))
        try:
            feed = _request_json(f"{MLB_API}/v1.1/game/{game_pk}/feed/live")
        except (OSError, ValueError, json.JSONDecodeError):
            feed = {}
        feed_venue = (feed.get("gameData") or {}).get("venue") or {}
        venue_id = int((game.get("venue") or {}).get("id") or feed_venue.get("id") or 0)
        try:
            full_venue = feed_venue if feed_venue.get("location") else _venue(
                venue_id, venue_cache
            )
            venue = _venue_fields(full_venue)
            if venue_id:
                venue_cache[venue_id] = full_venue
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            venue = {"venue_id": venue_id, "venue": (game.get("venue") or {}).get("name")}
        official_away = _official_lineup(feed, "away")
        official_home = _official_lineup(feed, "home")
        projected_away = _pipeline_lineup(pipeline_lineups, away)
        projected_home = _pipeline_lineup(pipeline_lineups, home)
        lineups = {
            "away": {
                "status": "confirmed" if len(official_away) >= 9 else (
                    "projected" if len(projected_away) >= 9 else "unavailable"
                ),
                "source": "MLB live feed" if len(official_away) >= 9 else (
                    "MLBMA Today_Lineups" if len(projected_away) >= 9 else None
                ),
                "players": official_away if len(official_away) >= 9 else projected_away,
            },
            "home": {
                "status": "confirmed" if len(official_home) >= 9 else (
                    "projected" if len(projected_home) >= 9 else "unavailable"
                ),
                "source": "MLB live feed" if len(official_home) >= 9 else (
                    "MLBMA Today_Lineups" if len(projected_home) >= 9 else None
                ),
                "players": official_home if len(official_home) >= 9 else projected_home,
            },
        }
        officials = (
            ((feed.get("liveData") or {}).get("boxscore") or {}).get("officials") or []
        )
        plate = next(
            (
                item.get("official") or {}
                for item in officials
                if item.get("officialType") == "Home Plate"
            ),
            {},
        )
        plate_id = int(plate.get("id") or 0)
        umpire = {
            "status": "announced" if plate_id else "unannounced",
            "umpire_id": plate_id or None,
            "umpire": plate.get("fullName"),
            "profile": umpire_profiles.get(plate_id),
        }
        try:
            weather = _weather(venue, game.get("gameDate", ""))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            weather = {"status": "unavailable", "source": "Open-Meteo"}
        travel = {}
        for side, team in (("away", away_team), ("home", home_team)):
            try:
                travel[side] = _travel(
                    game,
                    int(team["id"]),
                    venue,
                    history,
                    venue_cache,
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                travel[side] = {"status": "unavailable"}

        probable_pitchers = {}
        for side in ("away", "home"):
            probable = game["teams"][side].get("probablePitcher") or {}
            player_id = int(probable.get("id") or 0)
            probable_pitchers[side] = {
                "pitcher_id": player_id or None,
                "pitcher": probable.get("fullName"),
                "profile": probable_profiles.get(player_id, {}),
            }

        context_games[str(game_pk)] = {
            "game_pk": game_pk,
            "game_date": game.get("officialDate") or slate_date,
            "game_time": game.get("gameDate"),
            "away": away,
            "home": home,
            "venue": venue,
            "lineups": lineups,
            "weather": weather,
            "umpire": umpire,
            "injuries": {
                "away": team_injuries.get(away, []),
                "home": team_injuries.get(home, []),
            },
            "travel": travel,
            "probable_pitchers": probable_pitchers,
        }

    payload = {
        "slate_date": slate_date,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "sources": {
            "schedule_lineups_injuries_umpires_venues": "MLB Stats API",
            "weather": "Open-Meteo hourly best-match",
        },
        "umpire_profile_metadata": umpire_meta,
        "games": context_games,
    }
    destination = out / "live_context.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
