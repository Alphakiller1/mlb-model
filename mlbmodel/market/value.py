"""Market value, executable-price, and action-state calculations."""
from __future__ import annotations

from dataclasses import dataclass

from mlbmodel import settings
from mlbmodel.market.oddsmath import american_to_decimal, prob_to_american


@dataclass(frozen=True)
class ValueAssessment:
    model_probability: float
    market_probability: float | None
    edge: float | None
    ev_per_unit: float | None
    fair_odds: int
    maximum_odds: int
    raw_state: str
    action: str
    reason: str


def assess_value(
    model_probability: float,
    executable_odds: int | None,
    market_probability: float | None,
    *,
    promotion_status: str,
    signal_edge_boost: float = 0.0,
) -> ValueAssessment:
    fair = prob_to_american(model_probability)
    if executable_odds is None or market_probability is None:
        return ValueAssessment(
            model_probability, market_probability, None, None, fair, fair,
            "NO-PRICE", "NO EDGE", "No executable market pair is available",
        )

    edge = model_probability - market_probability + signal_edge_boost
    decimal = american_to_decimal(executable_odds)
    ev = model_probability * (decimal - 1) - (1 - model_probability)
    implausible = edge >= settings.IMPLAUSIBLE_EDGE
    raw_state = (
        "REVIEW" if implausible
        else "PLAY" if edge >= 0.02 and ev > 0
        else "PASS"
    )

    if promotion_status != "PROMOTE":
        action = "MONITOR" if edge > 0 and ev > 0 else "AVOID"
        reason = "Research signal only; the strategy has not passed its promotion gate"
    elif raw_state == "PLAY":
        action = "BET"
        reason = "Positive executable EV and the governing strategy is promoted"
    elif raw_state == "REVIEW":
        action = "REVIEW"
        reason = "The apparent edge is too large to trust without checking inputs"
    else:
        action = "AVOID"
        reason = "No positive executable edge"

    return ValueAssessment(
        model_probability=round(model_probability, 4),
        market_probability=round(market_probability, 4),
        edge=round(edge, 4),
        ev_per_unit=round(ev, 4),
        fair_odds=fair,
        maximum_odds=fair,
        raw_state=raw_state,
        action=action,
        reason=reason,
    )
