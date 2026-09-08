import json
from pathlib import Path

from mlbmodel.report.board import GEM_EDGE_PTS, GEM_STATES, Board, Card, Group, Side, Tile
from mlbmodel.report.board_mlb import _is_gem, _tile
from mlbmodel.report.export import payload, write_bundle


def _board():
    priced_bet = Tile(
        label="Total", value="+4.2", state="OVER 8.5 · MONITOR",
        tone="warnc", gem=True, priced=True,
    )
    priced_watch = Tile(
        label="Moneyline", value="+1.0", state="HOU · AVOID",
        tone="mut", gem=False, priced=True,
    )
    model_only = Tile(
        label="Run line", value="55%", state="HOU · model only",
        tone="mut", gem=False, priced=False,
    )
    drivers = Tile(label="HOU lineup", value="+0.0%", state="unavailable · no adjustment")
    card = Card(
        key="HOU@DET",
        away=Side(abbr="HOU", score="4.1"),
        home=Side(abbr="DET", score="4.4"),
        groups=(
            Group(label="Full game", tiles=(priced_bet, priced_watch, model_only), tag="fullgame"),
            Group(label="Why this projection", tiles=(drivers,), market=False),
        ),
    )
    return Board(sport="MLB", cards=[card], date_label="2026-09-08")


def test_picks_are_priced_tiles_not_recommendations():
    board = _board()
    assert board.picks == 2
    gate = {"verdict": "HOLD/ABSTAIN", "reasons": ["OOS n 12 < min 50 (under-powered)"]}
    data = payload(board, gate=gate, slate_date="2026-09-08")
    assert data["schema"] == "mlb-model/board/1"
    assert data["authority"] == "HOLD/ABSTAIN"
    assert data["may_bet"] is False
    assert data["unmet_gates"] == ["OOS n 12 < min 50 (under-powered)"]
    assert len(data["priced_markets"]) == 2
    assert all(row["priced"] for row in data["priced_markets"])
    assert data["picks"] == 2
    # Unpriced model-only tiles are not picks.
    assert all(row["label"] != "Run line" for row in data["priced_markets"])


def test_flagged_tiles_are_gems_from_kernel_rule():
    row = {"edge": GEM_EDGE_PTS, "state": "MONITOR"}
    assert _is_gem(row)
    tile = _tile("Total", {"edge": 4.2, "state": "MONITOR", "side": "over", "line": 8.5, "tone": "warnc"})
    assert tile.priced is True
    assert tile.gem is True
    weak = {"edge": GEM_EDGE_PTS - 0.1, "state": "MONITOR"}
    assert not _is_gem(weak)
    rec = {"edge": 5.0, "state": "AVOID"}
    assert not _is_gem(rec)
    board = _board()
    data = payload(board, gate={"verdict": "HOLD/ABSTAIN", "reasons": ["gate"]})
    assert data["gems"] == 1
    assert len(data["flagged_tiles"]) == 1
    assert data["flagged_tiles"][0]["gem"] is True
    assert set(data["gem_states"]) == set(GEM_STATES)


def test_write_bundle_and_bet_is_not_emitted_while_unpromoted(tmp_path):
    board = _board()
    paths = write_bundle(
        tmp_path,
        board=board,
        gate={"verdict": "HOLD/ABSTAIN", "reasons": ["OOS ROI 95% LB -0.1 <= hurdle 0.0"]},
        sync={"status": "exact", "game_count": 1},
        slate_date="2026-09-08",
        ledger={"graded": 4, "pending": 2},
        leans=[],
    )
    board_json = json.loads(Path(paths["board"]).read_text(encoding="utf-8"))
    build = json.loads(Path(paths["build"]).read_text(encoding="utf-8"))
    record = json.loads(Path(paths["record"]).read_text(encoding="utf-8"))
    assert board_json["may_bet"] is False
    assert "BET" not in board_json["authority"]
    assert build["generated_at"]
    assert "sources" in build
    assert "odds" in build
    assert "issues" in build
    for key in (
        "games_graded", "pending_snapshots", "model_mae", "consensus_mae",
        "book_mae", "ats", "totals", "authority", "may_bet", "unmet_gates",
    ):
        assert key in record
    assert record["may_bet"] is False
    assert record["games_graded"] == 4
    assert record["pending_snapshots"] == 2
