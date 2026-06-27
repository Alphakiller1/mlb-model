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

from mlbmodel import settings
from mlbmodel.baseball.model import normal_cdf
from mlbmodel.market.oddsmath import american_to_implied, devig_two_way
from mlbmodel.market.value import assess_value

API_MARKETS = {
    "pitcher_strikeouts": "K",
    "pitcher_walks": "BB",
    "pitcher_earned_runs": "ER",
    "pitcher_outs": "Outs",
}


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
        key = " ".join(str(player).lower().replace(".", "").split())
        return [
            quote
            for quote in self.quotes
            if " ".join(quote.player.lower().replace(".", "").split()) == key
        ]


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
        first_probability, second_probability = devig_two_way(
            american_to_implied(first["odds"]),
            american_to_implied(second["odds"]),
        )
        for row, probability in (
            (first, first_probability), (second, second_probability)
        ):
            key = (
                row["game"], row["player"], row["prop"], row["line"], row["side"],
            )
            probabilities.setdefault(key, []).append((row, probability))
    quotes = []
    for key, values in probabilities.items():
        best = max((row for row, _ in values), key=lambda row: row["odds"])
        sharp = [
            probability
            for row, probability in values
            if row["book"] in settings.SHARP_BOOKS
        ]
        soft = [
            probability
            for row, probability in values
            if row["book"] not in settings.SHARP_BOOKS
        ]
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
                    statistics.median(probability for _, probability in values), 6
                ),
                book_count=len(values),
                sharp_probability=round(statistics.median(sharp), 6) if sharp else None,
                soft_probability=round(statistics.median(soft), 6) if soft else None,
                fetched_at=fetched,
            )
        )
    return PropOddsBoard(quotes)


def fetch_prop_payloads(cache_path: Path | None = None) -> tuple[list[dict], str]:
    if not settings.ODDS_API_KEY:
        raise RuntimeError("ODDS_API_KEY is not configured")
    event_query = urllib.parse.urlencode(
        {"apiKey": settings.ODDS_API_KEY, "dateFormat": "iso"}
    )
    event_url = (
        f"{settings.ODDS_API_BASE}/sports/{settings.ODDS_SPORT_KEY}/events?"
        f"{event_query}"
    )
    with urllib.request.urlopen(event_url, timeout=30) as response:
        events = json.loads(response.read().decode("utf-8"))
    payloads = []
    markets = ",".join(API_MARKETS)
    regions = getattr(settings, "ODDS_PROP_REGIONS", "us")
    for event in events:
        query = urllib.parse.urlencode(
            {
                "apiKey": settings.ODDS_API_KEY,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "american",
                "dateFormat": "iso",
            }
        )
        url = (
            f"{settings.ODDS_API_BASE}/sports/{settings.ODDS_SPORT_KEY}/events/"
            f"{event['id']}/odds?{query}"
        )
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payloads.append(json.loads(response.read().decode("utf-8")))
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
) -> PropOddsBoard:
    path = cache_path or settings.CACHE_DIR / "prop_odds_latest.json"
    if fetch:
        try:
            payloads, fetched = fetch_prop_payloads(path)
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
        return build_prop_board(
            payload.get("events") or [],
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
        mean = float(projection["mean"])
        standard_deviation = max(0.2, float(projection["sd"]))
        p_over = 1 - normal_cdf((quote.line - mean) / standard_deviation)
        model_probability = p_over if quote.side == "over" else 1 - p_over
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
                "edge": assessment.edge,
                "ev": assessment.ev_per_unit,
                "fair_odds": assessment.fair_odds,
                "state": assessment.action,
                "reason": assessment.reason,
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
    args = parser.parse_args()
    board = load_prop_board(
        fetch=True,
        cache_path=Path(args.cache) if args.cache else None,
    )
    print(
        f"pitcher prop sides={len(board.quotes)}"
        + (f" error={board.error}" if board.error else "")
    )


if __name__ == "__main__":
    main()
