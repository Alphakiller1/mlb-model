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

from mlbmodel.storage.supabase import SupabaseReader

UNEXPLAINED_THRESHOLD = int(os.getenv("PENDING_LEANS_THRESHOLD", "25"))


def pending_breakdown(reader: SupabaseReader | None = None) -> tuple[Counter, int, str | None]:
    reader = reader or SupabaseReader()
    if not reader.url or not reader.key:
        return Counter(), 0, "warehouse credentials not configured"
    read_all = reader.get_all if hasattr(type(reader), "get_all") else reader.get
    result = read_all(
        "model_leans?settled=eq.false&select=lean_id,slate_date,source,market,"
        "selection,ungraded_reason&order=slate_date.desc,lean_id.desc"
    )
    if result.error:
        return Counter(), 0, result.error
    today = date.today().isoformat()
    counts: Counter = Counter()
    unexplained = 0
    for row in result.rows:
        reason = str(row.get("ungraded_reason") or "(no reason recorded)")
        counts[reason] += 1
        if reason == "(no reason recorded)":
            slate = str(row.get("slate_date") or "")[:10]
            if slate and slate < today:
                unexplained += 1
    return counts, unexplained, None


def main() -> int:
    counts, unexplained, error = pending_breakdown()
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
    if unexplained > UNEXPLAINED_THRESHOLD:
        print(
            f"ERROR: {unexplained} stale pending lean(s) have no reason code "
            f"(threshold {UNEXPLAINED_THRESHOLD}) — the grader is not classifying them."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
