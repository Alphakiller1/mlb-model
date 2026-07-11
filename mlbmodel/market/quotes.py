"""Self-contained live odds ingestion with paired de-vigged consensus prices."""
from __future__ import annotations

import json
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from mlbmodel import settings
from mlbmodel.market import usage
from mlbmodel.market.oddsmath import american_to_implied, devig_two_way

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketQuote:
    market: str
    selection: str
    line: float | None
    best_odds: int
    best_book: str
    vigfree_probability: float
    hold: float | None
    book_count: int
    sharp_book_count: int
    soft_book_count: int
    sharp_books: tuple[tuple[str, float], ...]
    soft_books: tuple[tuple[str, float], ...]
    sharp_probability: float | None
    soft_probability: float | None
    fetched_at: str

    @property
    def sharp_divergence(self) -> float | None:
        if self.sharp_probability is None or self.soft_probability is None:
            return None
        return self.sharp_probability - self.soft_probability


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


class OddsBoard:
    def __init__(self, quotes: dict[tuple[str, str, str, float | None], MarketQuote]):
        self.quotes = quotes

    def quote(
        self,
        away: str,
        home: str,
        market: str,
        selection: str,
        line: float | None = None,
    ) -> MarketQuote | None:
        return self.quotes.get((f"{away}@{home}", market, selection, line))

    def modal_total(self, away: str, home: str) -> float | None:
        lines = [
            key[3]
            for key in self.quotes
            if key[0] == f"{away}@{home}" and key[1] == "total" and key[3] is not None
        ]
        return statistics.mode(lines) if lines else None

    def game_quotes(self, away: str, home: str) -> list[MarketQuote]:
        game = f"{away}@{home}"
        return [
            quote for key, quote in self.quotes.items()
            if key[0] == game
        ]


def _normalized_rows(events: list[dict], fetched_at: str) -> list[dict]:
    rows = []
    market_names = {
        "h2h": "ml", "spreads": "runline", "totals": "total",
        "h2h_1st_5_innings": "f5_ml", "totals_1st_5_innings": "f5_total",
        "spreads_1st_5_innings": "f5_runline",
    }
    for event in events:
        away = settings.team_abbr(event.get("away_team", ""))
        home = settings.team_abbr(event.get("home_team", ""))
        game = f"{away}@{home}"
        for bookmaker in event.get("bookmakers", []):
            book = str(bookmaker.get("key") or "")
            for market in bookmaker.get("markets", []):
                market_name = market_names.get(market.get("key"))
                if not market_name:
                    continue
                for outcome in market.get("outcomes", []):
                    raw_name = str(outcome.get("name") or "")
                    selection = (
                        settings.team_abbr(raw_name)
                        if market_name in {"ml", "runline", "f5_ml", "f5_runline"}
                        else raw_name.lower()
                    )
                    point = outcome.get("point")
                    line = float(point) if point is not None else None
                    rows.append({
                        "game": game,
                        "market": market_name,
                        "selection": selection,
                        "line": line,
                        "odds": int(outcome["price"]),
                        "book": book,
                        "fetched_at": fetched_at,
                    })
    return rows


def _pair_id(row: dict) -> tuple:
    # Totals (full-game and F5) pair by line; moneyline/runline pair without one.
    if row["market"] in {"total", "f5_total"}:
        return row["game"], row["book"], row["market"], row["line"]
    return row["game"], row["book"], row["market"], None


def build_board(events: list[dict], fetched_at: str | None = None) -> OddsBoard:
    fetched = fetched_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = _normalized_rows(events, fetched)
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault(_pair_id(row), []).append(row)

    novig: dict[tuple, list[tuple[dict, float, float]]] = {}
    for pair_rows in grouped.values():
        if len(pair_rows) != 2:
            continue
        first, second = pair_rows
        pa = american_to_implied(first["odds"])
        pb = american_to_implied(second["odds"])
        da, db = devig_two_way(pa, pb)
        # Two-sided hold (overround): how much vig the book bakes into BOTH sides. The
        # de-vigged probs already remove it; we carry it so the report can show the true
        # no-vig fair price next to the posted (juiced) number.
        hold = max(0.0, pa + pb - 1.0)
        novig.setdefault(
            (first["game"], first["market"], first["selection"], first["line"]), []
        ).append((first, da, hold))
        novig.setdefault(
            (second["game"], second["market"], second["selection"], second["line"]), []
        ).append((second, db, hold))

    quotes = {}
    for key, values in novig.items():
        best_row = max((row for row, _, _ in values), key=lambda row: row["odds"])
        all_probs = [probability for _, probability, _ in values]
        holds = [hold for _, _, hold in values]
        sharp_probs = [
            probability
            for row, probability, _ in values
            if row["book"] in settings.SHARP_BOOKS
        ]
        soft_probs = [
            probability
            for row, probability, _ in values
            if row["book"] not in settings.SHARP_BOOKS
        ]
        game, market, selection, line = key
        quotes[(game, market, selection, line)] = MarketQuote(
            market=market,
            selection=selection,
            line=line,
            best_odds=best_row["odds"],
            best_book=best_row["book"],
            vigfree_probability=round(float(statistics.median(all_probs)), 6),
            hold=round(float(statistics.median(holds)), 6) if holds else None,
            book_count=len(values),
            sharp_book_count=len(sharp_probs),
            soft_book_count=len(soft_probs),
            sharp_books=tuple(
                sorted(
                    (row["book"], probability)
                    for row, probability, _ in values
                    if row["book"] in settings.SHARP_BOOKS
                )
            ),
            soft_books=tuple(
                sorted(
                    (row["book"], probability)
                    for row, probability, _ in values
                    if row["book"] not in settings.SHARP_BOOKS
                )
            ),
            sharp_probability=round(float(_median(sharp_probs)), 6) if sharp_probs else None,
            soft_probability=round(float(_median(soft_probs)), 6) if soft_probs else None,
            fetched_at=fetched,
        )
    return OddsBoard(quotes)


