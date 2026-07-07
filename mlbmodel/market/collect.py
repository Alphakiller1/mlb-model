"""Collect paired market prices and publish sharp-vs-soft signals."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from mlbmodel import settings
from mlbmodel.baseball.repository import DataRepository
from mlbmodel.market.quotes import load_board
from mlbmodel.storage.supabase import SupabaseWriter


def signals_for_game(game, quotes) -> tuple[list[dict], list[dict]]:
    by_pair: dict[tuple, list] = {}
    for quote in quotes:
        if quote.sharp_divergence is None:
            continue
        pair = (quote.market, quote.line)
        by_pair.setdefault(pair, []).append(quote)

    signals, observations = [], []
    for pair_quotes in by_pair.values():
        best = max(pair_quotes, key=lambda quote: quote.sharp_divergence or -1)
        divergence = best.sharp_divergence or 0.0
        if not 0.02 <= divergence < 0.12:
            continue
        if best.sharp_book_count < 2 and divergence >= 0.06:
            continue
        signals.append({
            "game_pk": game.game_pk,
            "snapshot_time": best.fetched_at,
            "market_type": best.market,
            "selection": best.selection,
            "sharp_novig_prob": best.sharp_probability,
            "soft_novig_prob": best.soft_probability,
            "divergence": round(divergence, 4),
            "n_sharp_books": best.sharp_book_count,
            "n_soft_books": best.soft_book_count,
            "line_open": None,
            "line_current": best.best_odds,
            "line_delta": None,
            "steam_flag": False,
            "steam_books": None,
            "sharp_books_used": None,
            "source": "the-odds-api-unified",
        })
        side_role = (
            "over" if best.market == "total" and best.selection == "over"
            else "under" if best.market == "total"
            else "fav" if (best.soft_probability or 0) >= 0.5
            else "dog"
        )
        for book, probability in best.sharp_books:
            book_divergence = probability - (best.soft_probability or 0)
            if not 0.02 <= book_divergence < 0.12:
                continue
            observations.append({
                "game_pk": game.game_pk,
                "snapshot_time": best.fetched_at,
                "minutes_to_fp": None,
                "time_bucket": "pregame",
                "book": book,
                "market_type": best.market,
                "selection": best.selection,
                "line": best.line,
                "book_novig_prob": round(probability, 4),
                "soft_novig_prob": best.soft_probability,
                "divergence": round(book_divergence, 4),
                "side_role": side_role,
                "home_away": (
                    "home" if best.selection == game.home
                    else "away" if best.selection == game.away
                    else "na"
                ),
                "metric_version": settings.METRIC_VERSION,
            })
    return signals, observations


def run(*, data_dir=None, fetch=True) -> tuple[list[dict], list[dict]]:
    repo = DataRepository(data_dir)
    slate = repo.slate()
    if slate is None:
        raise RuntimeError("today_matchups.csv is unavailable")
    slate_date = str(slate.iloc[0].get("Slate_Date", ""))[:10] if len(slate) else ""
    cache_path = Path(data_dir) / "odds_latest.json" if data_dir else None
    board = load_board(fetch=fetch, cache_path=cache_path, slate_date=slate_date or None)
    signals, observations = [], []
    for _, row in slate.iterrows():
        away = str(row["Away"]).upper().strip()
        home = str(row["Home"]).upper().strip()
        game = repo.load_game(away, home)
        game_signals, game_observations = signals_for_game(
            game, board.game_quotes(away, home)
        )
        signals.extend(game_signals)
        observations.extend(game_observations)
    writer = SupabaseWriter()
    if signals and writer.url and writer.key:
        writer.insert("sharp_signals", signals)
    if observations and writer.url and writer.key:
        writer.insert("sharp_observations", observations)
    return signals, observations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(settings.DATA_DIR))
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    signals, observations = run(data_dir=args.data_dir, fetch=not args.no_fetch)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(
        f"{timestamp} sharp signals={len(signals)} "
        f"observations={len(observations)}"
    )


if __name__ == "__main__":
    main()
