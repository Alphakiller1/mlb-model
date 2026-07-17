"""Report unsettled model leans by reason after the settle job.

Exit code 1 when pending leans WITHOUT a reason code exceed the threshold —
that means the grader itself is not classifying them, which is a defect, not a
data delay. Reason-coded pending leans (game not final yet, etc.) are healthy.
"""
from __future__ import annotations

import os
from collections import Counter

from mlbmodel.storage.supabase import SupabaseReader

UNEXPLAINED_THRESHOLD = int(os.getenv("PENDING_LEANS_THRESHOLD", "25"))


def pending_breakdown(reader: SupabaseReader | None = None) -> tuple[Counter, str | None]:
    reader = reader or SupabaseReader()
    if not reader.url or not reader.key:
        return Counter(), "warehouse credentials not configured"
    result = reader.get(
        "model_leans?settled=eq.false&select=lean_id,slate_date,source,market,"
        "selection,ungraded_reason&order=slate_date.desc&limit=1000"
    )
    if result.error:
        return Counter(), result.error
    counts: Counter = Counter(
        str(row.get("ungraded_reason") or "(no reason recorded)") for row in result.rows
    )
    return counts, None


def main() -> int:
    counts, error = pending_breakdown()
    if error:
        print(f"pending lean check skipped: {error}")
        return 0
    total = sum(counts.values())
    if not total:
        print("OK: no pending model leans")
        return 0
    print(f"{total} model lean(s) still unsettled:")
    for reason, count in counts.most_common():
        print(f"  {reason}: {count}")
    unexplained = counts.get("(no reason recorded)", 0)
    if unexplained > UNEXPLAINED_THRESHOLD:
        print(
            f"ERROR: {unexplained} pending lean(s) have no reason code "
            f"(threshold {UNEXPLAINED_THRESHOLD}) — the grader is not classifying them."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
