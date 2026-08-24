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

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
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


class OddsBudgetExhausted(RuntimeError):
    """Raised instead of spending credits when the key is at or below its configured floor.

    Subclasses RuntimeError so the existing fetch-then-fall-back-to-cache handlers treat a
    budget stop exactly like any other fetch failure: the board loads from the last snapshot
    instead of the run dying or silently draining the key.
    """


# Per-process cache of the free quota probe. False = not yet probed this run.
_remaining_cache: Any = False


def remaining_credits(*, refresh: bool = False) -> int | None:
    """Credits left on the configured key, or None if unknown.

    Uses /v4/sports, which the Odds API serves for FREE (it costs no credit but still carries
    the x-requests-remaining header). Cached per process so a pipeline that fetches several
    times probes once. Never raises — an unknown budget must not block a fetch.
    """
    global _remaining_cache
    if _remaining_cache is not False and not refresh:
        return _remaining_cache
    from mlbmodel import settings

    _remaining_cache = None
    if not settings.ODDS_API_KEY:
        return None
    params = urllib.parse.urlencode({"apiKey": settings.ODDS_API_KEY})
    try:
        with urllib.request.urlopen(
            f"{settings.ODDS_API_BASE}/sports?{params}", timeout=20
        ) as response:
            response.read()
            value = _header(response.headers, "x-requests-remaining")
        _remaining_cache = int(float(value)) if value is not None else None
    except (OSError, urllib.error.URLError, TypeError, ValueError, json.JSONDecodeError):
        _remaining_cache = None
    return _remaining_cache


def check_budget(label: str) -> None:
    """Raise OddsBudgetExhausted when spending would take the key below its floor.

    No-op when the floor is unset (0) or the remaining budget could not be determined.
    """
    from mlbmodel import settings

    floor = settings.ODDS_API_MIN_REMAINING
    if floor <= 0:
        return
    remaining = remaining_credits()
    if remaining is None or remaining >= floor:
        return
    message = (
        f"skipping {label}: {remaining} Odds API credits left, "
        f"below the ODDS_API_MIN_REMAINING={floor} floor"
    )
    logger.warning(message)
    print(f"  [odds] {message}", flush=True)
    raise OddsBudgetExhausted(message)
