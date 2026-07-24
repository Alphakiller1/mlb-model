"""Post-build gate: confirm today's slate leans landed in the warehouse."""
from __future__ import annotations

import json
import os
import sys
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


def slate_date(data_dir: Path) -> str | None:
    explicit = os.getenv("VERIFY_SLATE_DATE", "").strip()[:10]
    if explicit:
        return explicit
    sync_path = data_dir / "mlbma_sync.json"
    if sync_path.exists():
        payload = json.loads(sync_path.read_text(encoding="utf-8"))
        value = str(payload.get("slate_date") or "")[:10]
        if value:
            return value
    matchups = data_dir / "today_matchups.csv"
    if matchups.exists():
        import pandas as pd

        frame = pd.read_csv(matchups, nrows=1)
        if "Slate_Date" in frame.columns and len(frame):
            return str(frame.iloc[0]["Slate_Date"])[:10]
    return None


def main() -> int:
    _load_env()
    data_dir = Path(os.getenv("MLBMODEL_CACHE_DIR") or os.getenv("MLBMA_DATA_DIR") or ROOT / "data")
    slate = slate_date(data_dir)
    if not slate:
        print("verify_lean_record skipped: no slate date")
        return 0

    from mlbmodel.storage.supabase import SupabaseReader

    reader = SupabaseReader()
    if not reader.url or not reader.key:
        print("ERROR: warehouse read credentials missing — cannot verify lean tracking")
        return 1

    result = reader.get(
        f"model_leans?slate_date=eq.{slate}&select=lean_id,lean,source,settled"
        "&order=recorded_at.desc&limit=1000"
    )
    if result.error:
        print(f"ERROR: lean warehouse read failed: {result.error}")
        return 1

    rows = result.rows
    actionable_tags = {"BET", "MONITOR", "STRONG", "LEAN", "OVER", "UNDER", "EDGE"}
    actionable = [row for row in rows if str(row.get("lean") or "").upper() in actionable_tags]
    prop_sources = {"prop", "projection", "prizepicks", "underdog", "sleeper", "pickem"}
    prop_rows = [row for row in rows if str(row.get("source") or "").lower() in prop_sources]
    min_actionable = int(os.getenv("LEAN_VERIFY_MIN_ACTIONABLE", "5"))
    min_props = int(os.getenv("LEAN_VERIFY_MIN_PROPS", "30"))

    if not rows:
        print(f"ERROR: no model_leans rows for slate {slate}")
        return 1
    if len(prop_rows) < min_props:
        print(
            f"ERROR: only {len(prop_rows)} prop/projection leans for {slate} "
            f"(need >= {min_props})"
        )
        return 1
    if len(actionable) < min_actionable:
        print(
            f"ERROR: only {len(actionable)} actionable market leans for {slate} "
            f"(need >= {min_actionable})"
        )
        return 1

    print(
        f"OK: {len(rows)} leans on {slate} "
        f"({len(prop_rows)} props/projections, {len(actionable)} actionable market, "
        f"{sum(1 for r in rows if r.get('settled'))} settled)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
