"""Paired, de-vigged pitcher-prop prices from The Odds API event endpoint."""
from __future__ import annotations

import argparse
import json
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from mlbmodel import settings
from mlbmodel.market.probability import p_over_exact
from mlbmodel.props import matrix
from mlbmodel.market import usage
from mlbmodel.market.prizepicks import normalize_name
from mlbmodel.market.oddsmath import (
    american_to_implied,
    devig_two_way,
    prob_to_american,
)
from mlbmodel.market.value import assess_value

API_MARKETS = {
    "pitcher_strikeouts": "K",
    "pitcher_walks": "BB",
    "pitcher_earned_runs": "ER",
    "pitcher_outs": "Outs",
}

# K and BB are the two markets where the rebuilt projection has beaten the
# sportsbook line on the settled ledger. They are the minimum useful live-price
# tier when quota is tight. ER can be added with more headroom; Outs is omitted
# from edge-priced refreshes because the market has out-forecast this model.
EDGE_API_MARKETS = ("pitcher_strikeouts", "pitcher_walks")
EXTENDED_EDGE_API_MARKETS = (*EDGE_API_MARKETS, "pitcher_earned_runs")


@dataclass(frozen=True)
class PropQuote:
    game: str
    player: str
    prop: str
    line: float
    side: str
    best_odds: int
    best_book: str
    no_vig_probability: float
    hold: float | None
    book_count: int
    sharp_probability: float | None
    soft_probability: float | None
    fetched_at: str

    @property
    def sharp_divergence(self) -> float | None:
        if self.sharp_probability is None or self.soft_probability is None:
            return None
        return self.sharp_probability - self.soft_probability


class PropOddsBoard:
    def __init__(self, quotes: list[PropQuote], error: str | None = None):
        self.quotes = quotes
        self.error = error

    def for_player(self, player: str) -> list[PropQuote]:
        key = normalize_name(player)
        return [
            quote
            for quote in self.quotes
            if normalize_name(quote.player) == key
        ]


ET = ZoneInfo("America/New_York")


def filter_events_for_slate(
    events: list[dict],
    slate_date: str | None,
) -> list[dict]:
    """Keep prop events whose first pitch falls on the active ET slate."""
    if not slate_date:
        return events
    kept = []
    for event in events:
        commence = str(event.get("commence_time") or "").strip()
        if not commence:
            continue
        try:
            when = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when.astimezone(ET).date().isoformat() == slate_date:
            kept.append(event)
    return kept


def _normalize_payloads(payloads: list[dict], fetched_at: str) -> list[dict]:
    rows = []
    for event in payloads:
        away = settings.team_abbr(event.get("away_team", ""))
        home = settings.team_abbr(event.get("home_team", ""))
        game = f"{away}@{home}"
        for bookmaker in event.get("bookmakers") or []:
            book = str(bookmaker.get("key") or "")
            for market in bookmaker.get("markets") or []:
                prop = API_MARKETS.get(str(market.get("key") or ""))
                if not prop:
                    continue
                for outcome in market.get("outcomes") or []:
                    point = outcome.get("point")
                    player = str(outcome.get("description") or "").strip()
                    side = str(outcome.get("name") or "").lower().strip()
                    if point is None or not player or side not in {"over", "under"}:
                        continue
                    rows.append(
                        {
                            "game": game,
                            "player": player,
                            "prop": prop,
                            "line": float(point),
                            "side": side,
                            "odds": int(outcome["price"]),
                            "book": book,
                            "fetched_at": fetched_at,
                        }
                    )
    return rows


