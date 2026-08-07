"""Session guard: the test suite must never write to a real warehouse.

``mlbmodel.settings`` calls ``load_dotenv()`` at import, so a developer's local
.env silently hands live Supabase credentials to every test. Any test that
builds the report (test_build_app_smoke, test_views_*) runs the lean recorder,
which upserts whatever the fixtures produced straight into the real
``model_leans`` ledger — 2,280 rows of 2026-08-01 fixture data reached the
production warehouse this way on 2026-08-07, across eight builds in one `pytest`
invocation.

Blanking the credentials for the whole session makes a local run behave like CI
(which has no .env) and turns ``record_leans`` into its documented no-op. Tests
that exercise the storage layer pass an explicit url/key to
``SupabaseReader``/``SupabaseWriter`` and are unaffected, because those
constructors only fall back to settings when the argument is None.
"""
from __future__ import annotations

import os

import pytest

from mlbmodel import settings

_ENV_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
)


@pytest.fixture(autouse=True, scope="session")
def _block_live_warehouse_access():
    env_originals = {key: os.environ.pop(key, None) for key in _ENV_KEYS}
    originals = (
        settings.SUPABASE_URL,
        settings.SUPABASE_KEY,
        settings.SUPABASE_SECRET_KEY,
        settings.SUPABASE_PUBLISHABLE_KEY,
    )
    settings.SUPABASE_URL = ""
    settings.SUPABASE_KEY = ""
    settings.SUPABASE_SECRET_KEY = ""
    settings.SUPABASE_PUBLISHABLE_KEY = ""
    try:
        yield
    finally:
        (
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY,
            settings.SUPABASE_SECRET_KEY,
            settings.SUPABASE_PUBLISHABLE_KEY,
        ) = originals
        for key, value in env_originals.items():
            if value is not None:
                os.environ[key] = value
