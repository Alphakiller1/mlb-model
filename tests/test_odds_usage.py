"""Odds API usage accounting: accumulates x-requests-last, tolerates missing headers."""
import pytest

from mlbmodel.market import usage


class _Resp:
    def __init__(self, headers):
        self.headers = headers


def test_record_accumulates_cost_across_calls(monkeypatch):
    monkeypatch.setattr(usage, "_run_total", 0)
    c1 = usage.record(_Resp({"x-requests-last": "6", "x-requests-used": "100",
                             "x-requests-remaining": "19900"}), "game-lines")
    c2 = usage.record(_Resp({"x-requests-last": "52", "x-requests-used": "152",
                             "x-requests-remaining": "19848"}), "props")
    assert c1 == 6
    assert c2 == 52
    assert usage.run_total() == 58


def test_record_is_safe_when_headers_missing_or_malformed(monkeypatch):
    monkeypatch.setattr(usage, "_run_total", 0)
    assert usage.record(_Resp({}), "no-headers") is None
    assert usage.record(_Resp({"x-requests-last": "not-a-number"}), "bad") is None
    assert usage.record(object(), "no-headers-attr") is None
    assert usage.run_total() == 0


def test_check_budget_is_a_noop_when_no_floor_is_configured(monkeypatch):
    from mlbmodel import settings

    monkeypatch.setattr(settings, "ODDS_API_MIN_REMAINING", 0)
    monkeypatch.setattr(usage, "_remaining_cache", 5)
    usage.check_budget("game-lines")  # must not raise


def test_check_budget_blocks_a_fetch_below_the_floor(monkeypatch):
    from mlbmodel import settings

    monkeypatch.setattr(settings, "ODDS_API_MIN_REMAINING", 20)
    monkeypatch.setattr(usage, "_remaining_cache", 15)
    with pytest.raises(usage.OddsBudgetExhausted) as excinfo:
        usage.check_budget("game-lines")
    assert "15" in str(excinfo.value) and "20" in str(excinfo.value)


def test_check_budget_allows_a_fetch_at_the_floor(monkeypatch):
    from mlbmodel import settings

    monkeypatch.setattr(settings, "ODDS_API_MIN_REMAINING", 20)
    monkeypatch.setattr(usage, "_remaining_cache", 20)
    usage.check_budget("game-lines")  # at the floor is still spendable


def test_check_budget_does_not_block_when_the_budget_is_unknown(monkeypatch):
    """An unreachable probe must degrade to fetching, not to a hard stop."""
    from mlbmodel import settings

    monkeypatch.setattr(settings, "ODDS_API_MIN_REMAINING", 20)
    monkeypatch.setattr(usage, "_remaining_cache", None)
    usage.check_budget("game-lines")


def test_budget_stop_is_catchable_as_a_fetch_failure():
    """load_board/load_prop_board fall back to cache on RuntimeError — stay in that family."""
    assert issubclass(usage.OddsBudgetExhausted, RuntimeError)
