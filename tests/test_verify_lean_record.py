from scripts.verify_lean_record import slate_date
from pathlib import Path


def test_slate_date_from_sync_json(tmp_path):
    sync = tmp_path / "mlbma_sync.json"
    sync.write_text('{"slate_date": "2026-07-24"}', encoding="utf-8")
    assert slate_date(tmp_path) == "2026-07-24"
