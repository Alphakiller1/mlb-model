"""
MLB adapter for the shared Board kernel (``report/board.py``).

The kernel owns the card anatomy, filters, counters and empty states. This module owns the
only baseball-specific decisions:

* **principals** are the two starting pitchers (K/9 + FIP)
* **groups** are Full Game and First 5 Innings — F5 is a first-class MLB market family
* **scores** are expected runs, split out of the model's total and margin

Nothing here renders HTML beyond the small logo/headshot fragments baseball already owns.
"""
from __future__ import annotations

from mlbmodel.report.board import (
    GEM_EDGE_PTS,
    GEM_STATES,
    Board,
    Card,
    Group,
    Principal,
    Side,
    Tile,
)
from mlbmodel.report.decision import MKT_LABEL
from mlbmodel.report.matchup import _headshot, _logo

# Market family -> (group key, tile label). Order fixes the tile order on every card, so
# two games are always read left-to-right the same way.
_FULL_GAME = (("ml", "Moneyline"), ("total", "Total"), ("runline", "Run line"))
_FIRST_FIVE = (("f5_ml", "F5 moneyline"), ("f5_total", "F5 total"), ("f5_runline", "F5 run line"))

_ALIASES = {
    "moneyline": "ml", "h2h": "ml", "ml": "ml",
    "total": "total", "totals": "total",
    "spread": "runline", "spreads": "runline", "run_line": "runline", "runline": "runline",
    "f5_ml": "f5_ml", "f5_total": "f5_total", "f5_runline": "f5_runline",
}


def _family(market) -> str:
    return _ALIASES.get(str(market or "").lower(), str(market or "").lower())


def _best_by_family(markets) -> dict[str, dict]:
    """Best-priced row per market family — a card shows one tile per market, not both sides."""
    best: dict[str, dict] = {}
    for row in markets or []:
        key = _family(row.get("market"))
        edge = row.get("edge")
        current = best.get(key)
        if current is None:
            best[key] = row
            continue
        current_edge = current.get("edge")
        if edge is None:
            continue
        if current_edge is None or edge > current_edge:
            best[key] = row
    return best


def _is_gem(row: dict) -> bool:
    edge = row.get("edge")
    return (
        edge is not None
        and edge >= GEM_EDGE_PTS
        and str(row.get("state") or "").upper() in GEM_STATES
    )


def _side_text(row: dict) -> str:
    side = str(row.get("side") or "").strip()
    line = row.get("line")
    if line is None:
        return side.upper()
    try:
        return f"{side.upper()} {float(line):g}"
    except (TypeError, ValueError):
        return side.upper()


def _tile(label: str, row: dict | None) -> Tile:
    if row is None:
        return Tile(label=label, value="—", state="Not offered", tone="mut")
    edge = row.get("edge")
    model = row.get("model")
    if edge is None:
        # No matched book price: show the model's own probability so the tile still carries
        # information, but leave it unpriced so it never counts as a pick.
        return Tile(
            label=label,
            value=f"{model:.0f}%" if isinstance(model, (int, float)) else "—",
            state=f"{_side_text(row)} · model only",
            tone="mut",
            note=str(row.get("reason") or "No book price matched this market."),
        )
    return Tile(
        label=label,
        value=f"{edge:+.1f}",
        state=f"{_side_text(row)} · {row.get('state') or ''}".strip(" ·"),
        tone=str(row.get("tone") or "mut"),
        note=str(row.get("reason") or ""),
        gem=_is_gem(row),
        priced=True,
    )


def _group(label: str, tag: str, spec, best: dict[str, dict]) -> Group | None:
    tiles = tuple(_tile(tile_label, best.get(key)) for key, tile_label in spec)
    if not any(tile.is_priced for tile in tiles):
        # Don't print an F5 shelf on a slate with no F5 prices — an empty group reads as a
        # broken section, while its absence reads as "not offered".
        if tag != "fullgame":
            return None
    priced = sum(1 for tile in tiles if tile.is_priced)
    return Group(label=label, tiles=tiles, tag=tag, state="Priced" if priced else "No price")


