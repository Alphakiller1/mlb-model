from datetime import date
from unittest.mock import MagicMock

from scripts.check_pending_leans import pending_breakdown


class _Result:
    def __init__(self, rows, error=None):
        self.rows = rows
        self.error = error


def test_pending_breakdown_ignores_today_without_reason():
    today = date.today().isoformat()
    reader = MagicMock()
    reader.url = "https://example.supabase.co"
    reader.key = "key"
    reader.get.return_value = _Result([
        {"slate_date": today, "ungraded_reason": None},
        {"slate_date": "2026-07-01", "ungraded_reason": None},
        {"slate_date": "2026-07-01", "ungraded_reason": "game_outcome_missing"},
    ])
    counts, unexplained, error = pending_breakdown(reader)
    assert error is None
    assert counts["(no reason recorded)"] == 2
    assert counts["game_outcome_missing"] == 1
    assert unexplained == 1
