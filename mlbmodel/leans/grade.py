"""Grade settled model leans against game and pitcher box-score outcomes."""
from __future__ import annotations

from datetime import datetime, timezone

from mlbmodel.storage.supabase import SupabaseReader, SupabaseWriter


def grade_lean(
    lean: dict,
    *,
    outcome: dict | None = None,
    pitcher_stats: dict | None = None,
) -> tuple[bool | None, bool]:
    """Return (won, push). None won means ungradeable."""
    market = str(lean.get("market") or "").lower()
    selection = str(lean.get("selection") or "").lower()
    line = lean.get("line")
    source = str(lean.get("source") or "").lower()

    if market in {"k", "bb", "er", "outs", "prop"} or source in {
        "prizepicks", "underdog", "sleeper", "pickem", "prop",
    }:
        if pitcher_stats is None or line is None:
            return None, False
        prop = market if market in {"k", "bb", "er", "outs"} else str(lean.get("market") or "")
        actual_map = {
            "k": pitcher_stats.get("strikeouts"),
            "bb": pitcher_stats.get("walks"),
            "er": pitcher_stats.get("earned_runs"),
            "outs": pitcher_stats.get("outs"),
        }
        actual = actual_map.get(prop.lower())
        if actual is None:
            return None, False
        try:
            actual_f = float(actual)
            line_f = float(line)
        except (TypeError, ValueError):
            return None, False
        if actual_f == line_f:
            return None, True
        over = actual_f > line_f
        want_over = selection == "over"
        return over == want_over, False

    if outcome is None:
        return None, False

    home_runs = outcome.get("home_runs")
    total = outcome.get("total_runs")
    winner = outcome.get("winner_team")
    margin = outcome.get("margin_home")

    if market in {"ml", "moneyline", "h2h"}:
        return winner == selection.upper(), False
    if market in {"total", "totals"} and line is not None and total is not None:
        line_f = float(line)
        total_f = float(total)
        if total_f == line_f:
            return None, True
        over = total_f > line_f
        return (over if selection == "over" else not over), False
    if market in {"runline", "spread", "spreads"} and margin is not None and home_runs is not None:
        team = selection.upper()
        home = str(outcome.get("home_team") or "").upper()
        team_margin = float(margin) if team == home else -float(margin)
        runline = -1.5
        return team_margin + runline > 0, False

    return None, False


def settle_leans(*, reader: SupabaseReader | None = None, writer: SupabaseWriter | None = None) -> int:
    reader = reader or SupabaseReader()
    writer = writer or SupabaseWriter()
    if not writer.url or not writer.key:
        return 0

    pending = reader.get(
        "model_leans?settled=eq.false&select=lean_id,slate_date,game_pk,source,"
        "market,selection,line&limit=5000"
    )
    if pending.error:
        raise RuntimeError(pending.error)

    outcomes = reader.get(
        "game_outcomes?select=game_pk,home_runs,away_runs,total_runs,margin_home,winner_team"
    )
    games = reader.get("games?select=game_pk,home_team,away_team")
    if outcomes.error or games.error:
        raise RuntimeError(outcomes.error or games.error)

    outcome_by_pk = {int(r["game_pk"]): r for r in outcomes.rows}
    game_by_pk = {int(r["game_pk"]): r for r in games.rows}
    for pk, row in outcome_by_pk.items():
        if pk in game_by_pk:
            row["home_team"] = game_by_pk[pk]["home_team"]
            row["away_team"] = game_by_pk[pk]["away_team"]

    settled = 0
    for lean in pending.rows:
        pk = lean.get("game_pk")
        outcome = outcome_by_pk.get(int(pk)) if pk is not None else None
        won, push = grade_lean(lean, outcome=outcome)
        if won is None and not push:
            continue
        writer.update(
            "model_leans",
            f"lean_id=eq.{lean['lean_id']}",
            {
                "settled": True,
                "won": won,
                "push": push,
                "settled_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        settled += 1
    return settled
