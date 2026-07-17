"""One-time forensic audit of the model_leans ledger.

Flags historical track-record contamination:

1. Pick'em leans recorded on days when the committed line snapshot predated the
   slate (lines nobody could actually bet). Snapshot history is reconstructed
   from the git commit dates of deployment_data/*_lines.json.
2. Leans in markets the grader could not settle before the 0005 migration
   (fantasy_score, h, f5_er, projections) — now gradeable or voidable; run the
   settle job after applying the migration to backfill.

Read-only: prints a report; pass --tag to write `ungraded_reason='suspect_stale_snapshot'`
onto flagged, still-unsettled pick'em leans.

Usage: python scripts/audit_leans.py [--tag]
"""
from __future__ import annotations

import argparse
import subprocess
from collections import Counter
from datetime import date, datetime

from mlbmodel import settings
from mlbmodel.storage.supabase import SupabaseReader, SupabaseWriter

PICKEM_SOURCES = {"prizepicks", "underdog", "sleeper"}
SNAPSHOT_FILES = {
    "prizepicks": "deployment_data/prizepicks_lines.json",
    "underdog": "deployment_data/underdog_lines.json",
    "sleeper": "deployment_data/sleeper_lines.json",
}


def snapshot_commit_dates(path: str) -> list[date]:
    """Dates on which the committed snapshot file changed (newest first)."""
    proc = subprocess.run(
        ["git", "log", "--format=%cs", "--", path],
        capture_output=True, text=True, cwd=settings.ROOT, check=False,
    )
    out = []
    for line in proc.stdout.splitlines():
        try:
            out.append(date.fromisoformat(line.strip()))
        except ValueError:
            continue
    return out


def snapshot_date_for(slate: date, commit_dates: list[date]) -> date | None:
    """Most recent snapshot refresh on or before the slate date."""
    eligible = [d for d in commit_dates if d <= slate]
    return max(eligible) if eligible else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", action="store_true",
                        help="Write suspect_stale_snapshot onto flagged unsettled pick'em leans.")
    args = parser.parse_args()

    reader = SupabaseReader()
    if not reader.url or not reader.key:
        print("warehouse credentials not configured (.env) — cannot audit")
        return 1
    result = reader.get(
        "model_leans?select=lean_id,slate_date,source,market,settled,won,push,void,"
        "ungraded_reason&limit=10000&order=slate_date.asc"
    )
    if result.error:
        print(f"read failed: {result.error}")
        return 1
    rows = result.rows
    print(f"audit: {len(rows)} leans in ledger")

    commit_dates = {book: snapshot_commit_dates(path) for book, path in SNAPSHOT_FILES.items()}
    for book, dates in commit_dates.items():
        label = ", ".join(str(d) for d in dates[:5])
        print(f"  {book} snapshot refreshes (latest 5): {label or 'none found in git'}")

    suspect: list[dict] = []
    ungradeable = Counter()
    for row in rows:
        source = str(row.get("source") or "").lower()
        market = str(row.get("market") or "").lower()
        slate_raw = str(row.get("slate_date") or "")[:10]
        try:
            slate = date.fromisoformat(slate_raw)
        except ValueError:
            continue
        if source in PICKEM_SOURCES:
            snap = snapshot_date_for(slate, commit_dates.get(source, []))
            # A snapshot committed before the slate date could not contain that
            # day's lines: PrizePicks/Underdog/Sleeper boards change daily.
            if snap is None or snap < slate:
                suspect.append(row)
        if market in {"fantasy_score", "h", "f5_er"} or source == "projection":
            if not row.get("settled"):
                ungradeable[f"{source}/{market}"] += 1

    print(f"\nSUSPECT pick'em leans (snapshot predates slate): {len(suspect)}")
    by_state = Counter(
        ("settled" if r.get("settled") else "pending") for r in suspect
    )
    for state, count in by_state.items():
        print(f"  {state}: {count}")
    graded_suspect = [r for r in suspect if r.get("settled") and r.get("won") is not None]
    if graded_suspect:
        wins = sum(1 for r in graded_suspect if r.get("won"))
        print(
            f"  ALREADY GRADED against possibly-phantom lines: {len(graded_suspect)} "
            f"({wins}W-{len(graded_suspect) - wins}L) — exclude these from any quoted record."
        )

    print(f"\nPre-0005 ungradeable-market pending leans: {sum(ungradeable.values())}")
    for key, count in ungradeable.most_common():
        print(f"  {key}: {count}")
    print("  (apply migrations/0005_grading_audit.sql, then run the settle job to backfill)")

    if args.tag and suspect:
        writer = SupabaseWriter()
        tagged = 0
        for row in suspect:
            if row.get("settled"):
                continue
            writer.update(
                "model_leans",
                f"lean_id=eq.{row['lean_id']}",
                {"ungraded_reason": "suspect_stale_snapshot"},
            )
            tagged += 1
        print(f"\ntagged {tagged} unsettled suspect lean(s)")
    print(f"\naudit completed {datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
