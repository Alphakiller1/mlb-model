"""Board kernel + MLB adapter.

The kernel is vendored into wnba-edge-model and nfl-model, so these tests pin the parts
every sport depends on: what counts as a pick, what counts as a gem, and that an unpriced
market can never inflate either counter.
"""
from __future__ import annotations

import pytest

from mlbmodel.report.board import (
    GEM_EDGE_PTS,
    Board,
    Card,
    Group,
    Principal,
    Side,
    Tile,
    board_html,
)
from mlbmodel.report.board_mlb import build_board, build_card


def _market(market, side, edge, state="BET", tone="pos", line=None, model=55.0):
    return {
        "market": market,
        "side": side,
        "line": line,
        "edge": edge,
        "state": state,
        "tone": tone,
        "model": model,
        "label": market,
        "reason": "",
    }


def _game(**overrides):
    game = {
        "away": "NYY",
        "home": "BOS",
        "key": "NYY@BOS",
        "time": "7:10 PM ET",
        "pk": 1,
        "ph": 0.56,
        "total": 9.0,
        "margin": 0.6,
        "asp": "Gerrit Cole",
        "hsp": "Brayan Bello",
        "ak": 27.0,
        "hk": 19.0,
        "afip": 3.10,
        "hfip": 4.30,
        "lean": "BOS",
    }
    game.update(overrides)
    return game


# ── counters ────────────────────────────────────────────────────────────────


def test_unpriced_tile_is_not_a_pick():
    tile = Tile(label="Total", value="55%", state="OVER · model only")
    assert not tile.is_priced


def test_priced_tile_counts_once():
    group = Group(
        label="Full game",
        tiles=(
            Tile(label="Moneyline", value="+3.0", priced=True),
            Tile(label="Total", value="52%"),
        ),
    )
    assert group.priced == 1


def test_card_picks_and_gems_come_from_tiles():
    card = Card(
        key="NYY@BOS",
        away=Side("NYY"),
        home=Side("BOS"),
        groups=(
            Group(
                label="Full game",
                tiles=(
                    Tile(label="Moneyline", value="+7.0", priced=True, gem=True),
                    Tile(label="Total", value="+0.4", priced=True),
                    Tile(label="Run line", value="—"),
                ),
            ),
        ),
    )
    assert card.picks == 2
    assert card.gems == 1


# ── MLB adapter ─────────────────────────────────────────────────────────────


def test_model_only_markets_do_not_count_as_picks():
    """A slate with no matched book prices must report zero picks, not one per market."""
    report = {"markets": [
        _market("ml", "BOS", None, state="NO MARKET", tone="mut"),
        _market("total", "over", None, state="NO MARKET", tone="mut", line=9.0),
    ]}
    card = build_card(_game(), report)
    assert card.picks == 0
    assert card.gems == 0
    # …but the tiles still carry the model's own number rather than going blank.
    tiles = [tile for group in card.groups for tile in group.tiles]
    assert any(tile.value.endswith("%") for tile in tiles)


def test_priced_market_becomes_a_pick_with_signed_edge():
    report = {"markets": [_market("ml", "BOS", 4.2)]}
    card = build_card(_game(), report)
    moneyline = next(t for g in card.groups for t in g.tiles if t.label == "Moneyline")
    assert moneyline.is_priced
    assert moneyline.value == "+4.2"
    assert "BOS" in moneyline.state
    assert card.picks == 1


@pytest.mark.parametrize(
    ("edge", "state", "expect_gem"),
    [
        (GEM_EDGE_PTS + 1.0, "BET", True),
        (GEM_EDGE_PTS - 0.1, "BET", False),      # below the edge floor
        (GEM_EDGE_PTS + 1.0, "AVOID", False),    # actionable states only
        (GEM_EDGE_PTS + 1.0, "MONITOR", True),
    ],
)
def test_gem_requires_both_edge_and_actionable_state(edge, state, expect_gem):
    card = build_card(_game(), {"markets": [_market("ml", "BOS", edge, state=state)]})
    assert (card.gems == 1) is expect_gem


def test_both_sides_of_a_market_collapse_to_the_better_tile():
    report = {"markets": [
        _market("total", "over", 1.1, line=9.0),
        _market("total", "under", 5.4, line=9.0),
    ]}
    card = build_card(_game(), report)
    totals = [t for g in card.groups for t in g.tiles if t.label == "Total"]
    assert len(totals) == 1
    assert totals[0].value == "+5.4"
    assert "UNDER" in totals[0].state


