"""Assemble the Results ledger from warehouse + local snapshot + game finals.

Pages builds record today's leans into ``model_leans_latest.json`` and (when
creds exist) Supabase. The Results pane used to read a single PostgREST page
of the newest warehouse rows — after recording every projection that window
is all unsettled pitcher stats, so the UI shows 0-0-0 even when yesterday's
matchup markets and a committed snapshot are sitting right there.

This module:
- pages warehouse settled rows (and pending non-projection rows)
- merges the local snapshot so CI/Pages still have a ledger without writes
- grades unsettled game markets in-memory against ``game_results.csv``
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from mlbmodel.baseball.repository import canonical_game_pk
from mlbmodel.leans.grade import grade_lean_detailed
from mlbmodel.storage.supabase import ReadResult

log = logging.getLogger(__name__)

LEAN_SELECT = (
    "lean_id,slate_date,game_pk,source,market,selection,line,"
    "model_prob,model_value,edge,lean,won,push,settled,entry_odds,recorded_at,"
    "void,ungraded_reason,closing_odds,clv_pts,realized_value"
)
SNAPSHOT_KEEP_DAYS = 60
RECENT_LIMIT = 80
_ACTIONABLE_TAGS = {
    "BET", "MONITOR", "STRONG", "LEAN", "EDGE", "OVER", "UNDER", "WATCH",
}


def lean_identity(row: dict) -> tuple:
    """Natural key matching ``model_leans`` uniqueness."""
    line = row.get("line")
    try:
        line_key: Any = round(float(line), 4) if line is not None else None
    except (TypeError, ValueError):
        line_key = line
    pk = row.get("game_pk")
    try:
        pk_key: Any = int(pk) if pk is not None else None
    except (TypeError, ValueError):
        pk_key = pk
    return (
        str(row.get("slate_date") or "")[:10],
        pk_key,
        str(row.get("source") or ""),
        str(row.get("market") or ""),
        str(row.get("selection") or ""),
        line_key,
    )


def _completeness(row: dict) -> tuple:
    has_wl = row.get("won") is not None or bool(row.get("push"))
    settled_clean = bool(row.get("settled")) and not bool(row.get("void"))
    return (
        settled_clean and has_wl,
        settled_clean,
        has_wl,
        bool(row.get("realized_value") is not None),
    )


def merge_lean_rows(*groups: Iterable[dict]) -> list[dict]:
    """Union lean groups; prefer the more-complete copy of each identity."""
    by_key: dict[tuple, dict] = {}
    for group in groups:
        for row in group or []:
            key = lean_identity(row)
            existing = by_key.get(key)
            if existing is None or _completeness(row) >= _completeness(existing):
                by_key[key] = dict(row)
    return list(by_key.values())


def prune_lean_rows(
    rows: list[dict],
    *,
    keep_days: int = SNAPSHOT_KEEP_DAYS,
    today: date | None = None,
) -> list[dict]:
    """Drop snapshot rows older than ``keep_days`` relative to today and the ledger."""
    dates = [str(r.get("slate_date") or "")[:10] for r in rows if r.get("slate_date")]
    if not dates:
        return rows
    today = today or datetime.now(timezone.utc).date()
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    try:
        latest = date.fromisoformat(max(dates))
        cutoff_latest = (latest - timedelta(days=keep_days)).isoformat()
        cutoff = min(cutoff, cutoff_latest)
    except ValueError:
        pass
    return [r for r in rows if str(r.get("slate_date") or "")[:10] >= cutoff]


def load_lean_snapshot(path: Path | str | None) -> list[dict]:
    if not path:
        return []
    dest = Path(path)
    if not dest.exists() or dest.stat().st_size == 0:
        return []
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("lean snapshot read failed (%s): %s", dest, exc)
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("rows") or []
        return [row for row in rows if isinstance(row, dict)]
    return []


def _read_path(reader, query: str) -> ReadResult:
    getter = getattr(reader, "get_all", None)
    if callable(getter):
        return getter(query)
    sep = "&" if "?" in query else "?"
    return reader.get(f"{query}{sep}limit=2000")


def fetch_warehouse_leans(reader) -> ReadResult:
    """Settled rows + pending non-projection rows. Soft-fails to an empty set."""
    settled = _read_path(
        reader,
        f"model_leans?settled=eq.true&select={LEAN_SELECT}&order=recorded_at.desc",
    )
    pending = _read_path(
        reader,
        "model_leans?settled=eq.false&source=neq.projection"
        f"&select={LEAN_SELECT}&order=recorded_at.desc",
    )
    if settled.error and pending.error:
        return ReadResult([], settled.error or pending.error)
    rows: list[dict] = []
    error = None
    if settled.error:
        error = settled.error
    else:
        rows.extend(settled.rows)
    if pending.error:
        error = error or pending.error
    else:
        rows.extend(pending.rows)
    # A partial success (one of the two queries) is still usable.
    if rows:
        return ReadResult(rows)
    return ReadResult([], error)


def fetch_warehouse_outcomes(reader) -> dict[int, dict]:
    games = _read_path(reader, "games?select=game_pk,home_team,away_team,game_date")
    outcomes = _read_path(
        reader,
        "game_outcomes?select=game_pk,home_runs,away_runs,total_runs,margin_home,winner_team",
    )
    if games.error or outcomes.error:
        return {}
    game_by_pk = {}
    for row in games.rows:
        try:
            game_by_pk[int(row["game_pk"])] = row
        except (TypeError, ValueError, KeyError):
            continue
    by_pk: dict[int, dict] = {}
    for row in outcomes.rows:
        if row.get("home_runs") is None and row.get("winner_team") is None:
            continue
        try:
            pk = int(row["game_pk"])
        except (TypeError, ValueError, KeyError):
            continue
        merged = dict(row)
        game = game_by_pk.get(pk) or {}
        merged.setdefault("home_team", game.get("home_team"))
        merged.setdefault("away_team", game.get("away_team"))
        merged.setdefault("game_date", game.get("game_date"))
        by_pk[pk] = merged
    return by_pk


def outcomes_from_game_results(rows: Iterable[dict]) -> tuple[dict[int, dict], dict[tuple[str, str], dict]]:
    """Rebuild game_outcomes from the team-level ``game_results.csv`` schema."""
    games: dict[tuple[str, str, str], dict] = {}
    for raw in rows:
        date_s = str(raw.get("game_date") or raw.get("date") or "")[:10]
        team = str(raw.get("team") or "").upper().strip()
        opp = str(raw.get("opp") or "").upper().strip()
        ha = str(raw.get("home_away") or "").lower().strip()
        try:
            team_runs = int(float(raw["team_runs"]))
            opp_runs = int(float(raw["opp_runs"]))
        except (KeyError, TypeError, ValueError):
            continue
        if not date_s or not team or not opp:
            continue
        if ha == "home":
            home, away, hr, ar = team, opp, team_runs, opp_runs
        elif ha == "away":
            away, home, ar, hr = team, opp, team_runs, opp_runs
        else:
            continue
        games[(date_s, home, away)] = {
            "game_date": date_s,
            "home_team": home,
            "away_team": away,
            "home_runs": hr,
            "away_runs": ar,
            "total_runs": hr + ar,
            "margin_home": hr - ar,
            "winner_team": home if hr > ar else away,
        }
    by_pk: dict[int, dict] = {}
    by_date_team: dict[tuple[str, str], dict] = {}
    for (date_s, home, away), outcome in games.items():
        pk = canonical_game_pk(date_s, away, home)
        payload = {**outcome, "game_pk": pk}
        by_pk[pk] = payload
        by_date_team[(date_s, home)] = payload
        by_date_team[(date_s, away)] = payload
    return by_pk, by_date_team


def load_game_results_outcomes(path: Path | str | None) -> tuple[dict[int, dict], dict[tuple[str, str], dict]]:
    if not path:
        return {}, {}
    dest = Path(path)
    if not dest.exists() or dest.stat().st_size == 0:
        return {}, {}
    try:
        with dest.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        log.warning("game_results read failed (%s): %s", dest, exc)
        return {}, {}
    return outcomes_from_game_results(rows)


def _prev_day(date_s: str) -> str | None:
    try:
        return (date.fromisoformat(date_s[:10]) - timedelta(days=1)).isoformat()
    except ValueError:
        return None


def outcome_for_lean(
    lean: dict,
    by_pk: dict[int, dict],
    by_date_team: dict[tuple[str, str], dict],
) -> dict | None:
    pk = lean.get("game_pk")
    try:
        pk_i = int(pk) if pk is not None else None
    except (TypeError, ValueError):
        pk_i = None
    if pk_i is not None and pk_i in by_pk:
        return by_pk[pk_i]
    date_s = str(lean.get("slate_date") or "")[:10]
    market = str(lean.get("market") or "").lower()
    sel = str(lean.get("selection") or "").upper().strip()
    if market not in {"ml", "moneyline", "h2h", "runline", "spread", "spreads", "run_line"}:
        return None
    if len(sel) != 3:
        return None
    for candidate in (date_s, _prev_day(date_s)):
        if not candidate:
            continue
        found = by_date_team.get((candidate, sel))
        if found:
            return found
    return None


def apply_local_grades(
    rows: list[dict],
    *,
    by_pk: dict[int, dict],
    by_date_team: dict[tuple[str, str], dict] | None = None,
) -> list[dict]:
    """Copy rows and fill W/L/P from local finals when the warehouse has not graded yet."""
    by_date_team = by_date_team or {}
    out: list[dict] = []
    for raw in rows:
        row = dict(raw)
        if row.get("settled") and not row.get("void"):
            out.append(row)
            continue
        # Re-grade voids that only failed because the outcome was missing.
        outcome = outcome_for_lean(row, by_pk, by_date_team)
        source = str(row.get("source") or "").lower()
        # Props/projections need pitcher box scores; leave those to the settle job.
        if source in {"prizepicks", "underdog", "sleeper", "pickem", "prop", "projection"}:
            out.append(row)
            continue
        result = grade_lean_detailed(row, outcome=outcome, pitcher_stats=None)
        if result.won is not None or result.push:
            row["settled"] = True
            row["won"] = result.won
            row["push"] = result.push
            row["void"] = False
            row["ungraded_reason"] = None
            if result.realized_value is not None:
                row["realized_value"] = result.realized_value
            row["_locally_graded"] = True
        elif result.reason and not row.get("ungraded_reason"):
            row["ungraded_reason"] = result.reason
        out.append(row)
    return out


def _recent_tier(row: dict) -> int:
    settled = bool(row.get("settled"))
    void = bool(row.get("void"))
    source = str(row.get("source") or "").lower()
    lean = str(row.get("lean") or "").upper()
    has_result = settled and (row.get("won") is not None or row.get("push") or void)
    if has_result and not void:
        return 0
    if settled and void:
        return 1
    if source != "projection" or lean in _ACTIONABLE_TAGS:
        return 2
    return 3


def select_recent_leans(rows: list[dict], *, limit: int = RECENT_LIMIT) -> list[dict]:
    """Settled W/L first, then pending game/prop leans, then pitcher projections."""
    ordered = sorted(
        rows,
        key=lambda r: str(r.get("recorded_at") or r.get("slate_date") or ""),
        reverse=True,
    )
    ordered.sort(key=_recent_tier)
    return ordered[:limit]


def load_tracked_leans(
    reader,
    *,
    snapshot_path: Path | str | None = None,
    game_results_path: Path | str | None = None,
) -> tuple[list[dict], str | None]:
    """Warehouse + snapshot + locally graded finals. Notice is set on warehouse failure."""
    warehouse = fetch_warehouse_leans(reader)
    snapshot_rows = load_lean_snapshot(snapshot_path)
    notice = None
    if warehouse.error and not warehouse.rows:
        notice = warehouse.error
        rows = list(snapshot_rows)
    else:
        rows = merge_lean_rows(warehouse.rows, snapshot_rows)
        if warehouse.error:
            notice = warehouse.error
    if not rows:
        return [], notice
    csv_pk, csv_team = load_game_results_outcomes(game_results_path)
    warehouse_pk = fetch_warehouse_outcomes(reader) if not (warehouse.error and not warehouse.rows) else {}
    by_pk = {**csv_pk, **warehouse_pk}
    by_date_team = dict(csv_team)
    for outcome in warehouse_pk.values():
        date_s = str(outcome.get("game_date") or "")[:10]
        home = str(outcome.get("home_team") or "").upper()
        away = str(outcome.get("away_team") or "").upper()
        if date_s and home:
            by_date_team[(date_s, home)] = outcome
        if date_s and away:
            by_date_team[(date_s, away)] = outcome
    return apply_local_grades(rows, by_pk=by_pk, by_date_team=by_date_team), notice
