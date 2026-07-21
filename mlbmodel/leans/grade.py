"""Grade settled model leans against game and pitcher box-score outcomes.

Every ungradeable lean carries an explicit reason code (persisted to
``model_leans.ungraded_reason``) and is voided once it can no longer grade —
nothing is silently skipped. Projection leans (``line is None``) settle by
recording the realized stat into ``realized_value`` so per-market error
distributions accumulate.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import NamedTuple

from mlbmodel.sources.pitcher_box_scores import fetch_pitcher_stats_for_date, lookup_pitcher_stats
from mlbmodel.storage.supabase import SupabaseReader, SupabaseWriter

log = logging.getLogger(__name__)

_PROP_KEYS = {
    "k": "k",
    "strikeouts": "k",
    "pitcher strikeouts": "k",
    "bb": "bb",
    "walks": "bb",
    "walks allowed": "bb",
    "er": "er",
    "earned runs": "er",
    "earned runs allowed": "er",
    "outs": "outs",
    "pitching outs": "outs",
    "h": "h",
    "hits": "h",
    "hits allowed": "h",
    "fantasy": "fantasy",
    "fantasy_score": "fantasy",
    "f5_er": "f5_er",
}

# Explicit ungradeable reason codes (persisted; see migration 0005).
REASON_NO_OUTCOME = "game_outcome_missing"
REASON_NO_PITCHER_STATS = "pitcher_stats_not_found"
REASON_NO_LINE = "no_line"
REASON_UNSUPPORTED_MARKET = "unsupported_market"
REASON_FANTASY_UNVERIFIED = "fantasy_formula_unverified"
REASON_BAD_VALUES = "unparseable_line_or_actual"

# Reasons that can never resolve — void immediately instead of waiting.
_TERMINAL_REASONS = {REASON_UNSUPPORTED_MARKET, REASON_FANTASY_UNVERIFIED}
# Pending leans older than this (days after slate_date) are voided with their
# last reason — postponed games and name mismatches must not pend forever.
VOID_AFTER_DAYS = 4

# Pitcher fantasy-score formulas by book. PrizePicks MLB fantasy scoring follows
# the DraftKings classic pitcher formula: IP x2.25 (0.75/out), K x2, Win x4,
# ER x-2, Hit/BB/HBP allowed x-0.6, CG +2.5. Rare bonuses (no-hitter/CGSO +2.5/+5)
# are not derivable from the box endpoint and are omitted (~1 game/season).
# Underdog/Sleeper formulas are intentionally undefined until verified — grading
# fantasy with the wrong formula is worse than not grading it.
_FANTASY_FORMULAS = {
    "prizepicks": {
        "outs": 0.75, "k": 2.0, "win": 4.0, "er": -2.0,
        "h": -0.6, "bb": -0.6, "hbp": -0.6, "cg": 2.5,
    },
    "projection": None,  # resolved to prizepicks below (PP_Fantasy projections)
}
_FANTASY_FORMULAS["projection"] = _FANTASY_FORMULAS["prizepicks"]


class GradeOutcome(NamedTuple):
    won: bool | None
    push: bool
    reason: str | None
    realized_value: float | None


def _prop_key(market: str) -> str | None:
    return _PROP_KEYS.get(str(market or "").strip().lower())


def fantasy_score(pitcher_stats: dict, source: str) -> float | None:
    """Compute a book's pitcher fantasy score from box stats; None when unverified."""
    formula = _FANTASY_FORMULAS.get(str(source or "").lower())
    if not formula:
        return None
    inputs = {
        "outs": pitcher_stats.get("outs"),
        "k": pitcher_stats.get("strikeouts"),
        "win": pitcher_stats.get("wins"),
        "er": pitcher_stats.get("earned_runs"),
        "h": pitcher_stats.get("hits"),
        "bb": pitcher_stats.get("walks"),
        "hbp": pitcher_stats.get("hit_batsmen"),
        "cg": pitcher_stats.get("complete_games"),
    }
    total = 0.0
    for key, weight in formula.items():
        value = inputs.get(key)
        if value is None:
            value = 0
        try:
            total += weight * float(value)
        except (TypeError, ValueError):
            return None
    return round(total, 2)


