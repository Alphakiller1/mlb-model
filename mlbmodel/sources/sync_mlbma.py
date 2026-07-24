#!/usr/bin/env python3
"""Materialize one deployable model dataset from the authoritative MLBMA sources."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

from mlbmodel import settings
from mlbmodel.sources.build_today_matchups import (
    MATCHUP_COLUMNS,
    build_rows,
    fetch_schedule,
    write_rows,
)
from mlbmodel.sources.hub_to_csv import write_csv
from mlbmodel.sources.live_context import collect as collect_live_context

ET = ZoneInfo("America/New_York")
HUB_DATASETS = {
    "Team_Profiles": "team_profiles.csv",
    "SP_Profiles": "sp_profiles.csv",
    "SP_L14": "sp_l14.csv",
    "SP_Game_Log": "sp_game_log.csv",
    "SP_Metric_Splits": "sp_metric_splits.csv",
    "Batter_Profiles": "batter_profiles.csv",
    "Batter_Splits_RHP": "batter_splits_rhp.csv",
    "Batter_Splits_LHP": "batter_splits_lhp.csv",
    "Bullpen_Unit": "bullpen_unit.csv",
    "Reliever_Log": "reliever_log.csv",
    "Player_Registry": "player_registry.csv",
    "Pitch_Mix_Pitcher": "pitch_mix_pitcher.csv",
    "Pitch_Mix_Pitcher_L14": "pitch_mix_pitcher_l14.csv",
    "Pitch_Mix_Batter": "pitch_mix_batter.csv",
    "Pitch_Mix_Batter_L14": "pitch_mix_batter_l14.csv",
    "Pitch_Mix_Team_Batting": "pitch_mix_team_batting.csv",
    "Pitch_Mix_Team_Batting_L14": "pitch_mix_team_batting_l14.csv",
    "Team_L10_SP_Hand": "team_l10_sp_hand.csv",
    "Signals_Today": "signals_today.csv",
    "Signals_Convergence": "signals_convergence.csv",
}
IDENTITY_COLUMNS = {"Game_PK", "MLB_Game_PK", "Game_Number", "Slate_Date"}
# Handedness is resolved from the authoritative MLB Stats API people record in
# build_rows; the MLBMA pipeline's own hand column is unreliable (lefties mislabeled R),
# so never let the pipeline merge clobber the schedule-sourced hand.
SCHEDULE_AUTHORITATIVE_COLUMNS = {"Away_Hand", "Home_Hand"}


EVENING_ROLLOVER_HOUR = 17  # 5 PM ET — roll the board to the next slate for pregame.


def eastern_date(now: dt.datetime | None = None) -> str:
    current = now or dt.datetime.now(dt.timezone.utc)
    return current.astimezone(ET).date().isoformat()


def resolve_slate_date(
    explicit: str | None = None,
    *,
    metadata: dict[str, str] | None = None,
    now: dt.datetime | None = None,
) -> str:
    """Pick the model slate date: explicit > hub future slate > evening rollover > hub today > today."""
    if explicit:
        return str(explicit)[:10]
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    today = current.date().isoformat()
    tomorrow = (current.date() + dt.timedelta(days=1)).isoformat()
    pipeline_date = str((metadata or {}).get("Slate_Date_ET") or "")[:10]
    if pipeline_date and pipeline_date > today:
        return pipeline_date
    if current.hour >= EVENING_ROLLOVER_HOUR:
        return tomorrow
    if pipeline_date == today:
        return pipeline_date
    return today


def _request(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def fetch_sheet_matrix(tab: str) -> list[list[str]]:
    query = urllib.parse.urlencode({
        "tqx": "out:csv",
        "sheet": tab,
        "_sync": str(int(dt.datetime.now().timestamp())),
    })
    url = (
        f"https://docs.google.com/spreadsheets/d/{settings.MLBMA_SHEET_ID}"
        f"/gviz/tq?{query}"
    )
    text = _request(url).decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(text)))


def fetch_sheet_rows(tab: str) -> list[dict]:
    matrix = fetch_sheet_matrix(tab)
    if not matrix:
        return []
    headers = [column.strip() for column in matrix[0]]
    return [
        {header: (row[index].strip() if index < len(row) else "")
         for index, header in enumerate(headers)}
        for row in matrix[1:]
        if any(value.strip() for value in row)
    ]


def fetch_hub_datasets() -> list[dict]:
    names = ",".join(HUB_DATASETS)
    path = (
        f"/rest/v1/hub_dataset?name=in.({names})"
        "&select=name,rows,row_count,updated_at"
    )
    headers = {
        "apikey": settings.MLBMA_HUB_KEY,
        "Authorization": f"Bearer {settings.MLBMA_HUB_KEY}",
    }
    return json.loads(
        _request(f"{settings.MLBMA_HUB_URL}{path}", headers=headers).decode()
    )


def materialize_hub(out: Path, datasets: list[dict]) -> dict[str, str]:
    by_name = {str(dataset.get("name")): dataset for dataset in datasets}
    missing = sorted(set(HUB_DATASETS) - set(by_name))
    if missing:
        raise RuntimeError(f"MLBMA hub is missing required datasets: {', '.join(missing)}")
    updated = {}
    for name, filename in HUB_DATASETS.items():
        dataset = by_name[name]
        rows = dataset.get("rows")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"MLBMA hub dataset {name} is empty")
        write_csv(rows, out / filename)
        updated[name] = str(dataset.get("updated_at") or "")
    return updated


def pipeline_metadata(matrix: list[list[str]]) -> dict[str, str]:
    metadata = {}
    for row in matrix:
        if len(row) >= 2 and row[0].strip():
            metadata[row[0].strip()] = row[1].strip()
    return metadata


def _pair(row: dict) -> str:
    return f"{str(row.get('Away') or '').upper().strip()}@{str(row.get('Home') or '').upper().strip()}"


def matchup_keys(rows: list[dict]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    keys = []
    for row in rows:
        pair = _pair(row)
        counts[pair] += 1
        suffix = f"#{counts[pair]}" if counts[pair] > 1 else ""
        keys.append(f"{pair}{suffix}")
    return keys


def current_pipeline_rows(rows: list[dict], slate_date: str) -> list[dict]:
    return [
        row for row in rows
        if str(row.get("Slate_Date") or "")[:10] == slate_date
    ]


def current_lineup_rows(rows: list[dict], slate_date: str) -> list[dict]:
    return [
        row for row in rows
        if str(row.get("Slate_Date") or "")[:10] == slate_date
    ]


def merge_pipeline_slate(
    schedule_rows: list[dict],
    pipeline_rows: list[dict],
) -> tuple[list[dict], bool]:
    """Use pipeline values only when its game multiset exactly matches the live schedule."""
    if Counter(map(_pair, schedule_rows)) != Counter(map(_pair, pipeline_rows)):
        return schedule_rows, False
    queues: dict[str, list[dict]] = defaultdict(list)
    for row in pipeline_rows:
        queues[_pair(row)].append(row)

    merged_rows = []
    for schedule_row in schedule_rows:
        pipeline_row = queues[_pair(schedule_row)].pop(0)
        merged = dict(schedule_row)
        for column in MATCHUP_COLUMNS:
            value = pipeline_row.get(column)
            if (
                column not in IDENTITY_COLUMNS
                and column not in SCHEDULE_AUTHORITATIVE_COLUMNS
                and value not in (None, "", "--")
            ):
                merged[column] = value
        merged_rows.append(merged)
    return merged_rows, True


def _pipeline_updated_at(metadata: dict[str, str]) -> str | None:
    value = metadata.get("Last Updated")
    if not value:
        return None
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        return parsed.isoformat()
    except ValueError:
        return value


def sync(out: Path, slate_date: str | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    fetched_at = dt.datetime.now(dt.timezone.utc)
    metadata = pipeline_metadata(fetch_sheet_matrix("Last_Updated"))
    slate_date = resolve_slate_date(slate_date, metadata=metadata)

    hub_updated = materialize_hub(out, fetch_hub_datasets())
    games = fetch_schedule(slate_date)
    schedule_rows = build_rows(out, slate_date, games)
    all_pipeline_rows = fetch_sheet_rows("Today_Matchups")
    all_lineup_rows = fetch_sheet_rows("Today_Lineups")
    pipeline_rows = current_pipeline_rows(all_pipeline_rows, slate_date)
    pipeline_slate_date = metadata.get("Slate_Date_ET")
    merged_rows, game_set_exact = merge_pipeline_slate(schedule_rows, pipeline_rows)
    exact = game_set_exact and pipeline_slate_date == slate_date
    rows = merged_rows if exact else schedule_rows
    pipeline_lineups = current_lineup_rows(all_lineup_rows, slate_date) if exact else []
    source = "mlbma_pipeline" if exact else "mlb_live_schedule_fallback"
    if exact:
        message = (
            f"Exact MLBMA pipeline slate: {len(rows)} games for {slate_date}."
        )
    else:
        message = (
            f"MLBMA pipeline slate is {pipeline_slate_date or 'unavailable'}; "
            f"using Chase Analytics' live MLB schedule fallback for {slate_date}."
        )

    write_rows(rows, out / "today_matchups.csv")
    os.utime(out / "today_matchups.csv", (fetched_at.timestamp(), fetched_at.timestamp()))
    context_error = None
    try:
        live_context = collect_live_context(
            out,
            slate_date,
            games,
            pipeline_lineups=pipeline_lineups,
        )
    except Exception as exc:  # context is additive; the slate must still deploy
        live_context = {}
        context_error = f"{type(exc).__name__}: {exc}"
    keys = matchup_keys(rows)
    digest = hashlib.sha256(
        json.dumps({
            "slate_date": slate_date,
            "keys": keys,
            "source": source,
            "pipeline_updated_at": metadata.get("Last Updated"),
            "hub_updated": hub_updated,
        }, sort_keys=True).encode()
    ).hexdigest()[:16]
    manifest = {
        "sync_id": digest,
        "status": "exact" if exact else "fallback",
        "source": source,
        "message": message,
        "slate_date": slate_date,
        "game_count": len(rows),
        "matchup_keys": keys,
        "pipeline_slate_date": pipeline_slate_date,
        "pipeline_updated_at": _pipeline_updated_at(metadata),
        "hub_updated_at": hub_updated,
        "live_context_fetched_at": live_context.get("fetched_at"),
        "live_context_games": len(live_context.get("games") or {}),
        "live_context_error": context_error,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
    }
    (out / "mlbma_sync.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize deployable inputs with the authoritative MLBMA run."
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--date", help="ET slate date (defaults to today)")
    args = parser.parse_args()
    manifest = sync(Path(args.out), args.date)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