def build_prop_board(
    payloads: list[dict],
    fetched_at: str | None = None,
) -> PropOddsBoard:
    fetched = fetched_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = _normalize_payloads(payloads, fetched)
    pairs: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (
            row["game"], row["book"], row["player"], row["prop"], row["line"],
        )
        pairs.setdefault(key, []).append(row)
    probabilities: dict[tuple, list[tuple[dict, float]]] = {}
    for pair in pairs.values():
        if len(pair) != 2 or {row["side"] for row in pair} != {"over", "under"}:
            continue
        first, second = pair
        implied_first = american_to_implied(first["odds"])
        implied_second = american_to_implied(second["odds"])
        first_probability, second_probability = devig_two_way(
            implied_first, implied_second
        )
        # Two-sided hold (overround) on this over/under pair.
        hold = max(0.0, implied_first + implied_second - 1.0)
        for row, probability in (
            (first, first_probability), (second, second_probability)
        ):
            key = (
                row["game"], row["player"], row["prop"], row["line"], row["side"],
            )
            probabilities.setdefault(key, []).append((row, probability, hold))
    quotes = []
    for key, values in probabilities.items():
        best = max((row for row, _, _ in values), key=lambda row: row["odds"])
        sharp = [
            probability
            for row, probability, _ in values
            if row["book"] in settings.SHARP_BOOKS
        ]
        soft = [
            probability
            for row, probability, _ in values
            if row["book"] not in settings.SHARP_BOOKS
        ]
        holds = [hold for _, _, hold in values]
        game, player, prop, line, side = key
        quotes.append(
            PropQuote(
                game=game,
                player=player,
                prop=prop,
                line=line,
                side=side,
                best_odds=best["odds"],
                best_book=best["book"],
                no_vig_probability=round(
                    statistics.median(probability for _, probability, _ in values), 6
                ),
                hold=round(float(statistics.median(holds)), 6) if holds else None,
                book_count=len(values),
                sharp_probability=round(statistics.median(sharp), 6) if sharp else None,
                soft_probability=round(statistics.median(soft), 6) if soft else None,
                fetched_at=fetched,
            )
        )
    return PropOddsBoard(quotes)


def fetch_prop_payloads(
    cache_path: Path | None = None,
    *,
    slate_date: str | None = None,
    markets: tuple[str, ...] | None = None,
) -> tuple[list[dict], str]:
    if not settings.ODDS_API_KEY:
        raise RuntimeError("ODDS_API_KEY is not configured")
    # Props are the expensive fetch (one call per game), so guard before the event list.
    usage.check_budget("props")
    event_query = urllib.parse.urlencode(
        {"apiKey": settings.ODDS_API_KEY, "dateFormat": "iso"}
    )
    event_url = (
        f"{settings.ODDS_API_BASE}/sports/{settings.ODDS_SPORT_KEY}/events?"
        f"{event_query}"
    )
    with urllib.request.urlopen(event_url, timeout=30) as response:
        events = json.loads(response.read().decode("utf-8"))
    # The event list includes future slates. Additional markets are billed per
    # event, so filtering after the requests burns credits on games the report
    # immediately discards. Bound paid calls to the active Eastern-date slate.
    events = filter_events_for_slate(events, slate_date)
    payloads = []
    market_keys = tuple(dict.fromkeys(markets or tuple(API_MARKETS)))
    invalid_markets = sorted(set(market_keys) - set(API_MARKETS))
    if not market_keys or invalid_markets:
        raise ValueError(
            "prop markets must be a non-empty subset of API_MARKETS; invalid="
            + ",".join(invalid_markets)
        )
    requested_markets = ",".join(market_keys)
    regions = getattr(settings, "ODDS_PROP_REGIONS", "us")
    for event in events:
        query_params = {
            "apiKey": settings.ODDS_API_KEY,
            "regions": regions,
            "markets": requested_markets,
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        if settings.ODDS_BOOKMAKERS:
            query_params["bookmakers"] = settings.ODDS_BOOKMAKERS
        query = urllib.parse.urlencode(query_params)
        url = (
            f"{settings.ODDS_API_BASE}/sports/{settings.ODDS_SPORT_KEY}/events/"
            f"{event['id']}/odds?{query}"
        )
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payloads.append(json.loads(response.read().decode("utf-8")))
                usage.record(response, "props")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = cache_path or settings.CACHE_DIR / "prop_odds_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": fetched, "events": payloads}),
        encoding="utf-8",
    )
    return payloads, fetched


