"""Least-privilege Supabase REST reads with visible error state."""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from mlbmodel import settings

log = logging.getLogger(__name__)

# PostgREST + Cloudflare: a 14-day finals upsert is hundreds of rows in one POST.
# Cloudflare 522 is "origin timed out" — not a missing service key. Chunk and retry.
UPSERT_CHUNK = 40
_TRANSIENT_HTTP = frozenset({502, 503, 504, 522, 524})
_RETRY_BACKOFF = (1.5, 3.0, 6.0)


@dataclass(frozen=True)
class ReadResult:
    rows: list[dict]
    error: str | None = None


class SupabaseReader:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url if url is not None else settings.SUPABASE_URL).rstrip("/")
        self.key = key if key is not None else settings.supabase_read_key()

    def get(self, path: str) -> ReadResult:
        if not self.url or not self.key:
            return ReadResult([], "warehouse read credentials are not configured")
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{path}",
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return ReadResult(json.loads(response.read().decode()))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            return ReadResult([], f"warehouse read failed: HTTP {exc.code}: {body}")
        except Exception as exc:
            return ReadResult([], f"warehouse read failed: {type(exc).__name__}")

    def get_all(
        self,
        path: str,
        *,
        page_size: int = 1000,
        max_rows: int = 25000,
    ) -> ReadResult:
        """Read a PostgREST collection past the project's 1,000-row response cap."""
        rows: list[dict] = []
        separator = "&" if "?" in path else "?"
        for offset in range(0, max_rows, page_size):
            result = self.get(
                f"{path}{separator}limit={page_size}&offset={offset}"
            )
            if result.error:
                return ReadResult(rows, result.error)
            rows.extend(result.rows)
            if len(result.rows) < page_size:
                break
        return ReadResult(rows)


def _chunks(rows: list[dict], size: int):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _upsert_error_message(table: str, exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode(errors="replace")[:400]
    if exc.code in (401, 403):
        return (
            f"supabase upsert {table} failed HTTP {exc.code}: {body} "
            "(SUPABASE_SECRET_KEY must be a write/service key)"
        )
    if exc.code in _TRANSIENT_HTTP:
        return (
            f"supabase upsert {table} failed HTTP {exc.code}: {body} "
            "(transient origin timeout — retry; not a missing service key)"
        )
    return f"supabase upsert {table} failed HTTP {exc.code}: {body}"


class SupabaseWriter:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url if url is not None else settings.SUPABASE_URL).rstrip("/")
        self.key = key if key is not None else settings.supabase_write_key()

    def upsert(
        self,
        table: str,
        rows: list[dict],
        on_conflict: str,
        *,
        chunk_size: int = UPSERT_CHUNK,
    ) -> int:
        if not rows:
            return 0
        if not self.url or not self.key:
            raise RuntimeError("warehouse write credentials are not configured")
        written = 0
        size = max(1, int(chunk_size))
        for chunk in _chunks(rows, size):
            written += self._upsert_chunk(table, chunk, on_conflict)
        return written

    def _upsert_chunk(self, table: str, rows: list[dict], on_conflict: str) -> int:
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?on_conflict={on_conflict}",
            data=json.dumps(rows).encode(),
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        attempts = len(_RETRY_BACKOFF) + 1
        last_exc: BaseException | None = None
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=30):
                    return len(rows)
            except urllib.error.HTTPError as exc:
                last_exc = exc
                transient = exc.code in _TRANSIENT_HTTP
                if transient and attempt < attempts - 1:
                    delay = _RETRY_BACKOFF[attempt]
                    log.warning(
                        "supabase upsert %s HTTP %s (attempt %s/%s); retry in %.1fs",
                        table, exc.code, attempt + 1, attempts, delay,
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(_upsert_error_message(table, exc)) from exc
            except urllib.error.URLError as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    delay = _RETRY_BACKOFF[attempt]
                    log.warning(
                        "supabase upsert %s %s (attempt %s/%s); retry in %.1fs",
                        table, type(exc.reason).__name__ if exc.reason else "URLError",
                        attempt + 1, attempts, delay,
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"supabase upsert {table} failed: {exc}"
                ) from exc
        raise RuntimeError(f"supabase upsert {table} failed: {last_exc}")

    def insert(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        if not self.url or not self.key:
            raise RuntimeError("warehouse write credentials are not configured")
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}",
            data=json.dumps(rows).encode(),
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30):
            return len(rows)

    def update(self, table: str, filters: str, values: dict) -> None:
        if not self.url or not self.key:
            raise RuntimeError("warehouse write credentials are not configured")
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?{filters}",
            data=json.dumps(values).encode(),
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="PATCH",
        )
        with urllib.request.urlopen(request, timeout=30):
            return None
