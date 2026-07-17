"""Closing-odds capture for model leans.

Each report build refreshes the `closing_odds` of today's still-unsettled leans
with the latest matched market price; the last pre-game build therefore leaves
the de-facto closing line on every lean. Settlement then computes
``clv_pts = implied(closing) − implied(entry)`` (positive = beat the close) —
the fastest-converging honest signal of pick quality.
"""
from __future__ import annotations

import logging

from mlbmodel.storage.supabase import SupabaseReader, SupabaseWriter

log = logging.getLogger(__name__)


def _line_key(value) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _odds_value(raw):
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_price_index(
    *,
    market_plays: list[dict] | None = None,
    matchup_markets_by_pk: dict[int, list[dict]] | None = None,
    prop_reports: list[dict] | None = None,
) -> dict[tuple, float]:
    """Current prices keyed the same way leans are recorded."""
    index: dict[tuple, float] = {}
    for play in market_plays or []:
        odds = _odds_value(play.get("entry_odds", play.get("price")))
        pk = play.get("pk")
        if odds is None or pk is None:
            continue
        key = (
            "sharp", int(pk), str(play.get("mkt_type") or "market").lower(),
            str(play.get("sel") or "").lower(), _line_key(play.get("market_line")),
        )
        index[key] = odds
    for pk, markets in (matchup_markets_by_pk or {}).items():
        if pk is None:
            continue
        for market in markets or []:
            odds = _odds_value(market.get("mkt"))
            if odds is None:
                continue
            market_type = str(market.get("market") or "market").lower()
            source = "f5" if market_type.startswith("f5_") else "matchup"
            key = (
                source, int(pk), market_type,
                str(market.get("side") or "").lower(), _line_key(market.get("line")),
            )
            index[key] = odds
    for report in prop_reports or []:
        odds = _odds_value(report.get("best_odds"))
        pk = report.get("game_pk")
        if odds is None or pk is None:
            continue
        key = (
            "prop", int(pk), str(report.get("prop") or "prop").lower(),
            str(report.get("side") or "").lower(), _line_key(report.get("line")),
        )
        index[key] = odds
    return index


def update_closing_odds(
    *,
    slate_date: str,
    price_index: dict[tuple, float],
    reader: SupabaseReader | None = None,
    writer: SupabaseWriter | None = None,
) -> int:
    """Refresh closing_odds on today's unsettled leans from the current prices."""
    if not price_index:
        return 0
    reader = reader or SupabaseReader()
    writer = writer or SupabaseWriter()
    if not writer.url or not writer.key:
        return 0
    pending = reader.get(
        f"model_leans?settled=eq.false&slate_date=eq.{str(slate_date)[:10]}"
        "&select=lean_id,game_pk,source,market,selection,line,closing_odds&limit=2000"
    )
    if pending.error:
        log.warning("closing-odds refresh skipped: %s", pending.error)
        return 0
    updated = 0
    for lean in pending.rows:
        pk = lean.get("game_pk")
        if pk is None:
            continue
        key = (
            str(lean.get("source") or "").lower(), int(pk),
            str(lean.get("market") or "").lower(),
            str(lean.get("selection") or "").lower(), _line_key(lean.get("line")),
        )
        odds = price_index.get(key)
        if odds is None:
            continue
        current = _odds_value(lean.get("closing_odds"))
        if current is not None and abs(current - odds) < 1e-9:
            continue
        writer.update(
            "model_leans", f"lean_id=eq.{lean['lean_id']}", {"closing_odds": odds}
        )
        updated += 1
    if updated:
        log.info("closing odds refreshed on %s lean(s) for %s", updated, slate_date)
    return updated
