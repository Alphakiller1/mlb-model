"""
Pitcher props — where the edge comes from, stated explicitly.

The previous version rendered two different quantities in one column called "Edge":

* a **book** edge, `model% − de-vigged market%` — a real edge against a price
* a **pick'em** number, `model% − 50%` — the model's distance from a coin flip, which is
  not an edge against anything, because a pick'em app charges its margin through the
  payout rather than through the line

A `+29.4pt` pick'em figure sitting in the same green column as a `+3.1pt` book edge made
the board unreadable: there was no way to tell which number represented money. So the two
channels are now separate tables with separate columns and separate verdicts.

**Priced edges** (sportsbooks / prediction markets) carry `Edge = model − de-vigged market`
and the EV that follows from it. This is the only column named Edge.

**Pick'em** carries `Model %` against the payout's breakeven hit rate — a power play needs
roughly 55–58% per leg to be profitable, so a 52% leg is a losing bet no matter how far it
sits from 50%. Non-standard (goblin/demon) lines are flagged because their payout, and so
their breakeven, is different and this repo does not store it.
"""
from __future__ import annotations

import html

from mlbmodel.market import prizepicks
from mlbmodel.market.probability import p_over_exact
from mlbmodel.report.html_fmt import edge_grade as _edge_grade, lean_dir_html, prob_chip_html
from mlbmodel.report.matchup import _headshot, _logo
from mlbmodel.report.pitch_mix_ui import pitch_mix_board_html

e = html.escape

_PICKEM_ORDER = ["PP_Fantasy", "K", "Outs", "ER", "H", "BB"]
_PROJ_KEYS = ("K", "Outs", "ER", "H", "BB", "Fantasy")
_FANTASY_BOOKS = frozenset({"prizepicks", "underdog", "sleeper"})

# Per-leg hit rate a standard power play must clear to break even, from the common payout
# ladder (2-pick 3x -> 0.577, 3-pick 5x -> 0.585, 4-pick 10x -> 0.562, 5-pick 20x -> 0.549).
# 0.577 is the strictest of the small slips, so clearing it clears the ladder.
PICKEM_BREAKEVEN = 0.577
_BREAKEVEN_NOTE = (
    "Power-play breakeven is about 55–58% per leg (2-pick 3× needs 57.7%, 3-pick 5× needs "
    "58.5%). A leg above 50% is not a bet; a leg above breakeven is."
)


def _p_over(line, projection):
    """P(over) from the simulated distribution — see market.probability.p_over_exact."""
    over, _push = p_over_exact(line, projection)
    return over


def _prop_label(prop_key: str) -> str:
    return prizepicks.STAT_LABEL.get(prop_key, str(prop_key))


def _norm_side(side) -> str:
    return str(side or "").strip().upper()


def _is_fantasy_report(rep: dict) -> bool:
    if str(rep.get("source") or "").lower() == "pickem":
        return True
    return str(rep.get("best_book") or "").lower() in _FANTASY_BOOKS


def play_lean_html(
    side,
    prop_key: str,
    line: float,
    *,
    edge=None,
    source: str | None = None,
    compact: bool = False,
) -> str:
    """Explicit play: ▲ OVER 5.5 Strikeouts · +4.0pt · DraftKings."""
    side_key = _norm_side(side)
    label = _prop_label(prop_key)
    if side_key not in {"OVER", "UNDER"}:
        return f'<span class="prop-play mut">{e(label)} {line:g}</span>'
    dir_html = lean_dir_html(side_key, as_pill=False)
    edge_html = ""
    if edge is not None:
        try:
            edge_html = f' <b class="{_edge_grade(edge)}">{float(edge) * 100:+.1f}pt</b>'
        except (TypeError, ValueError):
            pass
    book_html = (
        f' <span class="pill mut">{e(source)}</span>' if source and not compact else ""
    )
    return (
        f'<span class="prop-play">'
        f'{dir_html} <b class="prop-play__line">{line:g} {e(label)}</b>'
        f'{edge_html}{book_html}</span>'
    )


# ── channel 1: priced markets (a real edge against a de-vigged price) ─────────


