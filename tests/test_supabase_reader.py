import urllib.error
from io import BytesIO

import pytest

from mlbmodel.storage.supabase import ReadResult, SupabaseReader, SupabaseWriter


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


class _Ok:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int, body: bytes = b"error code: 522") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.supabase.co/rest/v1/games",
        code,
        "Error",
        hdrs=None,
        fp=BytesIO(body),
    )


def test_upsert_chunks_large_batches(monkeypatch):
    writer = SupabaseWriter("https://example.supabase.co", "key")
    calls = []

    def fake_open(request, timeout=30):
        payload = __import__("json").loads(request.data.decode())
        calls.append(len(payload))
        return _Ok()

    monkeypatch.setattr("mlbmodel.storage.supabase.urllib.request.urlopen", fake_open)
    rows = [{"game_pk": i} for i in range(90)]
    assert writer.upsert("games", rows, "game_pk", chunk_size=40) == 90
    assert calls == [40, 40, 10]


def test_upsert_retries_cloudflare_522_then_succeeds(monkeypatch):
    writer = SupabaseWriter("https://example.supabase.co", "key")
    attempts = {"n": 0}
    sleeps = []

    def fake_open(request, timeout=30):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(522)
        return _Ok()

    monkeypatch.setattr("mlbmodel.storage.supabase.urllib.request.urlopen", fake_open)
    monkeypatch.setattr("mlbmodel.storage.supabase.time.sleep", sleeps.append)
    assert writer.upsert("games", [{"game_pk": 1}], "game_pk") == 1
    assert attempts["n"] == 2
    assert sleeps == [1.5]


def test_upsert_522_does_not_blame_the_service_key(monkeypatch):
    writer = SupabaseWriter("https://example.supabase.co", "key")

    def fake_open(request, timeout=30):
        raise _http_error(522)

    monkeypatch.setattr("mlbmodel.storage.supabase.urllib.request.urlopen", fake_open)
    monkeypatch.setattr("mlbmodel.storage.supabase.time.sleep", lambda *_: None)
    with pytest.raises(RuntimeError, match="transient origin timeout") as exc:
        writer.upsert("games", [{"game_pk": 1}], "game_pk")
    assert "SUPABASE_SECRET_KEY" not in str(exc.value)
    assert "522" in str(exc.value)


def test_upsert_401_still_points_at_the_write_key(monkeypatch):
    writer = SupabaseWriter("https://example.supabase.co", "key")

    def fake_open(request, timeout=30):
        raise _http_error(401, b"JWT expired")

    monkeypatch.setattr("mlbmodel.storage.supabase.urllib.request.urlopen", fake_open)
    with pytest.raises(RuntimeError, match="SUPABASE_SECRET_KEY"):
        writer.upsert("games", [{"game_pk": 1}], "game_pk")

