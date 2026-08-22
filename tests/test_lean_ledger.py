"""Local lean ledger: snapshot merge, warehouse paging, in-memory grading."""
from __future__ import annotations

from mlbmodel.baseball.repository import canonical_game_pk
from mlbmodel.leans.calibration import summarize_tracked
from mlbmodel.leans.ledger import (
    apply_local_grades,
    fetch_warehouse_leans,
    load_tracked_leans,
    merge_lean_rows,
    outcomes_from_game_results,
    select_recent_leans,
)
from mlbmodel.storage.supabase import ReadResult


class RecordingReader:
    def __init__(self, routes):
        self.routes = routes
        self.paths: list[str] = []

    def get(self, path):
        raise AssertionError(f"results must page with get_all, got get({path})")

    def get_all(self, path):
        self.paths.append(path)
        for prefix, result in self.routes.items():
            if path.startswith(prefix):
                return result
        return ReadResult([])


def test_fetch_warehouse_leans_pages_settled_and_pending():
    settled = [{"slate_date": "2026-08-01", "source": "matchup", "settled": True, "won": True,
                "market": "ml", "selection": "TOR", "lean": "PROJECTION", "game_pk": 1}]
    pending = [{"slate_date": "2026-08-22", "source": "matchup", "settled": False,
                "market": "ml", "selection": "NYY", "lean": "PROJECTION", "game_pk": 2}]
    reader = RecordingReader({
        "model_leans?settled=eq.true": ReadResult(settled),
        "model_leans?settled=eq.false": ReadResult(pending),
    })
    result = fetch_warehouse_leans(reader)
    assert result.error is None
    assert len(result.rows) == 2
    assert any("settled=eq.true" in path for path in reader.paths)
    assert any("source=neq.projection" in path for path in reader.paths)


def test_merge_prefers_settled_copy():
    pending = {"slate_date": "2026-08-01", "game_pk": 1, "source": "matchup",
               "market": "ml", "selection": "TOR", "line": None, "settled": False}
    graded = {**pending, "settled": True, "won": True, "push": False}
    merged = merge_lean_rows([pending], [graded])
    assert len(merged) == 1
    assert merged[0]["settled"] is True
    assert merged[0]["won"] is True


def test_local_grade_matchup_ml_from_game_results():
    pk = canonical_game_pk("2026-08-01", "STL", "TOR")
    by_pk, by_team = outcomes_from_game_results([
        {"game_date": "2026-08-01", "home_away": "home", "team": "TOR", "opp": "STL",
         "team_runs": "5", "opp_runs": "1", "result": "W"},
        {"game_date": "2026-08-01", "home_away": "away", "team": "STL", "opp": "TOR",
         "team_runs": "1", "opp_runs": "5", "result": "L"},
    ])
    assert pk in by_pk
    rows = apply_local_grades(
        [{"slate_date": "2026-08-01", "game_pk": pk, "source": "matchup",
          "market": "ml", "selection": "TOR", "lean": "PROJECTION", "settled": False}],
        by_pk=by_pk,
        by_date_team=by_team,
    )
    assert rows[0]["settled"] is True
    assert rows[0]["won"] is True


def test_select_recent_puts_settled_ahead_of_projection_flood():
    rows = [
        {"source": "projection", "lean": "PROJECTION", "settled": False,
         "recorded_at": "2026-08-22T20:00:00Z", "selection": f"p{i}"}
        for i in range(40)
    ]
    rows.append({
        "source": "matchup", "lean": "PROJECTION", "settled": True, "won": False,
        "recorded_at": "2026-08-01T12:00:00Z", "selection": "TOR", "market": "ml",
    })
    recent = select_recent_leans(rows, limit=10)
    assert recent[0]["won"] is False
    assert recent[0]["source"] == "matchup"


def test_load_tracked_leans_snapshot_only_when_warehouse_empty(tmp_path):
    from mlbmodel.leans.record import write_lean_snapshot

    pk = canonical_game_pk("2026-08-01", "STL", "TOR")
    snapshot = tmp_path / "leans.json"
    write_lean_snapshot([{
        "slate_date": "2026-08-01", "game_pk": pk, "source": "matchup",
        "market": "ml", "selection": "TOR", "line": None, "lean": "PROJECTION",
        "settled": False, "model_prob": 0.53,
    }], snapshot)
    finals = tmp_path / "game_results.csv"
    finals.write_text(
        "game_date,home_away,team,opp,team_runs,opp_runs,result\n"
        "2026-08-01,home,TOR,STL,5,1,W\n"
        "2026-08-01,away,STL,TOR,1,5,L\n",
        encoding="utf-8",
    )
    rows, notice = load_tracked_leans(
        RecordingReader({}),
        snapshot_path=snapshot,
        game_results_path=finals,
    )
    assert notice is None
    tracked = summarize_tracked(rows)
    assert tracked["wins"] >= 1
    assert tracked["losses"] == 0
