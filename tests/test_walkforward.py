"""Enforces Constitution STD-10 (point-in-time / no leakage) + execution-cost handling."""
from mlbmodel.backtest.walkforward import (
    executable_rows, net_roi, kalshi_fee, evaluate, time_ordered_split, steam_rule,
)


def test_net_roi_sign_and_fee():
    # winning a 0.40 entry returns ~ +1.5/unit gross; fee reduces it
    gross = net_roi(0.40, True, fee=False)
    netf = net_roi(0.40, True, fee=True)
    assert gross > netf > 0
    assert net_roi(0.40, False, fee=True) < 0
    assert kalshi_fee(0.5) > kalshi_fee(0.05)        # fee peaks mid, ~0 at tails


def test_time_split_is_point_in_time():
    rows = [{"game_pk": d, "signal_time": f"2026-06-{d:02d}T00:00:00Z",
             "entry_prob": 0.5, "won": d % 2 == 0,
             "implied_probability": 0.5, "signal_delta": 0.05}
            for d in range(1, 21)]
    train, test = time_ordered_split(rows, 0.7)
    assert len(train) == 14 and len(test) == 6
    assert max(r["signal_time"] for r in train) < min(r["signal_time"] for r in test)


def test_evaluate_shape():
    rows = [{"entry_prob": 0.45, "won": True, "implied_probability": 0.52},
            {"entry_prob": 0.55, "won": False, "implied_probability": 0.50}]
    ev = evaluate(rows)
    assert ev["n"] == 2 and "roi" in ev and "clv" in ev and "roi_lb" in ev


def test_steam_rule_threshold():
    r = steam_rule(0.04)
    assert r({"signal_delta": 0.05})
    assert not r({"signal_delta": 0.03})
    assert not r({"signal_delta": None})


def test_hindsight_only_rows_are_rejected():
    rows = [{"game_pk": 1, "open_prob": 0.4, "delta": 0.05, "won": True,
             "implied_probability": 0.5, "snapshot_time": "2026-06-01T00:00:00Z"}]
    assert executable_rows(rows) == []