def _priced_plays(row: dict) -> list[dict]:
    """Book / prediction-market reports, best edge first."""
    plays = []
    for rep in row.get("market_report") or []:
        if _is_fantasy_report(rep):
            continue
        plays.append({
            "source": str(rep.get("best_book") or "book"),
            "prop": rep["prop"],
            "line": rep["line"],
            "side": rep.get("side"),
            "model": rep.get("model_probability"),
            "market": rep.get("market_probability"),
            "price": rep.get("best_odds"),
            "fair": rep.get("market_fair_odds"),
            "hold": rep.get("hold"),
            "edge": rep.get("edge"),
            "ev": rep.get("ev"),
            "state": rep.get("state"),
            "books": rep.get("books"),
        })
    plays.sort(key=lambda p: -(p.get("edge") if p.get("edge") is not None else -1))
    return plays


def _priced_row(play: dict) -> str:
    edge = play.get("edge")
    if edge is None:
        edge_cell = '<span class=mut>—</span>'
    else:
        edge_cell = f'<b class="{_edge_grade(edge)}">{float(edge) * 100:+.1f}pt</b>'
    ev = play.get("ev")
    ev_cell = f'{float(ev):+.3f}u' if ev is not None else '<span class=mut>—</span>'
    price = play.get("price")
    price_cell = f'{int(price):+d}' if price is not None else '<span class=mut>—</span>'
    fair = play.get("fair")
    fair_cell = f'{int(fair):+d}' if fair is not None else '<span class=mut>—</span>'
    hold = play.get("hold")
    hold_cell = f'{float(hold):.1f}%' if hold is not None else '<span class=mut>—</span>'
    state = str(play.get("state") or "")
    tone = {"BET": "pos", "MONITOR": "warnc", "REVIEW": "warnc", "AVOID": "neg"}.get(state, "mut")
    books = play.get("books")
    return (
        f'<tr><td><span class="pill mut">{e(play["source"])}</span>'
        f'{f"<span class=mut> ×{books}</span>" if books else ""}</td>'
        f'<td>{e(_prop_label(play["prop"]))} '
        f'<b>{_norm_side(play["side"]).title()}</b></td>'
        f'<td class=num><b>{play["line"]:g}</b></td>'
        f'<td class=num>{price_cell}</td>'
        f'<td class=num>{fair_cell}</td>'
        f'<td class=num>{hold_cell}</td>'
        f'<td class=num>{prob_chip_html(play.get("market"))}</td>'
        f'<td class=num>{prob_chip_html(play.get("model"))}</td>'
        f'<td class=num>{edge_cell}</td>'
        f'<td class=num>{ev_cell}</td>'
        f'<td><span class="pill {tone}">{e(state or "—")}</span></td></tr>'
    )


def _priced_section(plays: list[dict]) -> str:
    head = (
        '<div class="prop-engine-section">'
        '<div class="ca-subhead">Priced markets</div>'
        '<p class="prop-basis">Edge = model probability − the book\'s de-vigged (hold-removed) '
        'probability. This is the only number here measured against real money.</p>'
    )
    if not plays:
        return (
            f'{head}<div class="prop-engine-empty">No sportsbook or prediction-market price '
            f'is stored for this starter, so no edge can be measured. The projection below '
            f'is a forecast, not an edge.</div></div>'
        )
    rows = "".join(_priced_row(play) for play in plays)
    return (
        f'{head}<div class=table-scroll><table class="prop-engine-table sortable">'
        f'<thead><tr><th>Book</th><th>Market</th><th class=num>Line</th>'
        f'<th class=num>Price</th><th class=num>Fair</th><th class=num>Hold</th>'
        f'<th class=num>Market&nbsp;%</th><th class=num>Model&nbsp;%</th>'
        f'<th class=num>Edge</th><th class=num>EV</th><th>Verdict</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></div>'
    )


# ── channel 2: pick'em (model probability against a payout breakeven) ─────────


