from mlbmodel.storage.supabase import ReadResult, SupabaseReader


def test_get_all_paginates_until_short_page(monkeypatch):
    reader = SupabaseReader("https://example.supabase.co", "key")
    calls = []

    def fake_get(path):
        calls.append(path)
        if "offset=0" in path:
            return ReadResult([{"id": index} for index in range(1000)])
        return ReadResult([{"id": 1000}])

    monkeypatch.setattr(reader, "get", fake_get)
    result = reader.get_all("model_leans?settled=eq.false&select=id")

    assert result.error is None
    assert len(result.rows) == 1001
    assert calls == [
        "model_leans?settled=eq.false&select=id&limit=1000&offset=0",
        "model_leans?settled=eq.false&select=id&limit=1000&offset=1000",
    ]


def test_get_all_preserves_partial_rows_when_later_page_fails(monkeypatch):
    reader = SupabaseReader("https://example.supabase.co", "key")

    def fake_get(path):
        if "offset=0" in path:
            return ReadResult([{"id": index} for index in range(1000)])
        return ReadResult([], "warehouse read failed")

    monkeypatch.setattr(reader, "get", fake_get)
    result = reader.get_all("games?select=game_pk")

    assert len(result.rows) == 1000
    assert result.error == "warehouse read failed"