def load_prop_board(
    *,
    fetch: bool = False,
    cache_path: Path | None = None,
    slate_date: str | None = None,
    markets: tuple[str, ...] | None = None,
) -> PropOddsBoard:
    path = cache_path or settings.CACHE_DIR / "prop_odds_latest.json"
    if fetch:
        try:
            payloads, fetched = fetch_prop_payloads(
                path,
                slate_date=slate_date,
                markets=markets,
            )
            payloads = filter_events_for_slate(payloads, slate_date)
            return build_prop_board(payloads, fetched)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            fetch_error = str(exc)
        else:  # pragma: no cover
            fetch_error = None
    else:
        fetch_error = None
    if not path.exists():
        return PropOddsBoard([], fetch_error or "No pitcher-prop price snapshot is loaded.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = filter_events_for_slate(payload.get("events") or [], slate_date)
        if slate_date and not events:
            return PropOddsBoard(
                [],
                f"No pitcher-prop prices are loaded for {slate_date}.",
            )
        return build_prop_board(
            events,
            str(payload.get("fetched_at") or ""),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return PropOddsBoard([], str(exc))


def market_report(
    pitcher: dict,
    board: PropOddsBoard,
    *,
    promotion_status: str = "HOLD/ABSTAIN",
) -> list[dict]:
    reports = []
    projections = pitcher.get("projections") or {}
    for quote in board.for_player(pitcher.get("pitcher", "")):
        projection = projections.get(quote.prop)
        if not projection:
            continue
        # Price the distribution the simulation actually drew, not a normal refitted to its
        # first two moments. On a half-point line push is zero; on a whole number it is not,
        # and the under must not silently absorb it.
        p_over, p_push = p_over_exact(quote.line, projection)
        model_probability = p_over if quote.side == "over" else 1 - p_over - p_push
        # Where the book's line has been measured to out-forecast this model, the projection
        # still shows but cannot be sold as value — see matrix.MARKET_OUTFORECASTS_MODEL.
        actionable = matrix.market_is_actionable(quote.prop)
        assessment = assess_value(
            model_probability,
            quote.best_odds,
            quote.no_vig_probability,
            promotion_status=promotion_status,
        )
        reports.append(
            {
                "prop": quote.prop,
                "side": quote.side,
                "line": quote.line,
                "best_odds": quote.best_odds,
                "best_book": quote.best_book,
                "books": quote.book_count,
                "model_probability": round(model_probability, 4),
                "market_probability": quote.no_vig_probability,
                "market_fair_odds": prob_to_american(quote.no_vig_probability),
                "hold": (
                    round(quote.hold * 100, 1) if quote.hold is not None else None
                ),
                "edge": assessment.edge,
                "ev": assessment.ev_per_unit,
                "fair_odds": assessment.fair_odds,
                "state": assessment.action if actionable else "NO EDGE",
                "market_outforecasts_model": not actionable,
                "reason": (
                    assessment.reason if actionable else
                    "The posted line out-forecasts this model on this market "
                    "(measured on the settled ledger), so a disagreement here is "
                    "read as model error, not value"
                ),
                "sharp_divergence": quote.sharp_divergence,
                "fetched_at": quote.fetched_at,
            }
        )
    return sorted(
        reports,
        key=lambda row: (
            -(row.get("edge") or -1),
            row["prop"],
            row["side"],
        ),
    )


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="Refresh paired pitcher-prop prices from The Odds API."
    )
    parser.add_argument("--cache")
    parser.add_argument(
        "--slate-date",
        help="Eastern-date slate (YYYY-MM-DD); paid event calls are limited to this date",
    )
    parser.add_argument(
        "--markets",
        help="Comma-separated API market keys; defaults to every supported market",
    )
    args = parser.parse_args()
    markets = (
        tuple(key.strip() for key in args.markets.split(",") if key.strip())
        if args.markets
        else None
    )
    board = load_prop_board(
        fetch=True,
        cache_path=Path(args.cache) if args.cache else None,
        slate_date=args.slate_date,
        markets=markets,
    )
    print(
        f"pitcher prop sides={len(board.quotes)}"
        + (f" error={board.error}" if board.error else "")
    )


if __name__ == "__main__":
    main()
