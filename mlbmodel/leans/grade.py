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
    "fantasy_score": "fantasy_score",
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
# Reasons that were TRANSIENT: the lean was gradeable, the data just had not landed yet.
# A lean voided for one of these is re-opened on later runs, because `VOID_AFTER_DAYS`
# otherwise makes a timing accident permanent. On 2026-09-04 this described 587 rows on the
# 2026-08-24 slate alone — every one of them a game whose outcome the warehouse now holds,
# across only 10 game_pks, voided purely because grading ran before the finals were ingested.
# That is most of the game model's evidence base thrown away for a scheduling reason.
_RECOVERABLE_REASONS = {REASON_NO_OUTCOME, REASON_NO_PITCHER_STATS}
# Pending leans older than this (days after slate_date) are voided with their
# last reason — postponed games and name mismatches must not pend forever.
VOID_AFTER_DAYS = 4

# Pitcher fantasy scoring differs by book, so the formula is chosen by MARKET, not by
# source. Two distinct markets exist and they are NOT interchangeable:
#
#   `fantasy`       DraftKings classic: IP x2.25 (0.75/out), K x2, Win x4, ER x-2,
#                   Hit/BB/HBP allowed x-0.6, CG +2.5.
#   `fantasy_score` PrizePicks: Out +1, K +3, ER -3, Quality Start +4, Win +6.
#
# Grading both with the DraftKings formula (the behaviour before 2026-08-28, when
# `fantasy_score` shared the `fantasy` prop key and the formula was keyed off
# `source`) put every PrizePicks projection on the wrong scale: 555 settled rows
# graded against a mean realised 12.93 while the projection engine — correctly —
# produced 26.32. PrizePicks' own posted lines for the same slate averaged 26.50,
# which is what confirms the projection side was right and the grader was wrong.
#
# Rare DraftKings bonuses (no-hitter/CGSO) are not derivable from the box endpoint
# and are omitted (~1 game/season). Underdog/Sleeper formulas stay undefined until
# verified — grading fantasy with the wrong formula is worse than not grading it.
_DRAFTKINGS_FANTASY = {
    "outs": 0.75, "k": 2.0, "win": 4.0, "er": -2.0,
    "h": -0.6, "bb": -0.6, "hbp": -0.6, "cg": 2.5,
}
_PRIZEPICKS_FANTASY = {"outs": 1.0, "k": 3.0, "er": -3.0, "win": 6.0}
# Quality start (>=6 IP and <=3 ER) is a joint condition, so it is applied separately
# from the per-event weights. Mirrors `qs_bonus` in mlbmodel.props.model.
_PRIZEPICKS_QUALITY_START = 4.0
# Books whose pitcher fantasy formula we have actually verified. Underdog and Sleeper
# also post fantasy props, but their scoring is unconfirmed, so their rows stay
# ungraded rather than being scored on someone else's formula.
_VERIFIED_FANTASY_SOURCES = {"prizepicks", "projection"}


class GradeOutcome(NamedTuple):
    won: bool | None
    push: bool
    reason: str | None
    realized_value: float | None


def _prop_key(market: str) -> str | None:
    return _PROP_KEYS.get(str(market or "").strip().lower())


def fantasy_score(pitcher_stats: dict, prop_key: str) -> float | None:
    """Compute a book's pitcher fantasy score from box stats; None when unverified.

    ``prop_key`` selects the book formula: ``fantasy`` is DraftKings, ``fantasy_score``
    is PrizePicks. Passing the wrong one silently rescales the result by roughly 2x.
    """
    formula = {
        "fantasy": _DRAFTKINGS_FANTASY,
        "fantasy_score": _PRIZEPICKS_FANTASY,
    }.get(str(prop_key or "").lower())
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
    if prop_key == "fantasy_score":
        try:
            outs = float(pitcher_stats.get("outs") or 0)
            earned = float(pitcher_stats.get("earned_runs") or 0)
        except (TypeError, ValueError):
            return None
        if outs >= 18 and earned <= 3:
            total += _PRIZEPICKS_QUALITY_START
    return round(total, 2)


