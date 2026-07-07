"""Pitcher props — one toggle per starter; book vs fantasy split inside each card."""
from __future__ import annotations

import html

from mlbmodel.market import prizepicks
from mlbmodel.market.probability import p_over_line_erf
from mlbmodel.report.html_fmt import edge_grade as _edge_grade, lean_dir_html, prob_chip_html
from mlbmodel.report.matchup import _headshot, _logo
from mlbmodel.report.pitch_mix_ui import pitch_mix_board_html

e = html.escape

_PICKEM_ORDER = ["PP_Fantasy", "K", "Outs", "ER", "H", "BB"]
_PROJ_KEYS = ("K", "BB", "ER", "Outs", "H", "Fantasy")
_FANTASY_BOOKS = frozenset({"prizepicks", "underdog", "sleeper"})


def _p_over(line, mean, sd):
    return p_over_line_erf(line, mean, sd or 0)


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
    """Explicit play: ▲ OVER 5.5 Strikeouts · +4.0pt · Underdog."""
    side_key = _norm_side(side)
    label = _prop_label(prop_key)
    if side_key not in {"OVER", "UNDER"}:
        return f'<span class="prop-play mut">{e(label)} {line:g}</span>'
    dir_html = lean_dir_html(side_key, as_pill=False)
    edge_html = ""
    if edge is not None:
        try:
            edge_html = (
                f' <b class="{_edge_grade(edge)}">{float(edge) * 100:+.1f}pt</b>'
            )
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


def _play_score(edge, model_prob) -> float:
    try:
        if edge is not None:
            return abs(float(edge))
    except (TypeError, ValueError):
        pass
    if model_prob is not None:
        try:
            return abs(float(model_prob) - 0.5)
        except (TypeError, ValueError):
            pass
    return 0.0


def _report_to_play(rep: dict, *, channel: str) -> dict:
    book = str(rep.get("best_book") or ("pick'em" if channel == "fantasy" else "sportsbook"))
    return {
        "channel": channel,
        "source": book,
        "prop": rep["prop"],
        "line": rep["line"],
        "side": rep.get("side"),
        "model": rep.get("model_probability"),
        "edge": rep.get("edge"),
        "price": rep.get("best_odds"),
        "odds_type": rep.get("odds_type"),
    }


def _book_plays(row: dict) -> list[tuple[float, dict]]:
    plays: list[tuple[float, dict]] = []
    for rep in row.get("market_report") or []:
        if _is_fantasy_report(rep):
            continue
        play = _report_to_play(rep, channel="book")
        plays.append((_play_score(play.get("edge"), play.get("model")), play))
    plays.sort(key=lambda item: -item[0])
    return plays


def _pickem_plays(row: dict, sources: list[tuple[str, dict]]) -> list[tuple[float, dict]]:
    name_key = prizepicks.normalize_name(row.get("pitcher"))
    projections = row.get("projections") or {}
    plays: list[tuple[float, dict]] = []
    for book_label, board in sources:
        lines = board.get(name_key, {})
        if not lines:
            continue
        for key in _PICKEM_ORDER:
            line_obj, proj = lines.get(key), projections.get(key)
            if not line_obj or not proj:
                continue
            mean, sd = proj.get("mean"), proj.get("sd")
            p_over = _p_over(line_obj["line"], mean, sd or 0)
            side = "OVER" if p_over >= 0.5 else "UNDER"
            edge = p_over - 0.5
            play = {
                "channel": "fantasy",
                "source": book_label,
                "prop": key,
                "line": line_obj["line"],
                "side": side,
                "model": p_over,
                "edge": edge,
                "price": None,
                "odds_type": line_obj.get("odds_type"),
            }
            plays.append((abs(edge), play))
    plays.sort(key=lambda item: -item[0])
    return plays


def _fantasy_plays(row: dict, sources: list[tuple[str, dict]]) -> list[dict]:
    from_boards = [play for _, play in _pickem_plays(row, sources)]
    if from_boards:
        return from_boards
    fallback: list[tuple[float, dict]] = []
    for rep in row.get("market_report") or []:
        if not _is_fantasy_report(rep):
            continue
        play = _report_to_play(rep, channel="fantasy")
        fallback.append((_play_score(play.get("edge"), play.get("model")), play))
    fallback.sort(key=lambda item: -item[0])
    return [play for _, play in fallback]


def _book_market_plays(row: dict) -> list[dict]:
    return [play for _, play in _book_plays(row)]


def _all_plays(row: dict, sources: list[tuple[str, dict]]) -> list[dict]:
    ranked = _book_plays(row) + _pickem_plays(row, sources)
    ranked.sort(key=lambda item: -item[0])
    return [play for _, play in ranked]