def _pickem_from_reports(row: dict) -> list[dict]:
    """Pick'em legs already shaped as market rows.

    `pickem_market_reports` writes pick'em lines into `market_report` when the Odds API has
    no props for a starter, so the live boards are not the only source. Reading only the
    boards dropped those legs entirely whenever a snapshot failed to load.
    """
    plays = []
    for rep in row.get("market_report") or []:
        if not _is_fantasy_report(rep):
            continue
        model = rep.get("model_probability")
        if model is None:
            continue
        odds_type = str(rep.get("odds_type") or "standard")
        plays.append({
            "source": str(rep.get("best_book") or "pick'em").title(),
            "prop": rep["prop"],
            "line": rep["line"],
            "side": _norm_side(rep.get("side")),
            "model": float(model),
            "odds_type": odds_type,
            "clears": (float(model) >= PICKEM_BREAKEVEN) if odds_type == "standard" else None,
        })
    plays.sort(key=lambda p: -p["model"])
    return plays


def _pickem_plays(row: dict, sources: list[tuple[str, dict]]) -> list[dict]:
    name_key = prizepicks.normalize_name(row.get("pitcher"))
    projections = row.get("projections") or {}
    plays = []
    for book_label, board in sources:
        lines = board.get(name_key, {})
        if not lines:
            continue
        for key in _PICKEM_ORDER:
            line_obj, proj = lines.get(key), projections.get(key)
            if not line_obj or not proj:
                continue
            p_over = _p_over(line_obj["line"], proj)
            side = "OVER" if p_over >= 0.5 else "UNDER"
            model = p_over if side == "OVER" else 1 - p_over
            odds_type = str(line_obj.get("odds_type") or "standard")
            plays.append({
                "source": book_label,
                "prop": key,
                "line": line_obj["line"],
                "side": side,
                "model": model,
                "odds_type": odds_type,
                # Only a standard line has the payout ladder this breakeven is drawn from.
                "clears": (model >= PICKEM_BREAKEVEN) if odds_type == "standard" else None,
            })
    if not plays:
        return _pickem_from_reports(row)
    plays.sort(key=lambda p: -p["model"])
    return plays


def _pickem_row(play: dict) -> str:
    model = play["model"]
    odds_type = play["odds_type"]
    if play["clears"] is None:
        verdict = (
            f'<span class="pill mut" title="Payout for {e(odds_type)} lines is not stored, '
            f'so its breakeven is unknown">{e(odds_type)} payout</span>'
        )
        margin_cell = '<span class=mut>—</span>'
    else:
        margin = (model - PICKEM_BREAKEVEN) * 100
        verdict = (
            '<span class="pill pos">Clears</span>' if play["clears"]
            else '<span class="pill neg">Short</span>'
        )
        cls = "c-good" if play["clears"] else "c-poor"
        margin_cell = f'<b class="{cls}">{margin:+.1f}pt</b>'
    return (
        f'<tr><td><span class="pill mut">{e(play["source"])}</span></td>'
        f'<td>{e(_prop_label(play["prop"]))} <b>{play["side"].title()}</b></td>'
        f'<td class=num><b>{play["line"]:g}</b></td>'
        f'<td class=num>{prob_chip_html(model)}</td>'
        f'<td class=num><span class=mut>{PICKEM_BREAKEVEN * 100:.1f}%</span></td>'
        f'<td class=num>{margin_cell}</td>'
        f'<td>{verdict}</td></tr>'
    )


def _pickem_section(plays: list[dict]) -> str:
    head = (
        '<div class="prop-engine-section">'
        '<div class="ca-subhead">Pick\'em</div>'
        f'<p class="prop-basis">{_BREAKEVEN_NOTE}</p>'
    )
    if not plays:
        return (
            f'{head}<div class="prop-engine-empty">No PrizePicks, Underdog or Sleeper line '
            f'for this starter.</div></div>'
        )
    rows = "".join(_pickem_row(play) for play in plays)
    return (
        f'{head}<div class=table-scroll><table class="prop-engine-table sortable">'
        f'<thead><tr><th>App</th><th>Market</th><th class=num>Line</th>'
        f'<th class=num>Model&nbsp;%</th><th class=num>Breakeven</th>'
        f'<th class=num>Margin</th><th>Verdict</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></div>'
    )


# ── the headline: only ever a number that means money ────────────────────────


