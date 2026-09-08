"""Machine-readable slate export for downstream systems.

The dashboard HTML is a rendered page. This module is the contract the content
engine reads: `board.json` (slate), `build.json` (data freshness), `record.json`
(graded ledger). Field names follow the NFL/CFB publication bundle.

`schema` is versioned; add fields freely, rename or remove them only with a
version bump.

Picks / Gems semantics are the Board kernel's, not a second definition:

* **priced_markets** — tiles with a matched book price (`Tile.priced` /
  `Group.priced`). A model probability with no book price is not a pick.
* **flagged_tiles** — priced tiles with edge >= 3.0 and state in {BET, MONITOR}
  (`board.py` GEM_EDGE_PTS / GEM_STATES). UI labels stay "Picks" / "Gems".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mlbmodel.leans.calibration import record_from_rows, summarize_record
from mlbmodel.report.board import GEM_EDGE_PTS, GEM_STATES, Board


SCHEMA = "mlb-model/board/1"


def _stamp() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _tile_row(card, group, tile) -> dict:
    return {
        "game": card.key,
        "away": card.away.abbr,
        "home": card.home.abbr,
        "group": group.label,
        "group_tag": group.tag,
        "label": tile.label,
        "value": tile.value,
        "state": tile.state,
        "priced": bool(tile.priced),
        "gem": bool(tile.gem),
        "note": tile.note,
    }


def _iter_tiles(board: Board):
    for card in board.cards:
        for group in card.groups:
            for tile in group.tiles:
                yield card, group, tile


def payload(
    board: Board,
    *,
    gate: dict | None = None,
    slate_date: str | None = None,
    generated_at: datetime | None = None,
) -> dict:
    """Serialize the live Board kernel — the same object the HTML counts Picks/Gems from."""
    gate = gate or {}
    verdict = str(gate.get("verdict") or "HOLD/ABSTAIN")
    reasons = list(gate.get("reasons") or [])
    stamp = generated_at or _stamp()
    tiles = [_tile_row(card, group, tile) for card, group, tile in _iter_tiles(board)]
    priced = [row for row in tiles if row["priced"]]
    flagged = [row for row in priced if row["gem"]]
    return {
        "schema": SCHEMA,
        "sport": "mlb",
        "generated_at_utc": _iso(stamp),
        "slate_date": slate_date,
        "authority": verdict,
        "may_bet": verdict == "PROMOTE",
        "unmet_gates": reasons,
        "evidence": "mlbmodel.quant.promotion_gate.promotion_verdict",
        "gem_edge_pts": GEM_EDGE_PTS,
        "gem_states": sorted(GEM_STATES),
        "picks": board.picks,
        "gems": board.gems,
        "priced_markets": priced,
        "flagged_tiles": flagged,
        "games": [
            {
                "key": card.key,
                "away": card.away.abbr,
                "home": card.home.abbr,
                "projected_away": card.away.score,
                "projected_home": card.home.score,
                "start": card.start_text,
                "headline": card.headline,
                "picks": card.picks,
                "gems": card.gems,
            }
            for card in board.cards
        ],
    }


def health(
    *,
    data_dir: Path | None = None,
    sync: dict | None = None,
    odds_status: dict | None = None,
    issues: list[str] | None = None,
    slate_date: str | None = None,
    generated_at: datetime | None = None,
) -> dict:
    """DataStatus-shaped manifest (NFL/CFB `build.json` field contract)."""
    stamp = generated_at or _stamp()
    sources: list[dict] = []
    if data_dir is not None:
        data_dir = Path(data_dir)
        for name in (
            "today_matchups.csv",
            "game_results.csv",
            "odds_latest.json",
            "model_leans_latest.json",
            "mlbma_sync.json",
        ):
            path = data_dir / name
            rows = None
            if path.exists() and path.suffix == ".csv":
                try:
                    rows = sum(1 for _ in path.open(encoding="utf-8")) - 1
                except OSError:
                    rows = None
            elif path.exists() and path.name == "model_leans_latest.json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    rows = int(payload.get("count") or len(payload.get("rows") or []))
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    rows = None
            sources.append({
                "name": name,
                "exists": path.exists(),
                "rows": rows,
                "state": "fresh" if path.exists() else "missing",
            })
    problem_list = list(issues or [])
    sync = sync or {}
    if sync.get("status") not in {None, "exact", "ok", "fresh"} and sync:
        if sync.get("status") == "fallback":
            problem_list.append("MLBMA sync used a live fallback slate")
        elif sync.get("message"):
            problem_list.append(str(sync["message"]))
    odds = dict(odds_status or {})
    if not odds:
        odds = {"state": "unknown", "requested_book": "draftkings"}
    return {
        "state": "fresh" if not problem_list else "degraded",
        "generated_at": stamp.strftime("%Y-%m-%d %H:%M UTC"),
        "slate_date": slate_date,
        "sources": sources,
        "odds": odds,
        "sync": {
            "status": sync.get("status"),
            "message": sync.get("message"),
            "game_count": sync.get("game_count"),
        },
        "issues": list(dict.fromkeys(problem_list)),
    }


def record_payload(
    *,
    gate: dict | None = None,
    ledger: dict | None = None,
    leans: list[dict] | None = None,
) -> dict:
    """ModelStatus / results ledger (NFL/CFB `record.json` field contract)."""
    gate = gate or {}
    ledger = ledger or {}
    verdict = str(gate.get("verdict") or "HOLD/ABSTAIN")
    reasons = list(gate.get("reasons") or [])
    rows = leans or []
    rec = record_from_rows(rows) if rows else {
        "total": 0, "wins": 0, "losses": 0, "pushes": 0, "hit_rate": None,
    }
    summary = summarize_record(rows) if rows else {}
    return {
        "scope": "local prediction ledger + settled model_leans when present",
        "authority": "shadow_only" if verdict != "PROMOTE" else verdict,
        "may_bet": verdict == "PROMOTE",
        "unmet_gates": reasons,
        "promotion": verdict,
        "games_graded": int(ledger.get("graded") or rec.get("total") or 0),
        "pending_snapshots": int(ledger.get("pending") or 0),
        "model_mae": None,
        "consensus_mae": None,
        "book_mae": None,
        "ats": {
            "win": int(rec.get("wins") or 0),
            "loss": int(rec.get("losses") or 0),
            "push": int(rec.get("pushes") or 0),
        },
        "totals": {"win": 0, "loss": 0, "push": 0},
        "hit_rate": rec.get("hit_rate"),
        "brier": summary.get("brier") if summary else None,
    }


def write(payload_dict: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload_dict, indent=2) + "\n", encoding="utf-8")
    return out


def write_bundle(
    site_dir: Path,
    *,
    board: Board,
    gate: dict | None = None,
    sync: dict | None = None,
    data_dir: Path | None = None,
    slate_date: str | None = None,
    ledger: dict | None = None,
    leans: list[dict] | None = None,
    odds_status: dict | None = None,
    issues: list[str] | None = None,
) -> dict[str, Path]:
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    board_path = write(
        payload(board, gate=gate, slate_date=slate_date),
        site_dir / "board.json",
    )
    build_path = write(
        health(
            data_dir=data_dir,
            sync=sync,
            odds_status=odds_status,
            issues=issues,
            slate_date=slate_date,
        ),
        site_dir / "build.json",
    )
    record_path = write(
        record_payload(gate=gate, ledger=ledger, leans=leans),
        site_dir / "record.json",
    )
    return {"board": board_path, "build": build_path, "record": record_path}
