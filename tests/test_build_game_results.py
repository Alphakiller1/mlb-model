import sys

from mlbmodel.sources.build_game_results import main


class _Writer:
    def __init__(self):
        self.url = "https://example.supabase.co"
        self.key = "secret"

    def upsert(self, table, rows, on_conflict):
        raise RuntimeError(
            "supabase upsert games failed HTTP 522: error code: 522 "
            "(transient origin timeout — retry; not a missing service key)"
        )


def test_build_game_results_keeps_csv_when_warehouse_522(tmp_path, monkeypatch, capsys):
    finals = [{
        "date": "2026-09-07", "game_number": 1, "mlb_game_pk": 1,
        "away": "NYY", "home": "BOS", "ar": 3, "hr": 5, "f5a": 1, "f5h": 2,
    }]
    monkeypatch.setattr(
        "mlbmodel.sources.build_game_results.fetch_finals",
        lambda start, end: finals,
    )
    monkeypatch.setattr(
        "mlbmodel.sources.build_game_results.SupabaseWriter",
        _Writer,
    )
    monkeypatch.setattr(sys, "argv", ["build_game_results", "--out", str(tmp_path), "--days", "1"])
    main()
    csv_path = tmp_path / "game_results.csv"
    assert csv_path.exists()
    text = csv_path.read_text(encoding="utf-8")
    assert "NYY" in text and "BOS" in text
    assert "warehouse write skipped after retries" in capsys.readouterr().out
