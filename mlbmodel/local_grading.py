"""Portable prediction ledger and grader for MLB model runs.

The hosted warehouse remains useful for portfolio reporting, but an unavailable
credential must not make a model run untraceable.  This ledger records every
game-market projection and pitcher-prop projection locally, then grades it from
the same refreshed game and starter logs used by the model.
"""
from __future__ import annotations

import csv
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


COLUMNS = [
    "prediction_id", "run_id", "recorded_at", "game_date", "game_pk", "kind",
    "market", "selection", "line", "odds", "book", "projection", "player",
    "status", "actual", "won", "void_reason",
]


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _norm(value: object) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def _path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "prediction_ledger.csv"


def _load(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype=str).fillna("").reindex(columns=COLUMNS, fill_value="")


def record_run(data_dir: str | Path, slate_date: str, model_by_pk: dict, pkmap: dict,
               prop_rows: list[dict]) -> int:
    """Append every generated game projection and pitcher prop in one run."""
    path = _path(data_dir)
    frame = _load(path)
    run_id = uuid.uuid4().hex[:12]
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict] = []
    for game_pk, markets in model_by_pk.items():
        for market in markets:
            rows.append({
                "prediction_id": uuid.uuid4().hex, "run_id": run_id,
                "recorded_at": recorded_at, "game_date": slate_date, "game_pk": game_pk,
                "kind": "game", "market": market.get("market", ""),
                "selection": market.get("side", ""), "line": market.get("line", ""),
                "odds": market.get("mkt", ""), "book": market.get("book", ""),
                "projection": market.get("model", ""),
                "player": pkmap.get(game_pk, ""), "status": "pending",
                "actual": "", "won": "", "void_reason": "",
            })
    for prop in prop_rows:
        rows.append({
            "prediction_id": uuid.uuid4().hex, "run_id": run_id,
            "recorded_at": recorded_at, "game_date": slate_date,
            "game_pk": prop.get("game_pk", ""), "kind": "prop",
            "market": prop.get("prop", ""), "selection": prop.get("side", ""),
            "line": prop.get("line", ""), "odds": prop.get("best_odds", ""),
            "book": prop.get("best_book", ""), "projection": prop.get("model_mean", ""),
            "player": prop.get("pitcher", ""), "status": "pending", "actual": "",
            "won": "", "void_reason": "",
        })
    if not rows:
        return 0
    pd.concat([frame, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True).to_csv(path, index=False)
    return len(rows)


def grade_pending(data_dir: str | Path) -> dict[str, int]:
    """Grade pending entries with local final-score and starter-game-log data."""
    path = _path(data_dir)
    frame = _load(path)
    if frame.empty:
        return {"graded": 0, "pending": 0, "voided": 0}
    results_path = Path(data_dir) / "game_results.csv"
    starters_path = Path(data_dir) / "sp_game_log.csv"
    game_scores = {}
    if results_path.exists():
        results = pd.read_csv(results_path, dtype=str).fillna("")
        for date, group in results.groupby("game_date"):
            home = group[group["home_away"].str.lower() == "home"]
            if not home.empty:
                row = home.iloc[0]
                game_scores[(str(date), str(row["opp"]), str(row["team"]))] = (
                    _number(row["opp_runs"]), _number(row["team_runs"]),
                )
    starter_stats = {}
    if starters_path.exists():
        starters = pd.read_csv(starters_path, dtype=str).fillna("")
        for _, row in starters.iterrows():
            starter_stats[(str(row.get("date", "")), _norm(row.get("pitcher_name")))] = row
    graded = voided = 0
    for idx, row in frame[frame["status"] == "pending"].iterrows():
        if row["kind"] == "game":
            away, sep, home = row["player"].partition("@")
            score = game_scores.get((row["game_date"], away, home)) if sep else None
            line = _number(row["line"])
            if score is None:
                continue
            away_runs, home_runs = score
            market, selection = row["market"], row["selection"]
            if market == "ml":
                won = (home_runs > away_runs) if selection == home else (away_runs > home_runs)
                actual = home_runs - away_runs
            elif market == "total" and line is not None:
                actual = home_runs + away_runs
                won = actual > line if selection == "over" else actual < line
            elif market == "runline" and line is not None:
                actual = home_runs - away_runs if selection == home else away_runs - home_runs
                won = actual + line > 0
            else:
                frame.at[idx, "status"] = "void"; frame.at[idx, "void_reason"] = "ungradeable_market"; voided += 1
                continue
            frame.at[idx, "actual"] = str(actual)
            frame.at[idx, "status"] = "graded"
            frame.at[idx, "won"] = str(won).lower()
            graded += 1
            continue
        stat = starter_stats.get((row["game_date"], _norm(row["player"])))
        if stat is None:
            continue
        key = row["market"]
        actual = {"K": _number(stat.get("K")), "BB": _number(stat.get("BB")),
                  "ER": _number(stat.get("ER")), "Outs": (_number(stat.get("IP")) or 0) * 3,
                  "F5_ER": _number(stat.get("f5_er"))}.get(key)
        line = _number(row["line"])
        if actual is None or line is None or row["selection"] not in {"over", "under"}:
            frame.at[idx, "status"] = "void"; frame.at[idx, "void_reason"] = "ungradeable_market"; voided += 1
            continue
        frame.at[idx, "actual"] = str(actual)
        frame.at[idx, "status"] = "graded"
        frame.at[idx, "won"] = str(actual > line if row["selection"] == "over" else actual < line).lower()
        graded += 1
    frame.to_csv(path, index=False)
    return {"graded": graded, "pending": int((frame.status == "pending").sum()), "voided": voided}