def _primary_lean_banner(row: dict, sources: list[tuple[str, dict]]) -> str:
    if row.get("projection_trust") != "trusted":
        return '<span class="pill warnc">Thin data</span>'
    plays = _all_plays(row, sources)
    if not plays:
        return '<span class="pill mut">No priced line</span>'
    play = plays[0]
    return play_lean_html(
        play["side"],
        play["prop"],
        play["line"],
        edge=play.get("edge"),
        source=play["source"],
    )


def _projection_strip(projections: dict) -> str:
    cells = []
    for key in _PROJ_KEYS:
        val = (projections.get(key) or {}).get("mean")
        if val is None:
            continue
        cells.append(f'<span><i>{e(key)}</i><b>{val:.1f}</b></span>')
    if not cells:
        return ""
    return f'<div class="prop-proj-strip prop-proj-strip--inline">{"".join(cells)}</div>'


def _engine_table_row(play: dict) -> str:
    prop_label = _prop_label(play["prop"])
    variant = ""
    if play.get("odds_type") and play["odds_type"] != "standard":
        variant = f' <span class="mut odds-variant">{e(str(play["odds_type"]))}</span>'
    if play.get("price") is not None:
        price_cell = f'{int(play["price"]):+d}'
    elif play.get("channel") == "fantasy":
        price_cell = '<span class=mut>pick&apos;em</span>'
    else:
        price_cell = '<span class=mut>—</span>'
    model_cell = prob_chip_html(play.get("model"))
    edge_val = play.get("edge")
    if edge_val is not None:
        edge_cell = f'<b class="{_edge_grade(edge_val)}">{float(edge_val) * 100:+.1f}pt</b>'
    else:
        edge_cell = '<span class=mut>—</span>'
    return (
        f'<tr><td><span class="pill mut">{e(play["source"])}</span></td>'
        f'<td>{e(prop_label)}{variant}</td>'
        f'<td class=num><b>{play["line"]:g}</b></td>'
        f'<td>{price_cell}</td>'
        f'<td class=num>{model_cell}</td>'
        f'<td class=num>{edge_cell}</td>'
        f'<td>{play_lean_html(play["side"], play["prop"], play["line"], compact=True)}</td></tr>'
    )


def _plays_section(title: str, plays: list[dict], *, empty: str) -> str:
    if not plays:
        return (
            f'<div class="prop-engine-section">'
            f'<div class="ca-subhead">{title}</div>'
            f'<div class="prop-engine-empty">{empty}</div></div>'
        )
    rows = "".join(_engine_table_row(play) for play in plays)
    return (
        f'<div class="prop-engine-section">'
        f'<div class="ca-subhead">{title}</div>'
        f'<div class=table-scroll><table class="prop-engine-table sortable">'
        f'<tr><th>Book</th><th>Stat</th><th>Line</th><th>Price</th>'
        f'<th>Model</th><th>Edge</th><th>Play</th></tr>{rows}</table></div></div>'
    )


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
    proj_strip = _projection_strip(projections)

    book_section = _plays_section(
        "Book &amp; prediction market",
        _book_market_plays(row),
        empty="No sportsbook or prediction-market lines for this starter.",
    )
    fantasy_section = _plays_section(
        "Fantasy",
        _fantasy_plays(row, pickem_sources),
        empty="No PrizePicks, Underdog, or Sleeper lines for this starter.",
    )

    pitch_mix = ""
    if pitch_matchup.get("pitches"):
        pitch_mix = (
            f'<div class="prop-engine-pitchmix">'
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
    {proj_strip}
    {book_section}
    {fantasy_section}
    {pitch_mix}
  </div>
</div>"""


def prop_channel_counts(
    pitchers: list[dict],
    pickem_sources: list[tuple[str, dict]],
) -> tuple[int, int]:
    book_n = sum(len(_book_market_plays(row)) for row in pitchers)
    fantasy_n = sum(len(_fantasy_plays(row, pickem_sources)) for row in pitchers)
    return book_n, fantasy_n


def pitcher_prop_deck(
    pitchers: list[dict],
    pickem_sources: list[tuple[str, dict]],
) -> str:
    if not pitchers:
        return '<div class=empty>No pitcher inputs loaded.</div>'
    cards = []
    expanded_count = 0
    for index, row in enumerate(pitchers):
        has_play = bool(
            _book_market_plays(row) or _fantasy_plays(row, pickem_sources)
        )
        expanded = has_play and expanded_count < 3
        if expanded:
            expanded_count += 1
        cards.append(
            pitcher_prop_card(
                index, row, pickem_sources=pickem_sources, expanded=expanded
            )
        )
    return f'<div class=pitcher-prop-deck>{"".join(cards)}</div>'
