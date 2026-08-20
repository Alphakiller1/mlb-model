import json

from scripts.verify_lean_record import _verify_rows, slate_date


def test_slate_date_from_sync_json(tmp_path):
    sync = tmp_path / "mlbma_sync.json"
    sync.write_text('{"slate_date": "2026-07-24"}', encoding="utf-8")
    assert slate_date(tmp_path) == "2026-07-24"


def test_verify_rows_accepts_local_snapshot_with_game_markets(monkeypatch, tmp_path):
    monkeypatch.setenv("LEAN_VERIFY_MIN_ACTIONABLE", "3")
    monkeypatch.setenv("LEAN_VERIFY_MIN_PROPS", "30")
    monkeypatch.setenv("LEAN_VERIFY_MIN_MATCHUP", "6")
    rows = [
        {"source": "matchup", "market": "ml", "lean": "MONITOR", "settled": False},
        {"source": "matchup", "market": "ml", "lean": "AVOID", "settled": False},
        {"source": "matchup", "market": "total", "lean": "MONITOR", "settled": False},
        {"source": "matchup", "market": "total", "lean": "AVOID", "settled": False},
        {"source": "matchup", "market": "runline", "lean": "MONITOR", "settled": False},
        {"source": "matchup", "market": "runline", "lean": "AVOID", "settled": False},
    ] + [
        {"source": "projection", "market": "k", "lean": "PROJECTION", "settled": False}
        for _ in range(30)
    ]
    path = tmp_path / "model_leans_latest.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert _verify_rows("2026-07-06", payload["rows"], origin=str(path)) == 0