def _prop_actual(prop_key: str, pitcher_stats: dict, source: str) -> tuple[float | None, str | None]:
    """Realized value for a prop market, or (None, reason)."""
    if prop_key == "f5_er":
        # First-5-innings earned runs are not exposed by the box endpoint.
        return None, REASON_UNSUPPORTED_MARKET
    if prop_key in {"fantasy", "fantasy_score"}:
        if str(source or "").lower() not in _VERIFIED_FANTASY_SOURCES:
            return None, REASON_FANTASY_UNVERIFIED
        value = fantasy_score(pitcher_stats, prop_key)
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

    if outcome is None:
        return GradeOutcome(None, False, REASON_NO_OUTCOME, None)

    if market in {"f5_ml", "f5_total", "f5_runline"}:
        home_f5 = outcome.get("home_f5_runs")
        away_f5 = outcome.get("away_f5_runs")
        if home_f5 is None or away_f5 is None:
            return GradeOutcome(None, False, REASON_NO_OUTCOME, None)
        home_f5, away_f5 = float(home_f5), float(away_f5)
        home = str(outcome.get("home_team") or "").upper()
        if market == "f5_ml":
            if home_f5 == away_f5:
                return GradeOutcome(None, True, None, home_f5 - away_f5)
            winner = home if home_f5 > away_f5 else str(outcome.get("away_team") or "").upper()
            return GradeOutcome(winner == selection.upper(), False, None, home_f5 - away_f5)
        if market == "f5_total" and line is not None:
            actual = home_f5 + away_f5
            line_f = float(line)
            if actual == line_f:
                return GradeOutcome(None, True, None, actual)
            over = actual > line_f
            return GradeOutcome(over if selection == "over" else not over, False, None, actual)
        if market == "f5_runline" and line is not None:
            team_margin = home_f5 - away_f5 if selection.upper() == home else away_f5 - home_f5
            adjusted = team_margin + float(line)
            if adjusted == 0:
                return GradeOutcome(None, True, None, team_margin)
            return GradeOutcome(adjusted > 0, False, None, team_margin)
        return GradeOutcome(None, False, REASON_BAD_VALUES, None)

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

    pending_path = (
        "model_leans?settled=eq.false&select=*"
        "&order=slate_date.asc,lean_id.asc"
    )
    if hasattr(type(reader), "get_all"):
        pending = reader.get_all(pending_path, max_rows=250000)
        read_all = reader.get_all
    else:
        pending = reader.get(pending_path)
        read_all = reader.get
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

    # F5 game markets were historically voided as unsupported even though the outcomes
    # table already stores first-five linescores. Re-open those audit rows automatically so
    # the corrected grader backfills them instead of leaving permanent false voids.
    candidates = list(pending.rows)
    seen_ids = {str(row.get("lean_id")) for row in candidates}

    def _reopen(query: str) -> None:
        result = read_all(query)
        if result.error:
            return
        for row in result.rows:
            lean_id = str(row.get("lean_id"))
            if lean_id not in seen_ids:
                seen_ids.add(lean_id)
                candidates.append(row)

    _reopen(
        "model_leans?settled=eq.true&void=eq.true&ungraded_reason=eq.unsupported_market"
        "&market=in.(f5_ml,f5_total,f5_runline)&select=*"
    )
    # And anything voided for a reason that was only ever a timing problem. If the data still
    # is not there the row simply voids again, so re-attempting costs nothing.
    _reopen(
        "model_leans?settled=eq.true&void=eq.true&ungraded_reason=in.("
        + ",".join(sorted(_RECOVERABLE_REASONS))
        + ")&select=*"
    )

    outcomes = read_all(
        "game_outcomes?select=game_pk,home_runs,away_runs,home_f5_runs,away_f5_runs,"
        "total_runs,margin_home,winner_team"
    )
    games = read_all("games?select=game_pk,home_team,away_team,game_date")
    if outcomes.error or games.error:
        raise RuntimeError(outcomes.error or games.error)

    outcome_by_pk = {int(r["game_pk"]): r for r in outcomes.rows}
    game_by_pk = {int(r["game_pk"]): r for r in games.rows}
    for pk, row in outcome_by_pk.items():
        if pk in game_by_pk:
            row["home_team"] = game_by_pk[pk]["home_team"]
            row["away_team"] = game_by_pk[pk]["away_team"]

    dates = sorted({str(row.get("slate_date") or "")[:10] for row in candidates if row.get("slate_date")})
    stats_by_date: dict[str, dict[str, dict]] = {}
    for day in dates:
        if day:
            stats_by_date[day] = fetch_pitcher_stats_for_date(day)

    settled = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    bulk_updates: list[dict] = []
    can_bulk_upsert = hasattr(type(writer), "upsert")

    def persist(lean: dict, payload: dict) -> None:
        if can_bulk_upsert:
            bulk_updates.append({**lean, **payload})
            return
        writer.update(
            "model_leans",
            f"lean_id=eq.{lean['lean_id']}",
            payload,
        )

    for lean in candidates:
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
                "void": False,
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
            persist(lean, payload)
            settled += 1
            continue

        # Ungradeable: persist the reason; void terminal or expired leans.
        reason = result.reason or REASON_BAD_VALUES
        expired = _older_than(slate_date, today, VOID_AFTER_DAYS)
        if reason in _TERMINAL_REASONS or expired:
            persist(
                lean,
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
            persist(lean, {"ungraded_reason": reason})

    if bulk_updates:
        for offset in range(0, len(bulk_updates), 250):
            writer.upsert(
                "model_leans",
                bulk_updates[offset : offset + 250],
                on_conflict="lean_id",
            )
    return settled


def _older_than(slate_date: str, today: date, days: int) -> bool:
    try:
        slate = date.fromisoformat(str(slate_date)[:10])
    except (TypeError, ValueError):
        return False
    return (today - slate).days > days