def _prop_actual(prop_key: str, pitcher_stats: dict, source: str) -> tuple[float | None, str | None]:
    """Realized value for a prop market, or (None, reason)."""
    if prop_key == "f5_er":
        # First-5-innings earned runs are not exposed by the box endpoint.
        return None, REASON_UNSUPPORTED_MARKET
    if prop_key == "fantasy":
        value = fantasy_score(pitcher_stats, source)
        if value is None:
            return None, REASON_FANTASY_UNVERIFIED
        return value, None
    actual_map = {
        "k": pitcher_stats.get("strikeouts"),
        "bb": pitcher_stats.get("walks"),
        "er": pitcher_stats.get("earned_runs"),
        "outs": pitcher_stats.get("outs"),
        "h": pitcher_stats.get("hits"),
    }
    if prop_key not in actual_map:
        return None, REASON_UNSUPPORTED_MARKET
    actual = actual_map[prop_key]
    if actual is None:
        return None, REASON_BAD_VALUES
    try:
        return float(actual), None
    except (TypeError, ValueError):
        return None, REASON_BAD_VALUES


def grade_lean_detailed(
    lean: dict,
    *,
    outcome: dict | None = None,
    pitcher_stats: dict | None = None,
) -> GradeOutcome:
    """Grade one lean. reason is set exactly when the lean could not be graded."""
    market = str(lean.get("market") or "").lower()
    selection = str(lean.get("selection") or "").lower()
    line = lean.get("line")
    source = str(lean.get("source") or "").lower()
    prop_key = _prop_key(market)

    if prop_key or source in {"prizepicks", "underdog", "sleeper", "pickem", "prop", "projection"}:
        if pitcher_stats is None:
            return GradeOutcome(None, False, REASON_NO_PITCHER_STATS, None)
        actual, reason = _prop_actual(prop_key or "", pitcher_stats, source)
        if actual is None:
            return GradeOutcome(None, False, reason, None)
        if line is None:
            # Projection lean: settles by realized value only (error tracking).
            if source == "projection":
                return GradeOutcome(None, False, None, actual)
            return GradeOutcome(None, False, REASON_NO_LINE, actual)
        try:
            line_f = float(line)
        except (TypeError, ValueError):
            return GradeOutcome(None, False, REASON_BAD_VALUES, actual)
        if actual == line_f:
            return GradeOutcome(None, True, None, actual)
        over = actual > line_f
        want_over = selection == "over"
        return GradeOutcome(over == want_over, False, None, actual)

    if market in {"f5_ml", "f5_total"}:
        # A full-game outcome is NOT the first-5-innings result; grading F5
        # markets against finals misgrades them. Void until linescore-based
        # F5 outcomes are ingested.
        return GradeOutcome(None, False, REASON_UNSUPPORTED_MARKET, None)

    if outcome is None:
        return GradeOutcome(None, False, REASON_NO_OUTCOME, None)

    total = outcome.get("total_runs")
    winner = outcome.get("winner_team")
    margin = outcome.get("margin_home")

    if market in {"ml", "moneyline", "h2h"}:
        return GradeOutcome(str(winner or "").upper() == selection.upper(), False, None, None)
    if market in {"total", "totals"} and line is not None and total is not None:
        line_f = float(line)
        total_f = float(total)
        if total_f == line_f:
            return GradeOutcome(None, True, None, total_f)
        over = total_f > line_f
        return GradeOutcome(over if selection == "over" else not over, False, None, total_f)
    if market in {"runline", "spread", "spreads", "run_line"} and margin is not None:
        team = selection.upper()
        home = str(outcome.get("home_team") or "").upper()
        team_margin = float(margin) if team == home else -float(margin)
        runline = float(line) if line is not None else -1.5
        if team_margin + runline == 0:
            return GradeOutcome(None, True, None, team_margin)
        return GradeOutcome(team_margin + runline > 0, False, None, team_margin)

    return GradeOutcome(None, False, REASON_UNSUPPORTED_MARKET, None)


def grade_lean(
    lean: dict,
    *,
    outcome: dict | None = None,
    pitcher_stats: dict | None = None,
) -> tuple[bool | None, bool]:
    """Back-compat wrapper: (won, push). Prefer grade_lean_detailed."""
    result = grade_lean_detailed(lean, outcome=outcome, pitcher_stats=pitcher_stats)
    return result.won, result.push


def american_implied(odds) -> float | None:
    try:
        value = float(odds)
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    if value > 0:
        return 100.0 / (value + 100.0)
    return -value / (-value + 100.0)