def _primary_lean_banner(row: dict, sources: list[tuple[str, dict]]) -> str:
    """Best actionable play. A priced edge outranks a pick'em leg, because it is measured
    against a real price; a pick'em leg only surfaces here if it clears its breakeven."""
    if row.get("projection_trust") != "trusted":
        return '<span class="pill warnc">Thin data — projection not trusted</span>'
    priced = [p for p in _priced_plays(row) if p.get("edge") is not None]
    flagged = [p for p in priced if p.get("state") == "REVIEW"]
    usable = [p for p in priced if p.get("state") != "REVIEW" and (p.get("edge") or 0) > 0]
    if usable:
        best = usable[0]
        return play_lean_html(
            best["side"], best["prop"], best["line"],
            edge=best.get("edge"), source=best["source"],
        )
    if flagged:
        # Say why the biggest number on the card is not the headline.
        return (
            f'<span class="pill warnc">Inputs under review — '
            f'{flagged[0]["edge"] * 100:+.0f}pt on {e(_prop_label(flagged[0]["prop"]))} '
            f'is too large to trust</span>'
        )
    clearing = [p for p in _pickem_plays(row, sources) if p.get("clears")]
    if clearing:
        best = clearing[0]
        return (
            f'{play_lean_html(best["side"], best["prop"], best["line"], source=best["source"])}'
            f' <span class="pill pos">{best["model"] * 100:.0f}% vs {PICKEM_BREAKEVEN * 100:.0f}% needed</span>'
        )
    return '<span class="pill mut">No priced edge</span>'


def _projection_strip(projections: dict) -> str:
    """Model forecast with its uncertainty — the input every edge on this card comes from."""
    cells = []
    for key in _PROJ_KEYS:
        proj = projections.get(key) or {}
        mean = proj.get("mean")
        if mean is None:
            continue
        sd = proj.get("sd")
        spread = f'<i class="prop-proj__sd">±{float(sd):.1f}</i>' if sd else ""
        cells.append(
            f'<span class="prop-proj__cell">'
            f'<i class="prop-proj__k">{e(_prop_label(key) if key != "Fantasy" else "Fantasy")}</i>'
            f'<b class="prop-proj__v">{float(mean):.1f}</b>{spread}</span>'
        )
    if not cells:
        return ""
    return (
        '<div class="prop-proj-strip">'
        '<span class="prop-proj__label">Projection</span>'
        f'{"".join(cells)}</div>'
    )


def _context_strip(row: dict) -> str:
    """Why the projection is what it is — sample, workload and opponent context."""
    bits = []
    ip = row.get("expected_ip")
    if isinstance(ip, (int, float)):
        bits.append(f'Expected IP <b>{float(ip):.1f}</b>')
    # k_rate/bb_rate are already percentages (K_pct), not fractions — scaling them by 100
    # printed "K rate 1923.0%".
    k_rate = row.get("k_rate")
    if isinstance(k_rate, (int, float)):
        bits.append(f'K rate <b>{float(k_rate):.1f}%</b>')
    bb_rate = row.get("bb_rate")
    if isinstance(bb_rate, (int, float)):
        bits.append(f'BB rate <b>{float(bb_rate):.1f}%</b>')
    era = row.get("skill_era")
    if isinstance(era, (int, float)):
        bits.append(f'Skill ERA <b>{float(era):.2f}</b>')
    coverage = row.get("data_coverage_pct")
    if isinstance(coverage, (int, float)):
        bits.append(f'Data coverage <b>{float(coverage):.0f}%</b>')
    trust = str(row.get("projection_trust") or "")
    if trust:
        bits.append(f'Trust <b>{e(trust)}</b>')
    lineup = str(row.get("lineup_status") or "")
    if lineup:
        bits.append(f'Lineup <b>{e(lineup)}</b>')
    if not bits:
        return ""
    return f'<div class="prop-context">{" · ".join(bits)}</div>'


