"""Apply a versioned SQL migration to Supabase (requires SUPABASE_DB_URL)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def apply_sql(path: Path) -> None:
    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not db_url:
        raise SystemExit(
            "SUPABASE_DB_URL is not set. Add the Postgres connection string from "
            "Supabase Dashboard → Project Settings → Database to .env, then re-run."
        )
    try:
        import psycopg2
    except ImportError as exc:
        raise SystemExit("pip install psycopg2-binary") from exc

    sql = path.read_text(encoding="utf-8")
    conn = psycopg2.connect(db_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()
    print(f"applied {path.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply a Supabase SQL migration file.")
    ap.add_argument(
        "migration",
        nargs="?",
        default="migrations/0003_model_leans.sql",
        help="path to .sql file (default: 0003_model_leans)",
    )
    args = ap.parse_args()
    _load_env()
    path = Path(args.migration)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise SystemExit(f"migration not found: {path}")
    apply_sql(path)


if __name__ == "__main__":
    main()
