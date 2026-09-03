"""Replay locally-snapshotted model leans into the warehouse.

A build writes its ledger locally first and *then* upserts it. When the upsert fails the run
still logs a warning and carries on, so the leans exist only as a file — and because
`model_leans_latest.json` is overwritten by the next build, that file used to be gone within
a day. That is how the warehouse ended up holding five slate dates for a whole season while
builds kept producing full boards.

This replays what is on disk. It is a **production write**, so it prints the plan and does
nothing unless you pass `--apply`.

    PYTHONPATH=. python scripts/replay_leans.py                 # show what would be sent
    PYTHONPATH=. python scripts/replay_leans.py --apply         # actually upsert
    PYTHONPATH=. python scripts/replay_leans.py --apply --slate 2026-08-31
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mlbmodel import settings
from mlbmodel.leans.record import record_leans
from mlbmodel.storage.supabase import SupabaseReader


def _snapshot_files(cache_dir: Path) -> list[Path]:
    files = sorted((cache_dir / "lean_snapshots").glob("*.json"))
    latest = cache_dir / "model_leans_latest.json"
    if latest.exists():
        files.append(latest)
    return files


def _load(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! {path.name}: unreadable ({type(exc).__name__})")
        return []
    return list(payload.get("rows") or [])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the warehouse write")
    parser.add_argument("--slate", help="only replay this slate date (YYYY-MM-DD)")
    parser.add_argument("--data-dir", help="override the snapshot directory")
    args = parser.parse_args()

    cache_dir = Path(args.data_dir) if args.data_dir else settings.CACHE_DIR
    print(f"snapshot directory: {cache_dir}")

    rows: dict[tuple, dict] = {}
    for path in _snapshot_files(cache_dir):
        for row in _load(path):
            slate = str(row.get("slate_date") or "")
            if args.slate and slate != args.slate:
                continue
            # Same uniqueness key the table enforces, so a replay is idempotent.
            key = (
                slate, row.get("game_pk"), row.get("source"),
                row.get("market"), row.get("selection"), row.get("line"),
            )
            rows[key] = row
    if not rows:
        print("nothing to replay")
        return

    by_slate: dict[str, int] = {}
    for (slate, *_rest) in rows:
        by_slate[slate] = by_slate.get(slate, 0) + 1
    print(f"\n{len(rows)} unique lean(s) on disk:")
    for slate in sorted(by_slate):
        print(f"  {slate}  {by_slate[slate]:5d}")

    reader = SupabaseReader()
    for slate in sorted(by_slate):
        result = reader.get(f"model_leans?select=lean_id&slate_date=eq.{slate}&limit=1000")
        if result.error:
            print(f"\n  warehouse read failed for {slate}: {result.error}")
        else:
            print(f"  {slate}: warehouse already holds {len(result.rows)} row(s)")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to upsert.")
        return

    written = record_leans(list(rows.values()), snapshot_path=False)
    print(f"\nupserted {written} lean(s)")


if __name__ == "__main__":
    main()