def pitcher_prop_card(
    index: int,
    row: dict,
    *,
    pickem_sources: list[tuple[str, dict]],
    expanded: bool = False,
) -> str:
    projections = row.get("projections") or {}
    pitch_matchup = row.get("pitch_matchup") or {}
    primary = _primary_lean_banner(row, pickem_sources)

    pitch_mix = ""
    if pitch_matchup.get("pitches"):
        pitch_mix = (
            f'<div class="prop-engine-section">'
            f'<div class="ca-subhead">Why — pitch mix vs this lineup</div>'
            f'{pitch_mix_board_html(pitch_matchup, compact=True)}</div>'
        )

    on_cls = " on" if expanded else ""
    return f"""<div class="pitcher-prop-card{on_cls}" id="prop-card-{index}">
  <button type=button class=pitcher-prop-head onclick="togglePitcherCard({index})" aria-expanded="{'true' if expanded else 'false'}">
    <div class=pitcher-prop-id>{_headshot(row.get("pitcher_id"))}
      <div><b>{e(str(row.get("pitcher") or "TBD"))}</b>
        <span class=pitcher-prop-meta>{_logo(row.get("team"), "tlogo sm")}{e(str(row.get("team") or ""))}
        <span class=mut>@</span> {_logo(row.get("opponent"), "tlogo sm")}{e(str(row.get("opponent") or ""))}</span>
      </div>
    </div>
    <div class=pitcher-prop-summary>
      <div class="prop-primary-lean">{primary}</div>
    </div>
    <span class=pitcher-prop-chevron aria-hidden=true>▸</span>
  </button>
  <div class=pitcher-prop-body>
    {_projection_strip(projections)}
    {_context_strip(row)}
    {_priced_section(_priced_plays(row))}
    {_pickem_section(_pickem_plays(row, pickem_sources))}
    {pitch_mix}
  </div>
</div>"""


def prop_channel_counts(
    pitchers: list[dict],
    pickem_sources: list[tuple[str, dict]],
) -> tuple[int, int]:
    book_n = sum(len(_priced_plays(row)) for row in pitchers)
    fantasy_n = sum(len(_pickem_plays(row, pickem_sources)) for row in pitchers)
    return book_n, fantasy_n


def actionable_counts(
    pitchers: list[dict],
    pickem_sources: list[tuple[str, dict]],
) -> tuple[int, int]:
    """Plays that actually clear their own bar — a priced positive edge, or a pick'em leg
    above breakeven. This is the number worth putting at the top of the page; a raw count
    of available lines says nothing about whether any of them are worth taking."""
    # REVIEW rows are excluded: an edge flagged implausible is evidence of a bad input, and
    # counting it as an opportunity is how a broken projection becomes a headline number.
    edges = sum(
        1
        for row in pitchers
        for play in _priced_plays(row)
        if (play.get("edge") or 0) > 0 and play.get("state") != "REVIEW"
    )
    clears = sum(
        1
        for row in pitchers
        for play in _pickem_plays(row, pickem_sources)
        if play.get("clears")
    )
    return edges, clears


def pitcher_prop_deck(
    pitchers: list[dict],
    pickem_sources: list[tuple[str, dict]],
) -> str:
    if not pitchers:
        return '<div class=empty>No pitcher inputs loaded.</div>'
    # Rank by what is actionable, not by name order: a starter carrying a real priced edge
    # belongs above one with nothing to bet.
    def rank(row):
        priced = [p for p in _priced_plays(row) if p.get("edge") is not None]
        best_edge = max((p["edge"] for p in priced), default=None)
        clears = [p for p in _pickem_plays(row, pickem_sources) if p.get("clears")]
        best_clear = max((p["model"] for p in clears), default=None)
        return (
            0 if best_edge is not None else (1 if best_clear is not None else 2),
            -(best_edge if best_edge is not None else (best_clear or 0)),
        )

    ordered = sorted(pitchers, key=rank)
    cards = []
    expanded_count = 0
    for index, row in enumerate(ordered):
        actionable = bool(
            [p for p in _priced_plays(row) if p.get("edge") is not None]
            or [p for p in _pickem_plays(row, pickem_sources) if p.get("clears")]
        )
        expanded = actionable and expanded_count < 3
        if expanded:
            expanded_count += 1
        cards.append(
            pitcher_prop_card(
                index, row, pickem_sources=pickem_sources, expanded=expanded
            )
        )
    return f'<div class=pitcher-prop-deck>{"".join(cards)}</div>'