def clv_points(entry_odds, closing_odds) -> float | None:
    """Closing-line value in probability points; positive = beat the close."""
    entry = american_implied(entry_odds)
    close = american_implied(closing_odds)
    if entry is None or close is None:
        return None
    return round((close - entry) * 100, 2)


def settle_leans(
    *,
    reader: SupabaseReader | None = None,
    writer: SupabaseWriter | None = None,
    today: date | None = None,
) -> int:
    reader = reader or SupabaseReader()
    writer = writer or SupabaseWriter()
    if not writer.url or not writer.key:
        return 0
    today = today or datetime.now(timezone.utc).date()

    pending = reader.get(
        "model_leans?settled=eq.false&select=lean_id,slate_date,game_pk,source,"
        "market,selection,line,pitcher_name,entry_odds,closing_odds,ungraded_reason&limit=5000"
    )
    if pending.error:
        # Missing migration (PGRST205) or similar — degrade instead of aborting
        # the whole settle pass (sharp observations can still grade).
        err = pending.error.lower()
        if (
            "pgrst205" in err
            or "could not find the table" in err
            or "model_leans" in err and ("404" in pending.error or "http 404" in err)
        ):
            log.warning("model_leans unavailable (%s); skipping lean settlement", pending.error)
            return 0
        raise RuntimeError(pending.error)

    outcomes = reader.get(
        "game_outcomes?select=game_pk,home_runs,away_runs,total_runs,margin_home,winner_team"
    )
    games = reader.get("games?select=game_pk,home_team,away_team,game_date")
    if outcomes.error or games.error:
        raise RuntimeError(outcomes.error or games.error)

    outcome_by_pk = {int(r["game_pk"]): r for r in outcomes.rows}
    game_by_pk = {int(r["game_pk"]): r for r in games.rows}
    for pk, row in outcome_by_pk.items():
        if pk in game_by_pk:
            row["home_team"] = game_by_pk[pk]["home_team"]
            row["away_team"] = game_by_pk[pk]["away_team"]

    dates = sorted({str(row.get("slate_date") or "")[:10] for row in pending.rows if row.get("slate_date")})
    stats_by_date: dict[str, dict[str, dict]] = {}
    for day in dates:
        if day:
            stats_by_date[day] = fetch_pitcher_stats_for_date(day)

    settled = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for lean in pending.rows:
        pk = lean.get("game_pk")
        outcome = outcome_by_pk.get(int(pk)) if pk is not None else None
        slate_date = str(lean.get("slate_date") or "")[:10]
        pitcher_stats = lookup_pitcher_stats(
            stats_by_date,
            slate_date=slate_date,
            pitcher_name=lean.get("pitcher_name"),
        )
        result = grade_lean_detailed(lean, outcome=outcome, pitcher_stats=pitcher_stats)

        graded = result.won is not None or result.push
        is_projection_settle = (
            str(lean.get("source") or "").lower() == "projection"
            and result.reason is None
            and result.realized_value is not None
        )
        if graded or is_projection_settle:
            payload = {
                "settled": True,
                "won": result.won,
                "push": result.push,
                "settled_at": now_iso,
                "ungraded_reason": None,
            }
            if result.realized_value is not None:
                payload["realized_value"] = result.realized_value
            clv = clv_points(lean.get("entry_odds"), lean.get("closing_odds"))
            if clv is not None:
                payload["clv_pts"] = clv
            writer.update("model_leans", f"lean_id=eq.{lean['lean_id']}", payload)
            settled += 1
            continue

        # Ungradeable: persist the reason; void terminal or expired leans.
        reason = result.reason or REASON_BAD_VALUES
        expired = _older_than(slate_date, today, VOID_AFTER_DAYS)
        if reason in _TERMINAL_REASONS or expired:
            writer.update(
                "model_leans",
                f"lean_id=eq.{lean['lean_id']}",
                {
                    "settled": True,
                    "void": True,
                    "won": None,
                    "push": False,
                    "ungraded_reason": reason,
                    "settled_at": now_iso,
                },
            )
        elif reason != (lean.get("ungraded_reason") or None):
            writer.update(
                "model_leans",
                f"lean_id=eq.{lean['lean_id']}",
                {"ungraded_reason": reason},
            )
    return settled


def _older_than(slate_date: str, today: date, days: int) -> bool:
    try:
        slate = date.fromisoformat(str(slate_date)[:10])
    except (TypeError, ValueError):
        return False
    return (today - slate).days > days
