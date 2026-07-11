"""Odds API usage accounting: accumulates x-requests-last, tolerates missing headers."""
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
