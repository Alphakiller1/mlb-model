"""Timestamped pick'em line snapshots.

Line caches are stored as ``{"snapshot_at": <UTC ISO>, "lines": [...]}`` so every
consumer can tell how old the lines are. Legacy bare-list snapshots (the
committed fallbacks predating this format) read fine but carry no timestamp —
they are treated as STALE, displayed with a warning, and never recorded as
leans: grading a lean against a line nobody could actually bet contaminates the
track record.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path


def write_lines_cache(lines: list[dict], cache_path: str | Path | None) -> None:
    if cache_path is None:
        return
    payload = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lines": lines,
    }
    Path(cache_path).write_text(json.dumps(payload), encoding="utf-8")


def read_lines_cache(cache_path: str | Path | None) -> tuple[list[dict], str | None]:
    """Returns (lines, snapshot_at). Accepts wrapped and legacy bare-list formats."""
    if not cache_path:
        return [], None
    path = Path(cache_path)
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], None
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        lines = data.get("lines")
        if isinstance(lines, list):
            return lines, data.get("snapshot_at")
    return [], None


def snapshot_is_fresh(snapshot_at: str | None, slate_date: str | None) -> bool:
    """A snapshot is fresh for a slate when it was taken on (or after) the slate date."""
    if not snapshot_at or not slate_date:
        return False
    try:
        snap_day = datetime.fromisoformat(str(snapshot_at).replace("Z", "+00:00")).date()
        slate = date.fromisoformat(str(slate_date)[:10])
    except (TypeError, ValueError):
        return False
    return snap_day >= slate


def snapshot_label(snapshot_at: str | None) -> str:
    if not snapshot_at:
        return "undated snapshot (treated as stale)"
    return f"lines as of {str(snapshot_at)[:16]}Z"
