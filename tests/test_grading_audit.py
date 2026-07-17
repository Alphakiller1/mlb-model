"""Grading-audit invariants: reason codes, void, realized values, CLV, freshness."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from mlbmodel.leans.calibration import (
    brier_score,
    calibration_buckets,
    clv_summary_from_leans,
    projection_error_summary,
    summarize_record,
    ungraded_reason_counts,
    wilson_interval,
)
from mlbmodel.leans.closing import build_price_index, update_closing_odds
from mlbmodel.leans.grade import (
    REASON_FANTASY_UNVERIFIED,
    REASON_NO_PITCHER_STATS,
    REASON_UNSUPPORTED_MARKET,
    clv_points,
    fantasy_score,
    grade_lean_detailed,
    settle_leans,
)
from mlbmodel.leans.record import collect_leans
from mlbmodel.market.lines_cache import (
    read_lines_cache,
    snapshot_is_fresh,
    write_lines_cache,
)
from mlbmodel.market.pickem import fresh_pickem_books
from mlbmodel.storage.supabase import ReadResult

BOX = {
    "strikeouts": 8, "walks": 1, "earned_runs": 2, "outs": 18, "hits": 5,
    "wins": 1, "hit_batsmen": 0, "complete_games": 0,
}


class MockWriter:
    def __init__(self):
        self.url = "https://example.supabase.co"
        self.key = "secret"
        self.updates: list[tuple[str, str, dict]] = []

    def update(self, table, query, payload):
        self.updates.append((table, query, payload))


class MockReader:
    def __init__(self, routes):
        self.routes = routes

    def get(self, path):
        for prefix, result in self.routes.items():
            if path.startswith(prefix):
                return result
        return ReadResult([], f"no route for {path}")


# ---------- grade_lean_detailed ----------

def test_hits_market_grades():
    result = grade_lean_detailed(
        {"market": "h", "selection": "under", "line": 5.5, "source": "prop"},
        pitcher_stats=BOX,
    )
    assert result.won is True
    assert result.realized_value == 5.0


def test_prizepicks_fantasy_grades_with_dk_formula():
    # 18 outs*0.75 + 8K*2 + W*4 - 2ER*2 - 5H*.6 - 1BB*.6 = 13.5+16+4-4-3.6 = 25.9
    assert fantasy_score(BOX, "prizepicks") == 25.9
    result = grade_lean_detailed(
        {"market": "fantasy_score", "selection": "over", "line": 24.5, "source": "prizepicks"},
        pitcher_stats=BOX,
    )
    assert result.won is True
    assert result.realized_value == 25.9


def test_unverified_book_fantasy_gets_reason_not_a_grade():
    result = grade_lean_detailed(
        {"market": "fantasy_score", "selection": "over", "line": 24.5, "source": "underdog"},
        pitcher_stats=BOX,
    )
    assert result.won is None
    assert result.reason == REASON_FANTASY_UNVERIFIED


def test_f5_markets_void_instead_of_misgrading_against_full_game():
    for market in ("f5_ml", "f5_total", "f5_er"):
        result = grade_lean_detailed(
            {"market": market, "selection": "over", "line": 4.5, "source": "matchup"},
            outcome={"total_runs": 9, "winner_team": "BOS", "margin_home": 2},
            pitcher_stats=BOX if market == "f5_er" else None,
        )
        assert result.won is None, market
        assert result.reason == REASON_UNSUPPORTED_MARKET, market


def test_projection_lean_settles_by_realized_value_only():
    result = grade_lean_detailed(
        {"market": "k", "selection": "model", "line": None, "source": "projection"},
        pitcher_stats=BOX,
    )
    assert result.won is None and result.push is False
    assert result.reason is None
    assert result.realized_value == 8.0


def test_missing_pitcher_stats_reason():
    result = grade_lean_detailed(
        {"market": "k", "selection": "over", "line": 5.5, "source": "prop"},
        pitcher_stats=None,
    )
    assert result.reason == REASON_NO_PITCHER_STATS


# ---------- settle_leans ----------

def _routes(leans):
    return {
        "model_leans?": ReadResult(leans),
        "game_outcomes?": ReadResult([]),
        "games?": ReadResult([]),
    }


def test_settle_writes_projection_realized_value():
    leans = [{
        "lean_id": 7, "slate_date": "2026-07-06", "game_pk": None, "source": "projection",
        "market": "k", "selection": "model", "line": None, "pitcher_name": "Gerrit Cole",
        "entry_odds": None, "closing_odds": None, "ungraded_reason": None,
    }]
    writer = MockWriter()
    with patch("mlbmodel.leans.grade.fetch_pitcher_stats_for_date",
               return_value={"gerrit cole": BOX}):
        settled = settle_leans(reader=MockReader(_routes(leans)), writer=writer,
                               today=date(2026, 7, 7))
    assert settled == 1
    payload = writer.updates[0][2]
    assert payload["settled"] is True
    assert payload["realized_value"] == 8.0
    assert payload["won"] is None


def test_settle_voids_terminal_and_expired_reasons():
    leans = [
        {"lean_id": 1, "slate_date": "2026-07-06", "game_pk": 1, "source": "matchup",
         "market": "f5_total", "selection": "over", "line": 4.5, "pitcher_name": None,
         "entry_odds": None, "closing_odds": None, "ungraded_reason": None},
        # ML lean with no outcome, slate 10 days old -> expired void.
        {"lean_id": 2, "slate_date": "2026-06-26", "game_pk": 99, "source": "matchup",
         "market": "ml", "selection": "BOS", "line": None, "pitcher_name": None,
         "entry_odds": None, "closing_odds": None, "ungraded_reason": None},
        # ML lean from yesterday with no outcome yet -> reason recorded, NOT voided.
        {"lean_id": 3, "slate_date": "2026-07-05", "game_pk": 98, "source": "matchup",
         "market": "ml", "selection": "BOS", "line": None, "pitcher_name": None,
         "entry_odds": None, "closing_odds": None, "ungraded_reason": None},
    ]
    writer = MockWriter()
    with patch("mlbmodel.leans.grade.fetch_pitcher_stats_for_date", return_value={}):
        settled = settle_leans(reader=MockReader(_routes(leans)), writer=writer,
                               today=date(2026, 7, 6))
    assert settled == 0
    by_id = {q: p for _, q, p in writer.updates}
    assert by_id["lean_id=eq.1"]["void"] is True
    assert by_id["lean_id=eq.2"]["void"] is True
    assert by_id["lean_id=eq.3"] == {"ungraded_reason": "game_outcome_missing"}


def test_settle_computes_clv_on_graded_lean():
    leans = [{
        "lean_id": 4, "slate_date": "2026-07-06", "game_pk": 1, "source": "prop",
        "market": "k", "selection": "over", "line": 5.5, "pitcher_name": "Gerrit Cole",
        "entry_odds": 110, "closing_odds": -120, "ungraded_reason": None,
    }]
    writer = MockWriter()
    with patch("mlbmodel.leans.grade.fetch_pitcher_stats_for_date",
               return_value={"gerrit cole": BOX}):
        settle_leans(reader=MockReader(_routes(leans)), writer=writer, today=date(2026, 7, 7))
    payload = writer.updates[0][2]
    assert payload["won"] is True
    # entry +110 -> 47.62%, close -120 -> 54.55%: beat the close by ~6.9pt.
    assert 6.5 < payload["clv_pts"] < 7.3


def test_clv_points_signs():
    assert clv_points(110, -120) > 0  # got a better price than close
    assert clv_points(-120, 110) < 0
    assert clv_points(None, -110) is None


# ---------- calibration ----------

def _lean(prob, won, **kw):
    row = {"settled": True, "push": False, "void": False, "won": won,
           "model_prob": prob, "source": "sharp"}
    row.update(kw)
    return row


def test_calibration_uses_mean_predicted_and_wilson_ci():
    rows = [_lean(0.62, True)] * 6 + [_lean(0.68, False)] * 4
    buckets = calibration_buckets(rows, buckets=5)
    assert len(buckets) == 1
    b = buckets[0]
    assert abs(b["predicted"] - 64.4) < 0.1  # mean of probs, not the 70 midpoint
    assert b["n"] == 10
    assert b["actual_lo"] < b["actual"] < b["actual_hi"]
    assert b["reliable"] is True


def test_brier_and_summary_exclude_void_and_projections():
    rows = [
        _lean(0.6, True),
        _lean(0.6, False),
        _lean(0.6, None, void=True),
        _lean(0.6, None, source="projection", model_value=6.0, realized_value=8.0),
    ]
    summary = summarize_record(rows)
    assert summary["wins"] == 1 and summary["losses"] == 1
    assert summary["voids"] == 1
    assert summary["brier"] == brier_score(rows)
    assert summary["brier"] == round(((0.6 - 1) ** 2 + (0.6 - 0) ** 2) / 2, 4)


def test_wilson_interval_sane():
    lo, hi = wilson_interval(8, 10)
    assert 0.4 < lo < 0.8 < hi <= 1.0


def test_projection_error_summary():
    rows = [
        _lean(None, None, source="projection", market="k", model_value=6.0, realized_value=8.0),
        _lean(None, None, source="projection", market="k", model_value=5.0, realized_value=4.0),
    ]
    out = projection_error_summary(rows)
    assert out[0]["market"] == "k"
    assert out[0]["n"] == 2
    assert out[0]["mean_error"] == -0.5
    assert out[0]["mae"] == 1.5


def test_clv_summary_and_reason_counts():
    rows = [
        _lean(0.6, True, clv_pts=2.0),
        _lean(0.6, False, clv_pts=-1.0),
        {"settled": False, "ungraded_reason": "game_outcome_missing"},
    ]
    clv = clv_summary_from_leans(rows)
    assert clv["n"] == 2 and clv["clv_pts"] == 0.5
    assert ungraded_reason_counts(rows) == {"game_outcome_missing": 1}


# ---------- snapshot freshness ----------

def test_lines_cache_round_trip_and_freshness(tmp_path):
    path = tmp_path / "lines.json"
    write_lines_cache([{"player_key": "x", "proj_key": "K", "line": 5.5}], path)
    lines, snapshot_at = read_lines_cache(path)
    assert lines and snapshot_at
    assert snapshot_is_fresh(snapshot_at, snapshot_at[:10]) is True
    assert snapshot_is_fresh(snapshot_at, "2099-01-01") is False


def test_legacy_list_snapshot_is_stale(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text('[{"player_key": "x"}]', encoding="utf-8")
    lines, snapshot_at = read_lines_cache(path)
    assert lines and snapshot_at is None
    assert snapshot_is_fresh(snapshot_at, "2026-07-06") is False
    assert fresh_pickem_books({"prizepicks": snapshot_at}, "2026-07-06") == set()


def test_stale_books_do_not_record_pickem_leans():
    pickem_rows = [{
        "book": "prizepicks", "prop": "K", "line": 5.5, "projection": 6.5,
        "p_over": 0.72, "lean": "OVER", "game_pk": 1, "pitcher": "Gerrit Cole",
        "edge_pts": 22.0,
    }]
    kwargs = dict(
        slate_date="2026-07-06", market_plays=[], prop_reports=[],
        matchup_markets_by_pk={}, pitchers=[], pickem_rows=pickem_rows,
    )
    stale = collect_leans(**kwargs, fresh_pickem_books=set())
    fresh = collect_leans(**kwargs, fresh_pickem_books={"prizepicks"})
    unfiltered = collect_leans(**kwargs)  # None = legacy behavior, records all
    assert stale == []
    assert len(fresh) == 1 and fresh[0]["source"] == "prizepicks"
    assert fresh[0]["run_id"]
    assert len(unfiltered) == 1


# ---------- entry odds float fix + closing odds ----------

def test_matchup_entry_odds_accepts_floats():
    markets = {1: [{
        "market": "total", "side": "over", "line": 8.5, "state": "BET",
        "edge": 0.03, "model": 55.0, "mkt": -110.0,
    }]}
    rows = collect_leans(
        slate_date="2026-07-06", market_plays=[], pickem_rows=[], prop_reports=[],
        matchup_markets_by_pk=markets,
    )
    assert rows[0]["entry_odds"] == -110.0


def test_closing_odds_update_matches_and_writes():
    index = build_price_index(
        matchup_markets_by_pk={1: [{"market": "total", "side": "over", "line": 8.5, "mkt": -118}]},
        prop_reports=[{"game_pk": 1, "prop": "K", "side": "over", "line": 5.5, "best_odds": 105}],
    )
    reader = MockReader({
        "model_leans?": ReadResult([
            {"lean_id": 1, "game_pk": 1, "source": "matchup", "market": "total",
             "selection": "over", "line": 8.5, "closing_odds": None},
            {"lean_id": 2, "game_pk": 1, "source": "prop", "market": "k",
             "selection": "over", "line": 5.5, "closing_odds": 105},
            {"lean_id": 3, "game_pk": 2, "source": "matchup", "market": "total",
             "selection": "over", "line": 8.5, "closing_odds": None},
        ]),
    })
    writer = MockWriter()
    updated = update_closing_odds(
        slate_date="2026-07-06", price_index=index, reader=reader, writer=writer
    )
    assert updated == 1  # lean 2 unchanged, lean 3 unmatched
    assert writer.updates[0][1] == "lean_id=eq.1"
    assert writer.updates[0][2] == {"closing_odds": -118.0}