def _expected_runs(total, margin) -> tuple[str, str]:
    """Split the model's expected total and margin back into two team scores."""
    try:
        total_runs, edge_runs = float(total), float(margin)
    except (TypeError, ValueError):
        return "—", "—"
    home = (total_runs + edge_runs) / 2.0
    away = (total_runs - edge_runs) / 2.0
    return f"{away:.1f}", f"{home:.1f}"


def _drivers_group(report: dict | None) -> Group | None:
    """Lineup and bullpen state — the adjustments that silently do nothing when their feed
    is missing.

    Both are wired into the run model (`staff_factor` blends the pen in on a workload
    factor; `lineup_features` scales team runs off the posted order), but each falls back to
    a neutral 1.0 whenever the order is unposted or fewer than six batters match a profile.
    A neutral factor is indistinguishable from "not modelled" unless the card says which, so
    this shelf states it per side. Unpriced by construction — it explains the projection, it
    is not a market.
    """
    gd = (report or {}).get("gd")
    if gd is None:
        return None

    tiles: list[Tile] = []
    for side in ("away", "home"):
        lineup = getattr(gd, f"{side}_lineup_features", None) or {}
        team = str(getattr(gd, side, side)).upper()
        factor = float(lineup.get("factor") or 1.0)
        matched = int(lineup.get("matched_batters") or 0)
        status = str(lineup.get("status") or "unavailable")
        active = abs(factor - 1.0) > 1e-6
        tiles.append(Tile(
            label=f"{team} lineup",
            value=f"{(factor - 1.0) * 100:+.1f}%" if active else "flat",
            state=(f"{status} · {matched} matched" if active
                   else f"{status} · no adjustment"),
            tone="side" if active else "mut",
            note=(
                "Order posted and matched to batter profiles; team runs scaled by it."
                if active else
                "Fewer than six batters matched a profile, or no order posted — the lineup "
                "adjustment is inert for this game."
            ),
        ))

    for side in ("away", "home"):
        pen = getattr(gd, f"{side}_bullpen_features", None) or {}
        team = str(getattr(gd, side, side)).upper()
        workload = float(pen.get("workload_factor") or 1.0)
        tired = workload > 1.0
        tiles.append(Tile(
            label=f"{team} bullpen",
            value=f"+{(workload - 1.0) * 100:.1f}%" if tired else "rested",
            state="recent workload" if tired else "no recent load",
            tone="warnc" if tired else "mut",
            note=(
                "Pitches thrown in the previous two days raise this pen's expected runs "
                "allowed." if tired else
                "No qualifying appearances in the previous two days, so no workload penalty."
            ),
        ))

    return Group(
        label="Why this projection",
        tiles=tuple(tiles),
        tag="",
        state="Model inputs",
        market=False,
    )


def _principals(game: dict, report: dict | None) -> tuple[Principal, ...]:
    extras = (report or {}).get("extras") or {}

    def one(prefix: str, side: str, id_key: str) -> Principal:
        name = str(game.get(f"{prefix}sp") or "").strip()
        if not name:
            return Principal(name="TBD", team=game[side], stat="no probable")
        strikeouts, fip = game.get(f"{prefix}k"), game.get(f"{prefix}fip")
        bits = []
        if isinstance(strikeouts, (int, float)):
            bits.append(f"{strikeouts:.1f} K/9")
        if isinstance(fip, (int, float)):
            bits.append(f"{fip:.2f} FIP")
        return Principal(
            name=name,
            team=game[side],
            stat=" · ".join(bits),
            art_html=_headshot(extras.get(id_key)),
        )

    return (one("a", "away", "a_id"), one("h", "home", "h_id"))