def test_expected_runs_split_from_total_and_margin():
    card = build_card(_game(total=9.0, margin=1.0), {"markets": []})
    assert card.away.score == "4.0"
    assert card.home.score == "5.0"
    assert card.home.favored is True


def test_first_five_group_is_omitted_when_no_f5_price_exists():
    card = build_card(_game(), {"markets": [_market("ml", "BOS", 3.0)]})
    assert [group.label for group in card.groups] == ["Full game"]


def test_first_five_group_appears_once_f5_is_priced():
    report = {"markets": [
        _market("ml", "BOS", 3.0),
        _market("f5_total", "over", 2.2, line=4.5),
    ]}
    card = build_card(_game(), report)
    assert [group.label for group in card.groups] == ["Full game", "First 5 innings"]
    assert "f5" in card.tags


def test_starting_pitchers_are_the_principals():
    card = build_card(_game(), {"markets": []})
    assert card.principal_label == "Starting pitchers"
    assert [p.name for p in card.principals] == ["Gerrit Cole", "Brayan Bello"]
    assert "3.10 FIP" in card.principals[0].stat


def test_missing_probable_pitcher_renders_tbd_not_a_crash():
    card = build_card(_game(asp="", hsp=""), {"markets": []})
    assert [p.name for p in card.principals] == ["TBD", "TBD"]


def test_headline_names_the_best_priced_edge():
    report = {"markets": [
        _market("ml", "BOS", 1.0),
        _market("total", "under", 6.5, line=9.0),
    ]}
    card = build_card(_game(), report)
    assert "Total" in card.headline
    assert "+6.5pt" in card.headline


def test_headline_is_honest_when_nothing_is_priced():
    card = build_card(_game(), {"markets": [_market("ml", "BOS", None, state="NO MARKET")]})
    assert "No priced edge" in card.headline


# ── board assembly ──────────────────────────────────────────────────────────


def test_games_without_model_inputs_are_reported_not_dropped_silently():
    slate = [_game(), _game(away="CHC", home="STL", key="CHC@STL", pk=2, err=True)]
    board = build_board(slate, "2026-08-12", {}, {})
    assert len(board.cards) == 1
    assert any("without model inputs" in part for part in board.meta)


def test_board_totals_are_the_sum_of_its_cards():
    slate = [_game(), _game(away="CHC", home="STL", key="CHC@STL", pk=2)]
    reports = {
        "NYY@BOS": {"markets": [_market("ml", "BOS", 8.0)]},
        "CHC@STL": {"markets": [_market("total", "over", 1.0, line=8.5)]},
    }
    board = build_board(slate, "2026-08-12", reports, {})
    assert board.picks == 2
    assert board.gems == 1


def test_empty_slate_renders_an_honest_empty_state():
    html = board_html(build_board([], "", {}, {}))
    assert "No games on this slate yet" in html


# ── rendering ───────────────────────────────────────────────────────────────


def test_board_html_is_escaped():
    board = Board(
        sport="MLB",
        cards=[Card(key="x", away=Side('<img src=x onerror="alert(1)">'), home=Side("BOS"))],
    )
    html = board_html(board)
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_card_exposes_filter_tags_and_counts_as_data_attributes():
    slate = [_game()]
    reports = {"NYY@BOS": {"markets": [
        _market("ml", "BOS", 9.0),
        _market("f5_total", "over", 1.0, line=4.5),
    ]}}
    html = board_html(build_board(slate, "2026-08-12", reports, {}))
    assert 'data-picks="2"' in html
    assert 'data-gems="1"' in html
    assert 'data-tags="f5 fullgame gems"' in html


def test_unknown_tone_falls_back_to_muted_never_raw_class_injection():
    html = board_html(
        Board(sport="MLB", cards=[Card(
            key="x", away=Side("A"), home=Side("B"),
            status_label="live", status_tone='" onload="x',
        )])
    )
    assert 'onload=' not in html
    assert "bd-status is-mut" in html


def test_principal_without_art_still_renders_a_slot():
    html = board_html(
        Board(sport="MLB", cards=[Card(
            key="x", away=Side("A"), home=Side("B"),
            principals=(Principal(name="Sole Starter"),),
        )])
    )
    assert "bd-face--na" in html
    assert "Sole Starter" in html
