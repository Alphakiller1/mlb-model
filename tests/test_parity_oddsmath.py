"""Migration parity gate (consolidation charter, deliverable 9).

Proves the unified mlbmodel.market.oddsmath is behavior-identical to the LEGACY
bet_evaluator implementation on identical inputs. This is a *migration-period* test: it
skips cleanly when the legacy repo isn't importable (e.g. CI, or after the legacy repo is
archived). Point BET_EVALUATOR_PATH at the legacy checkout to run it locally.

Run locally with the legacy venv (has pandas/config):
    cd <bet-evaluator> && PYTHONPATH=<mlb-model> .venv/bin/python -m pytest \
        <mlb-model>/tests/test_parity_oddsmath.py
"""
import os
import sys

import pytest

from mlbmodel.market.oddsmath import (
    american_to_implied, american_to_decimal, prob_to_american,
)

_LEGACY = os.environ.get(
    "BET_EVALUATOR_PATH",
    "/Users/chase/Projects/SCL/_github-repos/bet-evaluator",
)


def _legacy():
    if _LEGACY not in sys.path:
        sys.path.insert(0, _LEGACY)
    try:
        import bet_evaluator  # noqa: requires legacy deps (pandas/config)
        return bet_evaluator
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"legacy bet_evaluator not importable here ({exc}) — parity skipped")


def test_oddsmath_parity_vs_legacy():
    L = _legacy()
    for o in range(-1000, 1001):
        if o == 0:
            continue
        assert abs(L.american_to_implied(o) - american_to_implied(o)) < 1e-12, o
        assert abs(L.american_to_decimal(o) - american_to_decimal(o)) < 1e-12, o
    for o in (-300, -150, -110, 110, 150, 300):
        assert L.prob_to_american(L.american_to_implied(o)) == \
            prob_to_american(american_to_implied(o)), o
