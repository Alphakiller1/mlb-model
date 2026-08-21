"""Post-build gate: confirm today's slate leans landed in the warehouse."""
from __future__ import annotations

import json
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


def _env_flag(name: str) -> bool | None:
    raw = os.getenv(name, "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return None


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


def priced_event_count(data_dir: Path, slate: str) -> int:
    """Odds API events in the cached snapshot whose first pitch falls on `slate` (ET)."""
    try:
        from mlbmodel.market.quotes import filter_events_for_slate, load_cached_events

        events, _fetched = load_cached_events(data_dir / "odds_latest.json")
        return len(filter_events_for_slate(events, slate))
    except Exception:
        return 0


def require_actionable_gate(data_dir: Path, slate: str) -> bool:
    """BET/MONITOR counts are only meaningful when this slate has priced game lines.

    Scheduled Pages builds skip the live Odds API fetch when the key is near quota.
    The committed snapshot is then for an earlier slate, so tonight's games have no
    prices and almost every lean is PROJECTION/WATCH — not a recorder failure.
    """
    if _env_flag("LEAN_VERIFY_REQUIRE_PRICED_MARKETS") is False:
        return False
    if _env_flag("ODDS_LIVE_FETCH_SKIPPED") is True and priced_event_count(data_dir, slate) == 0:
        return False
    if _env_flag("LEAN_VERIFY_REQUIRE_PRICED_MARKETS") is True:
        return True
    return priced_event_count(data_dir, slate) > 0


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
        snapshot = data_dir / "model_leans_latest.json"
        if snapshot.exists():
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            rows = payload.get("rows") or []
            return _verify_rows(
                slate,
                rows,
                origin=str(snapshot),
                require_actionable=require_actionable_gate(data_dir, slate),
                priced_games=priced_event_count(data_dir, slate),
            )
        print("ERROR: warehouse read credentials missing — cannot verify lean tracking")
        return 1

    result = reader.get_all(
        f"model_leans?slate_date=eq.{slate}&select=lean_id,lean,source,market,settled"
        "&order=recorded_at.desc"
    )
    if result.error:
        print(f"ERROR: lean warehouse read failed: {result.error}")
        return 1

    return _verify_rows(
        slate,
        result.rows,
        origin="warehouse",
        require_actionable=require_actionable_gate(data_dir, slate),
        priced_games=priced_event_count(data_dir, slate),
    )


def _verify_rows(
    slate: str,
    rows: list[dict],
    *,
    origin: str,
    require_actionable: bool = True,
    priced_games: int | None = None,
) -> int:
    actionable_tags = {"BET", "MONITOR", "STRONG", "LEAN", "OVER", "UNDER", "EDGE"}
    actionable = [row for row in rows if str(row.get("lean") or "").upper() in actionable_tags]
    prop_sources = {"prop", "projection", "prizepicks", "underdog", "sleeper", "pickem"}
    prop_rows = [row for row in rows if str(row.get("source") or "").lower() in prop_sources]
    game_markets = {"ml", "total", "runline"}
    matchup_rows = [
        row for row in rows
        if str(row.get("source") or "").lower() == "matchup"
        and str(row.get("market") or "").lower() in game_markets
    ]
    min_actionable = int(os.getenv("LEAN_VERIFY_MIN_ACTIONABLE", "5"))
    min_props = int(os.getenv("LEAN_VERIFY_MIN_PROPS", "30"))
    min_matchup = int(os.getenv("LEAN_VERIFY_MIN_MATCHUP", "6"))

    if not rows:
        print(f"ERROR: no model_leans rows for slate {slate} ({origin})")
        return 1
    if len(prop_rows) < min_props:
        print(
            f"ERROR: only {len(prop_rows)} prop/projection leans for {slate} "
            f"(need >= {min_props})"
        )
        return 1
    if len(matchup_rows) < min_matchup:
        print(
            f"ERROR: only {len(matchup_rows)} moneyline/total/runline leans for {slate} "
            f"(need >= {min_matchup})"
        )
        return 1
    if len(actionable) < min_actionable:
        priced_note = "" if priced_games is None else f", {priced_games} priced game(s) in odds cache"
        if require_actionable:
            print(
                f"ERROR: only {len(actionable)} actionable market leans for {slate} "
                f"(need >= {min_actionable}{priced_note})"
            )
            return 1
        print(
            f"WARNING: only {len(actionable)} actionable market leans for {slate} "
            f"(need >= {min_actionable}{priced_note}); skipping priced-market gate "
            f"(no live/cached game lines for this slate — Odds API fetch skipped or snapshot stale)"
        )

    priced_txt = "" if priced_games is None else f", {priced_games} priced games"
    print(
        f"OK: {len(rows)} leans on {slate} via {origin} "
        f"({len(prop_rows)} props/projections, {len(matchup_rows)} ml/total/runline, "
        f"{len(actionable)} actionable market{priced_txt}, "
        f"{sum(1 for r in rows if r.get('settled'))} settled)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
