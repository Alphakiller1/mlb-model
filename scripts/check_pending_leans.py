"""Report unsettled model leans by reason after the settle job.

Exit code 1 when stale pending leans WITHOUT a reason code exceed the threshold —
that means the grader itself is not classifying them, which is a defect, not a
data delay. Reason-coded pending leans (game not final yet, etc.) are healthy.
Today's open slate may still be pending without a reason until games finish.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import date

from mlbmodel.leans.grade import VOID_AFTER_DAYS

from mlbmodel.storage.supabase import SupabaseReader

UNEXPLAINED_THRESHOLD = int(os.getenv("PENDING_LEANS_THRESHOLD", "25"))
STALE_THRESHOLD = int(os.getenv("STALE_PENDING_THRESHOLD", "0"))


def pending_breakdown(
    reader: SupabaseReader | None = None,
) -> tuple[Counter, int, int, str | None]:
    reader = reader or SupabaseReader()
    if not reader.url or not reader.key:
        return Counter(), 0, 0, "warehouse credentials not configured"
    path = (
        "model_leans?settled=eq.false&select=lean_id,slate_date,source,market,"
        "selection,ungraded_reason&order=slate_date.desc,lean_id.desc"
    )
    result = (
        reader.get_all(path, max_rows=250000)
        if hasattr(type(reader), "get_all")
        else reader.get(path)
    )
    if result.error:
        return Counter(), 0, 0, result.error
    today = date.today()
    counts: Counter = Counter()
    unexplained = 0
    stale = 0
    for row in result.rows:
        reason = str(row.get("ungraded_reason") or "(no reason recorded)")
        counts[reason] += 1
        if reason == "(no reason recorded)":
            slate = str(row.get("slate_date") or "")[:10]
            if slate and slate < today.isoformat():
                unexplained += 1
        try:
            slate_day = date.fromisoformat(str(row.get("slate_date") or "")[:10])
        except ValueError:
            continue
        if (today - slate_day).days > VOID_AFTER_DAYS:
            stale += 1
    return counts, unexplained, stale, None


def main() -> int:
    counts, unexplained, stale, error = pending_breakdown()
    if error:
        print(f"ERROR: pending lean check could not read the permanent warehouse: {error}")
        return 1 if os.getenv("LEAN_SETTLE_REQUIRED") == "1" else 0
    total = sum(counts.values())
    if not total:
        print("OK: no pending model leans")
        return 0
    print(f"{total} model lean(s) still unsettled:")
    for reason, count in counts.most_common():
        print(f"  {reason}: {count}")
    if unexplained > UNEXPLAINED_THRESHOLD:
        print(
            f"ERROR: {unexplained} stale pending lean(s) have no reason code "
            f"(threshold {UNEXPLAINED_THRESHOLD}) — the grader is not classifying them."
        )
        return 1
    if stale > STALE_THRESHOLD:
        print(
            f"ERROR: {stale} pending lean(s) are older than the {VOID_AFTER_DAYS}-day "
            f"retry window (threshold {STALE_THRESHOLD}) — settlement did not persist."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