def _headline(best: dict[str, dict]) -> tuple[str, str]:
    priced = [row for row in best.values() if row.get("edge") is not None]
    if not priced:
        return "No priced edge on this game", "mut"
    top = max(priced, key=lambda row: row["edge"])
    label = MKT_LABEL.get(str(top.get("market") or "").lower(), str(top.get("market") or ""))
    text = f"{label} {_side_text(top)} · {top['edge']:+.1f}pt"
    return text, ("pos" if _is_gem(top) else "side")


def build_card(game: dict, report: dict | None, sharp_count: int = 0) -> Card:
    key = game.get("key") or f'{game["away"]}@{game["home"]}'
    markets = (report or {}).get("markets") or []
    best = _best_by_family(markets)

    away_runs, home_runs = _expected_runs(game.get("total"), game.get("margin"))
    home_prob = game.get("ph")
    home_fav = isinstance(home_prob, (int, float)) and home_prob >= 0.5

    def win_text(probability) -> str:
        if not isinstance(probability, (int, float)):
            return ""
        return f"{probability * 100:.0f}% win"

    away_prob = (1.0 - float(home_prob)) if isinstance(home_prob, (int, float)) else None
    headline, headline_tone = _headline(best)

    groups = tuple(
        group
        for group in (
            _group("Full game", "fullgame", _FULL_GAME, best),
            _group("First 5 innings", "f5", _FIRST_FIVE, best),
            _drivers_group(report),
        )
        if group is not None
    )

    return Card(
        key=key,
        league="MLB",
        start_text=str(game.get("time") or ""),
        status_label=f"Sharp {sharp_count}" if sharp_count else "",
        status_tone="warnc" if sharp_count else "mut",
        away=Side(
            abbr=game["away"],
            score=away_runs,
            detail=win_text(away_prob),
            logo_html=_logo(game["away"], "tlogo"),
            favored=not home_fav,
        ),
        home=Side(
            abbr=game["home"],
            score=home_runs,
            detail=win_text(home_prob),
            logo_html=_logo(game["home"], "tlogo"),
            favored=home_fav,
        ),
        headline=headline,
        headline_tone=headline_tone,
        principals=_principals(game, report),
        principal_label="Starting pitchers",
        groups=groups,
        action_label="Price it",
        action_js=f"openGame('{key}')",
        footer_label="Full matchup breakdown",
        footer_js=f"openGame('{key}')",
        note="No priced markets — model projections only.",
    )


def build_board(slate, slate_date, reports_by_key, sharp_by_pk, sync=None) -> Board:
    """Assemble the MLB slate board. `reports_by_key` maps game key -> build_report dict."""
    cards = []
    for game in slate:
        if game.get("err"):
            continue
        key = game.get("key") or f'{game["away"]}@{game["home"]}'
        sharp = len(sharp_by_pk.get(game.get("pk"), []))
        cards.append(build_card(game, reports_by_key.get(key), sharp))

    sync = sync or {}
    sync_label = {"exact": "Exact", "fallback": "Live fallback"}.get(
        str(sync.get("status") or ""), "Untracked"
    )
    skipped = sum(1 for game in slate if game.get("err"))
    meta = [
        f"{len(cards)} games",
        str(slate_date or "slate pending"),
        f"sync {sync_label}",
    ]
    if skipped:
        meta.append(f"{skipped} without model inputs")

    return Board(
        sport="MLB",
        cards=cards,
        date_label=str(slate_date or ""),
        meta=meta,
        filters=[
            ("all", f"All {len(cards)}"),
            ("gems", "◆ Gems"),
            ("fullgame", "Full game"),
            ("f5", "First 5"),
        ],
        sorts=[("start", "Start time"), ("picks", "Priced markets"), ("gems", "Gems")],
        empty_text=(
            "No games on this slate yet. The board fills once the MLBMA pipeline publishes "
            "today's matchups."
        ),
    )
