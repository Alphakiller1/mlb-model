"""Odds API credit-usage accounting.

The Odds API returns three headers on every odds request:
  x-requests-last       — credits this request cost (markets x regions)
  x-requests-used       — credits used this billing period
  x-requests-remaining  — credits left this billing period

We were flying blind on burn vs. the monthly cap. ``record`` reads those headers off a
``urllib`` response, logs the per-call cost, and keeps a per-process running total so a full
pipeline run reports what it spent. Never raises — accounting must not break a fetch.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mlbmodel.odds.usage")

# Per-process running total of x-requests-last across every odds call this run.
_run_total = 0


def _header(headers: Any, name: str) -> str | None:
    try:
        return headers.get(name)
    except Exception:
        return None


def record(response: Any, label: str) -> int | None:
    """Log the credit cost of one Odds API response; return its x-requests-last (or None).

    ``response`` is a urllib HTTPResponse (``response.headers``). Safe on any object.
    """
    global _run_total
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    last = _header(headers, "x-requests-last")
    used = _header(headers, "x-requests-used")
    remaining = _header(headers, "x-requests-remaining")
    cost: int | None = None
    try:
        cost = int(last) if last is not None else None
    except (TypeError, ValueError):
        cost = None
    if cost is not None:
        _run_total += cost
    logger.info(
        "odds api %s: cost=%s used=%s remaining=%s (run total=%s)",
        label, last, used, remaining, _run_total,
    )
    # Also surface on stdout so it shows in pipeline/deploy logs without log config.
    print(
        f"  [odds] {label}: cost={last} used={used} remaining={remaining} "
        f"(run total={_run_total})",
        flush=True,
    )
    return cost


def run_total() -> int:
    """Credits spent by this process so far (sum of x-requests-last)."""
    return _run_total
