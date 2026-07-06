"""Persist model leans from a report build (idempotent upsert)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from mlbmodel import settings
from mlbmodel.storage.supabase import SupabaseWriter

log = logging.getLogger(__name__)
MODEL_VERSION = settings.MODEL_VERSION


def _row(
    *,
    slate_date: str,
    game_pk: int | None,
    source: str,
    market: str,
    selection: str,
    line: float | None,
    model_value: float | None,
    model_prob: float | None,
    edge: float | None,
    lean: str,
    entry_odds: float | None = None,
    pitcher_name: str | None = None,
) -> dict:
    row = {
        "slate_date": slate_date,
        "game_pk": game_pk,
        "source": source,
        "market": market,
        "selection": selection,
        "line": line,
        "model_value": model_value,
        "model_prob": model_prob,
        "edge": edge,
        "lean": lean,
        "model_version": MODEL_VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "settled": False,
    }
    if entry_odds is not None:
        row["entry_odds"] = entry_odds
    if pitcher_name:
        row["pitcher_name"] = pitcher_name
    return row


def _market_line(play: dict) -> float | None:
    raw = play.get("market_line")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _entry_odds(play: dict) -> float | None:
    raw = play.get("entry_odds", play.get("price"))
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def collect_leans(
    *,
    slate_date: str,
    market_plays: list[dict],
    pickem_rows: list[dict],
    prop_reports: list[dict],
    pkmap: dict[int, str] | None = None,
) -> list[dict]:
    """Gather lean dicts from markets board, pick'em, and prop edges."""
    pkmap = pkmap or {}
    rows: list[dict] = []

    for play in market_plays:
        verdict = str(play.get("verdict") or "")
        if verdict not in {"STRONG", "BET", "LEAN"}:
            continue
        pk = play.get("pk")
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=int(pk) if pk is not None else None,
                source="sharp",
                market=str(play.get("mkt_type") or "market"),
                selection=str(play.get("sel") or ""),
                line=_market_line(play),
                entry_odds=_entry_odds(play),
                model_value=play.get("model_p"),
                model_prob=play.get("model_p"),
                edge=play.get("medge"),
                lean=verdict,
            )
        )

    for item in pickem_rows:
        lean = str(item.get("lean") or "").upper()
        if lean not in {"OVER", "UNDER"}:
            continue
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=item.get("game_pk"),
                source=str(item.get("book") or "pickem"),
                market=str(item.get("prop") or "prop"),
                selection=lean.lower(),
                line=float(item["line"]) if item.get("line") is not None else None,
                model_value=item.get("projection"),
                model_prob=item.get("p_over"),
                edge=item.get("edge_pts"),
                lean=lean,
                pitcher_name=str(item.get("pitcher") or "") or None,
            )
        )

    for item in prop_reports:
        state = str(item.get("state") or "")
        if state not in {"BET", "MONITOR"}:
            continue
        edge = item.get("edge")
        if edge is None or float(edge) < 0.01:
            continue
        rows.append(
            _row(
                slate_date=slate_date,
                game_pk=item.get("game_pk"),
                source="prop",
                market=str(item.get("prop") or "prop"),
                selection=str(item.get("side") or ""),
                line=float(item["line"]) if item.get("line") is not None else None,
                model_value=item.get("model_mean"),
                model_prob=item.get("model_probability"),
                edge=float(edge) * 100 if abs(float(edge)) <= 1 else float(edge),
                lean=state,
                entry_odds=float(item["best_odds"]) if item.get("best_odds") is not None else None,
                pitcher_name=str(item.get("pitcher") or "") or None,
            )
        )

    return rows


def record_leans(rows: list[dict], *, writer: SupabaseWriter | None = None) -> int:
    """Upsert leans; returns count written. Skips gracefully without credentials."""
    if not rows:
        return 0
    writer = writer or SupabaseWriter()
    if not writer.url or not writer.key:
        return 0
    return writer.upsert(
        "model_leans",
        rows,
        on_conflict="slate_date,game_pk,source,market,selection,line",
    )
