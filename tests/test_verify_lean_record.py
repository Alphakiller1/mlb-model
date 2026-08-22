import json

from scripts.verify_lean_record import (
    _verify_rows,
    priced_event_count,
    require_actionable_gate,
    slate_date,
)


def _ledger_rows(*, actionable: int = 3, avoid: int = 3, projections: int = 30):
    rows = []
    markets = ("ml", "total", "runline")
    for i in range(actionable):
        rows.append({
            "source": "matchup",
            "market": markets[i % 3],
            "lean": "MONITOR",
            "settled": False,
        })
    for i in range(max(avoid, 6 - actionable)):
        rows.append({
            "source": "matchup",
            "market": markets[i % 3],
            "lean": "AVOID",
            "settled": False,
        })
    rows.extend(
        {"source": "projection", "market": "k", "lean": "PROJECTION", "settled": False}
        for _ in range(projections)
    )
    return rows


def test_slate_date_from_sync_json(tmp_path):
    sync = tmp_path / "mlbma_sync.json"
    sync.write_text('{"slate_date": "2026-07-24"}', encoding="utf-8")
    assert slate_date(tmp_path) == "2026-07-24"


def test_verify_rows_accepts_local_snapshot_with_game_markets(monkeypatch, tmp_path):
    monkeypatch.setenv("LEAN_VERIFY_MIN_ACTIONABLE", "3")
    monkeypatch.setenv("LEAN_VERIFY_MIN_PROPS", "30")
    monkeypatch.setenv("LEAN_VERIFY_MIN_MATCHUP", "6")
    rows = _ledger_rows(actionable=3, avoid=3, projections=30)
    path = tmp_path / "model_leans_latest.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert _verify_rows("2026-07-06", payload["rows"], origin=str(path)) == 0


def test_verify_rows_fails_when_priced_slate_lacks_actionable_leans(monkeypatch):
    monkeypatch.setenv("LEAN_VERIFY_MIN_ACTIONABLE", "5")
    monkeypatch.setenv("LEAN_VERIFY_MIN_PROPS", "30")
    monkeypatch.setenv("LEAN_VERIFY_MIN_MATCHUP", "6")
    rows = _ledger_rows(actionable=2, avoid=6, projections=30)
    assert _verify_rows(
        "2026-08-22",
        rows,
        origin="warehouse",
        require_actionable=True,
        priced_games=11,
    ) == 1


def test_verify_rows_skips_actionable_gate_without_prices(monkeypatch):
    monkeypatch.setenv("LEAN_VERIFY_MIN_ACTIONABLE", "5")
    monkeypatch.setenv("LEAN_VERIFY_MIN_PROPS", "30")
    monkeypatch.setenv("LEAN_VERIFY_MIN_MATCHUP", "6")
    rows = _ledger_rows(actionable=2, avoid=6, projections=30)
    assert _verify_rows(
        "2026-08-22",
        rows,
        origin="warehouse",
        require_actionable=False,
        priced_games=0,
    ) == 0


def _write_odds_snapshot(path, commence_time: str) -> None:
    path.write_text(
        json.dumps({
            "fetched_at": "2026-08-20T21:12:37+00:00",
            "events": [{
                "commence_time": commence_time,
                "away_team": "New York Yankees",
                "home_team": "Boston Red Sox",
            }],
        }),
        encoding="utf-8",
    )


def test_priced_event_count_uses_eastern_slate_date(tmp_path):
    _write_odds_snapshot(tmp_path / "odds_latest.json", "2026-08-22T02:11:00Z")  # Aug 21 ET
    assert priced_event_count(tmp_path, "2026-08-21") == 1
    assert priced_event_count(tmp_path, "2026-08-22") == 0


def test_require_actionable_gate_false_when_snapshot_is_other_day(tmp_path, monkeypatch):
    monkeypatch.delenv("LEAN_VERIFY_REQUIRE_PRICED_MARKETS", raising=False)
    monkeypatch.delenv("ODDS_LIVE_FETCH_SKIPPED", raising=False)
    _write_odds_snapshot(tmp_path / "odds_latest.json", "2026-08-21T23:05:00Z")
    assert require_actionable_gate(tmp_path, "2026-08-22") is False
    assert require_actionable_gate(tmp_path, "2026-08-21") is True


def test_require_actionable_gate_false_when_quota_skip_and_no_prices(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_LIVE_FETCH_SKIPPED", "1")
    monkeypatch.setenv("LEAN_VERIFY_REQUIRE_PRICED_MARKETS", "1")
    _write_odds_snapshot(tmp_path / "odds_latest.json", "2026-08-20T23:05:00Z")
    assert require_actionable_gate(tmp_path, "2026-08-22") is False
