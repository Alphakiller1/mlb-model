"""Least-privilege Supabase REST reads with visible error state."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from mlbmodel import settings


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


class SupabaseWriter:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url if url is not None else settings.SUPABASE_URL).rstrip("/")
        self.key = key if key is not None else settings.supabase_write_key()

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> int:
        if not rows:
            return 0
        if not self.url or not self.key:
            raise RuntimeError("warehouse write credentials are not configured")
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
        try:
            with urllib.request.urlopen(request, timeout=30):
                return len(rows)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:400]
            raise RuntimeError(
                f"supabase upsert {table} failed HTTP {exc.code}: {body} "
                "(SUPABASE_SECRET_KEY must be a write/service key)"
            ) from exc

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
