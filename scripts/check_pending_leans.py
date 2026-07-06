"""Warn when model leans remain unsettled after the settle job."""
from __future__ import annotations

from mlbmodel.storage.supabase import SupabaseReader


def pending_count(reader: SupabaseReader | None = None) -> tuple[int, str | None]:
    reader = reader or SupabaseReader()
    if not reader.url or not reader.key:
        return 0, "warehouse credentials not configured"
    result = reader.get(
        "model_leans?settled=eq.false&select=lean_id,slate_date,source,market,selection"
        "&order=slate_date.desc&limit=500"
    )
    if result.error:
        return 0, result.error
    return len(result.rows), None


def main() -> int:
    count, error = pending_count()
    if error:
        print(f"pending lean check skipped: {error}")
        return 0
    if count:
        print(f"WARNING: {count} model lean(s) still unsettled after settle run")
        return 0
    print("OK: no pending model leans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