def fetch_events(*, cache_path: Path | None = None) -> tuple[list[dict], str]:
    if not settings.ODDS_API_KEY:
        raise RuntimeError("ODDS_API_KEY is not configured")
    params = urllib.parse.urlencode({
        "apiKey": settings.ODDS_API_KEY,
        "regions": settings.ODDS_REGIONS,
        "markets": settings.ODDS_GAME_MARKETS,
        "oddsFormat": "american",
        "dateFormat": "iso",
    })
    url = f"{settings.ODDS_API_BASE}/sports/{settings.ODDS_SPORT_KEY}/odds?{params}"
    with urllib.request.urlopen(url, timeout=30) as response:
        events = json.loads(response.read().decode())
        usage.record(response, "game-lines")
    if settings.ODDS_F5_ENABLED and isinstance(events, list):
        # Best-effort and fully isolated: F5 is an add-on, it must never break (or block the
        # caching of) the core full-game odds.
        try:
            _merge_f5_markets(events)
        except Exception:
            pass
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = cache_path or settings.CACHE_DIR / "odds_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": fetched, "events": events}), encoding="utf-8")
    return events, fetched


def _merge_f5_markets(events: list[dict]) -> None:
    """Fetch first-5-innings odds per event and merge them into each event's bookmakers.

    F5 markets are "additional markets" only served by the per-event endpoint, so this costs
    one extra call per game. Best-effort: any failure leaves the event with its full-game
    markets only (F5 then falls back to model fair values downstream).
    """
    base = f"{settings.ODDS_API_BASE}/sports/{settings.ODDS_SPORT_KEY}/events"
    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        params = urllib.parse.urlencode({
            "apiKey": settings.ODDS_API_KEY,
            "regions": settings.ODDS_REGIONS,
            "markets": settings.ODDS_F5_MARKETS,
            "oddsFormat": "american",
            "dateFormat": "iso",
        })
        try:
            with urllib.request.urlopen(f"{base}/{event_id}/odds?{params}", timeout=30) as response:
                payload = json.loads(response.read().decode())
                usage.record(response, "f5")
        except Exception:
            continue
        # Merge the F5 markets into the matching bookmaker entries already on the event.
        existing = {bm.get("key"): bm for bm in event.get("bookmakers", [])}
        for book in payload.get("bookmakers", []):
            key = book.get("key")
            target = existing.get(key)
            if target is None:
                event.setdefault("bookmakers", []).append(book)
                existing[key] = book
            else:
                target.setdefault("markets", []).extend(book.get("markets", []))


def filter_events_for_slate(events: list[dict], slate_date: str | None) -> list[dict]:
    """Keep only Odds API events whose first pitch falls on the slate day (US/Eastern)."""
    if not slate_date:
        return events
    kept: list[dict] = []
    for event in events:
        commence = str(event.get("commence_time") or "").strip()
        if not commence:
            continue
        when = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when.astimezone(ET).date().isoformat() == slate_date:
            kept.append(event)
    return kept


def load_cached_events(cache_path: Path | None = None) -> tuple[list[dict], str]:
    path = cache_path or settings.CACHE_DIR / "odds_latest.json"
    if not path.exists():
        return [], ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("events", []), str(payload.get("fetched_at") or "")


def load_board(
    *,
    fetch: bool = False,
    cache_path: Path | None = None,
    slate_date: str | None = None,
) -> OddsBoard:
    if fetch:
        try:
            events, fetched = fetch_events(cache_path=cache_path)
            events = filter_events_for_slate(events, slate_date)
            return build_board(events, fetched)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            pass
    events, fetched = load_cached_events(cache_path)
    events = filter_events_for_slate(events, slate_date)
    return build_board(events, fetched) if events else OddsBoard({})
