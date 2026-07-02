"""Seed teams and the current slate into the unified warehouse."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from mlbmodel import settings
from mlbmodel.baseball.repository import canonical_game_pk
from mlbmodel.storage.supabase import SupabaseWriter

ET = ZoneInfo("America/New_York")


def scheduled_start(game_date: str, time_text: str) -> str | None:
    value = str(time_text or "").replace("ET", "").strip()
    try:
        parsed = dt.datetime.strptime(value, "%I:%M %p")
        year, month, day = (int(part) for part in game_date.split("-"))
        return dt.datetime(
            year, month, day, parsed.hour, parsed.minute, tzinfo=ET
        ).isoformat()
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(settings.DATA_DIR))
    args = parser.parse_args()
    data_dir = Path(args.data_dir)

    profiles = pd.read_csv(data_dir / "team_profiles.csv")
    teams = sorted(profiles["team"].astype(str).str.upper().str.strip().unique())
    team_rows = [
        {"team_id": index + 1, "team_abbr": team, "team_name": team}
        for index, team in enumerate(teams)
    ]

    slate = pd.read_csv(data_dir / "today_matchups.csv")
    game_rows = []
    for _, row in slate.iterrows():
        away = str(row["Away"]).upper().strip()
        home = str(row["Home"]).upper().strip()
        game_date = str(row.get("Slate_Date") or dt.date.today().isoformat())
        raw_game_number = row.get("Game_Number")
        game_number = (
            1 if raw_game_number is None or pd.isna(raw_game_number)
            else int(raw_game_number)
        )
        raw_pk = row.get("Game_PK")
        game_pk = (
            int(raw_pk)
            if raw_pk is not None and not pd.isna(raw_pk)
            else canonical_game_pk(game_date, away, home, game_number)
        )
        game_rows.append({
            "game_pk": game_pk,
            "season": int(game_date[:4]),
            "game_date": game_date,
            "scheduled_start": scheduled_start(game_date, row.get("Time")),
            "home_team": home,
            "away_team": away,
            "status": "scheduled",
        })

    writer = SupabaseWriter()
    writer.upsert("teams", team_rows, "team_abbr")
    writer.upsert("games", game_rows, "game_pk")
    print(f"upserted teams={len(team_rows)} games={len(game_rows)}")


if __name__ == "__main__":
    main()
