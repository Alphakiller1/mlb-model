"""Conservative paper-bankroll sizing and correlated exposure summaries."""
from __future__ import annotations

from dataclasses import dataclass

from mlbmodel.market.oddsmath import american_to_decimal


@dataclass(frozen=True)
class PortfolioSummary:
    open_positions: int
    total_units_at_risk: float
    games_exposed: int
    largest_game_exposure: float
    concentrated_games: tuple[int, ...]


def fractional_kelly(
    probability: float,
    odds: int,
    *,
    fraction: float = 0.25,
    bankroll_cap: float = 0.02,
    promoted: bool = False,
) -> float:
    """Return a bankroll fraction; unpromoted strategies always return zero."""
    if not promoted:
        return 0.0
    decimal = american_to_decimal(odds)
    profit = decimal - 1
    full_kelly = (profit * probability - (1 - probability)) / profit
    return round(max(0.0, min(bankroll_cap, full_kelly * fraction)), 4)


def summarize_positions(
    positions: list[dict],
    *,
    game_concentration_limit: float = 2.0,
) -> PortfolioSummary:
    by_game: dict[int, float] = {}
    total = 0.0
    for position in positions:
        units = float(position.get("stake_units") or 0)
        game_pk = int(position["game_pk"])
        total += units
        by_game[game_pk] = by_game.get(game_pk, 0.0) + units
    largest = max(by_game.values(), default=0.0)
    concentrated = tuple(
        sorted(game_pk for game_pk, units in by_game.items()
               if units > game_concentration_limit)
    )
    return PortfolioSummary(
        open_positions=len(positions),
        total_units_at_risk=round(total, 2),
        games_exposed=len(by_game),
        largest_game_exposure=round(largest, 2),
        concentrated_games=concentrated,
    )
