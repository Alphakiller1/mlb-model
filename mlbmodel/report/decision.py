"""Sharp + model decision fusion for the Markets board."""
from __future__ import annotations

import html

from mlbmodel.report.html_fmt import edge_grade, pct_chip_html, section_head

from mlbmodel.leans.decision_calibration import DecisionThresholds, DEFAULT_THRESHOLDS

e = html.escape

MKT_LABEL = {
    "moneyline": "Moneyline", "h2h": "Moneyline", "ml": "Moneyline",
    "total": "Total", "totals": "Total",
    "spread": "Run line", "spreads": "Run line", "run_line": "Run line", "runline": "Run line",
    "f5_ml": "F5 ML", "f5_total": "F5 Total", "f5_runline": "F5 Run line",
}

_MKT_ALIASES = {
    "moneyline": "ml", "h2h": "ml", "ml": "ml",
    "total": "total", "totals": "total",
    "spread": "runline", "spreads": "runline", "run_line": "runline", "runline": "runline",
    "f5_ml": "f5_ml", "f5_total": "f5_total", "f5_runline": "f5_runline",
}


def _normalize_market(market: str) -> str:
    return _MKT_ALIASES.get(str(market or "").lower(), str(market or "").lower())


def _play_key(pk, market: str, side, line) -> tuple:
    return (pk, _normalize_market(market), str(side or "").strip().lower(), line)


def _model_row_match(model_rows: list[dict] | None, mkt_type: str, sel: str) -> dict | None:
    target = _normalize_market(mkt_type)
    sel_l = str(sel or "").strip().lower()
    for row in model_rows or []:
        if _normalize_market(str(row.get("market") or "")) != target:
            continue
        if str(row.get("side") or "").strip().lower() == sel_l:
            return row
    return None

_VERDICT = {
    "STRONG":  (4, 2.0, "#2dd4bf", "rgba(45,212,191,.16)", "Sharp + model agree, price gives value"),
    "BET":     (3, 1.0, "#36d399", "rgba(54,211,153,.14)", "Sharp + model agree at a fair-or-better #"),
    "LEAN":    (2, 0.5, "#f5b14c", "rgba(245,177,76,.14)", "Right side, but the price is gone — wait for a number"),
    "SHARP":   (1, 0.5, "#9A6BFF", "rgba(154,107,255,.14)", "Sharp lean only — model/price hasn't confirmed"),
    "MODEL":   (2, 0.0, "#A78BFA", "rgba(167,139,250,.12)", "Model fair value — post a line at or better than fair"),
    "CONFLICT":(0, 0.0, "#f87171", "rgba(248,113,113,.14)", "Sharp and the model disagree — pass"),
}

_VERDICT_LABEL = {
    "STRONG": "STRONG BET", "BET": "BET", "LEAN": "LEAN",
    "SHARP": "SHARP-ONLY", "MODEL": "FAIR VALUE", "CONFLICT": "PASS",
}


def verdict_label(verdict: str) -> str:
    return _VERDICT_LABEL[verdict]


_VERDICT_CLASS = {
    "STRONG": "pos",
    "BET": "pos",
    "LEAN": "warnc",
    "SHARP": "mut",
    "MODEL": "side",
    "CONFLICT": "neg",
}


def verdict_badge(verdict: str) -> str:
    return (
        f'<span class="pill {_VERDICT_CLASS[verdict]}">'
        f'{_VERDICT_LABEL[verdict]}</span>'
    )


def _sel_match(model_side, sharp_sel) -> bool:
    return str(model_side or "").strip().lower() == str(sharp_sel or "").strip().lower()


def decide(
    signal: dict,
    model_rows: list[dict] | None,
    thresholds: DecisionThresholds | None = None,
) -> dict:
    """Fuse one sharp signal with the model's read on the same bet."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    div = float(signal.get("divergence") or 0)
    div_pts = div * 100
    sharp_p = float(signal.get("sharp_novig_prob") or 0) * 100
    soft_p = float(signal.get("soft_novig_prob") or 0) * 100
    mkt_type = str(signal.get("market_type") or "").lower()
    sel = str(signal.get("selection") or "")

    match = _model_row_match(model_rows, mkt_type, sel)
    model_p = match.get("model") if match else None
    medge = match.get("edge") if match else None
    ev = match.get("ev") if match else None
    price = match.get("mkt") if match else None
    fair = match.get("fair") if match else None
    book = match.get("book") if match else None

    model_supports = model_p is not None and model_p >= soft_p
    has_price = price is not None and medge is not None
    if not match:
        verdict = "SHARP"
    elif has_price and medge >= thresholds.strong_edge and div_pts >= thresholds.strong_div and (ev or 0) > 0:
        verdict = "STRONG"
    elif has_price and medge >= thresholds.bet_edge and (ev or 0) > 0:
        verdict = "BET"
    elif model_supports:
        verdict = "LEAN"
    else:
        verdict = "CONFLICT"

    rank, stake, _fg, _bg, _why = _VERDICT[verdict]
    score = rank * 1000 + div_pts + max(0.0, medge or 0)
    return {
        "verdict": verdict, "stake": stake, "score": score,
        "mkt_type": mkt_type, "sel": sel, "div_pts": div_pts,
        "sharp_p": sharp_p, "soft_p": soft_p,
        "model_p": model_p, "medge": medge, "ev": ev,
        "price": price, "fair": fair, "book": book,
        "market_line": match.get("line") if match else None,
        "entry_odds": price if isinstance(price, int) else None,
        "n_sharp": signal.get("n_sharp_books"), "n_soft": signal.get("n_soft_books"),
        "steam": bool(signal.get("steam_flag")),
    }


def collect_model_market_plays(
    slate,
    model_by_pk: dict[int, list[dict]],
    thresholds: DecisionThresholds | None = None,
) -> list[dict]:
    """Model fair values and priced edges — fills the board when sharp signals are absent."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    pkmap = {g["pk"]: f'{g["away"]}@{g["home"]}' for g in slate if "pk" in g}
    plays: list[dict] = []
    rank_base = {"STRONG": 4, "BET": 3, "LEAN": 2, "MODEL": 2, "SHARP": 1, "CONFLICT": 0}

    for pk, rows in (model_by_pk or {}).items():
        game = pkmap.get(pk, str(pk))
        for market in rows or []:
            model_p = market.get("model")
            mkt_type = str(market.get("market") or "")
            norm = _normalize_market(mkt_type)
            if norm not in {"ml", "total", "runline", "f5_ml", "f5_total", "f5_runline"}:
                continue
            if model_p is None:
                continue

            pseudo_edge = abs(float(model_p) - 50.0)
            has_price = market.get("mkt") is not None
            edge = market.get("edge")
            ev = market.get("ev")
            state = str(market.get("state") or "NO EDGE")
            if (
                has_price
                and edge is not None
                and float(edge) >= thresholds.strong_edge
                and (ev or 0) > 0
                and state == "BET"
            ):
                verdict = "STRONG"
            elif has_price and edge is not None and float(edge) >= thresholds.bet_edge and (ev or 0) > 0:
                verdict = "BET"
            elif has_price and state in {"MONITOR", "REVIEW", "BET"}:
                verdict = "LEAN"
            elif has_price:
                verdict = "LEAN" if pseudo_edge >= 2.0 else "CONFLICT"
            else:
                verdict = "MODEL"

            stake = _VERDICT[verdict][1] if verdict != "MODEL" else 0.0
            score = (
                rank_base.get(verdict, 0) * 1000
                + float(edge if edge is not None else pseudo_edge)
            )
            plays.append({
                "verdict": verdict,
                "stake": stake,
                "score": score,
                "mkt_type": mkt_type,
                "sel": str(market.get("side") or ""),
                "div_pts": 0.0,
                "sharp_p": None,
                "soft_p": None,
                "model_p": model_p,
                "medge": edge,
                "ev": ev,
                "price": market.get("mkt"),
                "fair": market.get("fair"),
                "book": market.get("book"),
                "market_line": market.get("line"),
                "entry_odds": market.get("mkt") if isinstance(market.get("mkt"), int) else None,
                "n_sharp": None,
                "n_soft": None,
                "steam": False,
                "pk": pk,
                "game": game,
                "source": "model",
            })

    plays.sort(key=lambda row: -row["score"])
    return plays


def collect_market_plays(
    slate,
    sharp_by_pk,
    model_by_pk,
    thresholds: DecisionThresholds | None = None,
) -> list[dict]:
    pkmap = {g["pk"]: f'{g["away"]}@{g["home"]}' for g in slate if "pk" in g}
    plays = []
    seen: set[tuple] = set()
    for pk, sigs in sharp_by_pk.items():
        for sig in sigs:
            play = decide(sig, model_by_pk.get(pk), thresholds)
            play["pk"], play["game"] = pk, pkmap.get(pk, str(pk))
            play["source"] = "sharp"
            plays.append(play)
            seen.add(_play_key(pk, play["mkt_type"], play["sel"], play.get("market_line")))

    for play in collect_model_market_plays(slate, model_by_pk or {}, thresholds):
        key = _play_key(play["pk"], play["mkt_type"], play["sel"], play.get("market_line"))
        if key in seen:
            continue
        seen.add(key)
        plays.append(play)

    plays.sort(key=lambda row: -row["score"])
    return plays


def _num(odds):
    return f"{odds:+d}" if isinstance(odds, int) else "—"


def _fmt_line(line) -> str:
    if line is None:
        return ""
    try:
        return f" {float(line):g}"
    except (TypeError, ValueError):
        return f" {line}"


def markets_html(
    slate,
    sharp_by_pk,
    model_by_pk=None,
    thresholds: DecisionThresholds | None = None,
) -> str:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    plays = collect_market_plays(slate, sharp_by_pk, model_by_pk or {}, thresholds)

    def row(play):
        mkt = MKT_LABEL.get(play["mkt_type"], play["mkt_type"].title())
        if isinstance(play["price"], int):
            bet = (
                f'<b>{e(mkt)} {e(play["sel"])}</b> <span class="pill side">{_num(play["price"])}</span>'
                + (f' <span class=mut>{e(str(play["book"]))}</span>' if play["book"] else "")
                + (
                    f'<div class="mut meta-sub">fair {_num(play["fair"])}</div>'
                    if isinstance(play["fair"], int) else ""
                )
            )
        elif isinstance(play.get("fair"), int):
            line_txt = _fmt_line(play.get("market_line"))
            bet = (
                f'<b>{e(mkt)} {e(play["sel"])}{line_txt}</b>'
                f'<div class="mut meta-sub">fair {_num(play["fair"])} · no live #</div>'
            )
        else:
            bet = f'<b>{e(mkt)} {e(play["sel"])}</b><div class="mut meta-sub">no live #</div>'
        sharp = (
            f'<b class={edge_grade(play["div_pts"] / 100)}>+{play["div_pts"]:.1f}pt</b>'
            f'<div class="mut meta-sub">{play["sharp_p"]:.0f}% vs {play["soft_p"]:.0f}% pub</div>'
            + ('<span class="pill warnc hold-tag">STEAM</span>' if play["steam"] else "")
            if play.get("sharp_p") is not None and play.get("soft_p") is not None
            else '<span class=mut>—</span>'
        )
        if play["medge"] is not None:
            ev_txt = f'{play["ev"] * 100:+.1f}% EV' if play["ev"] is not None else ""
            model = (
                f'<b class={edge_grade(play["medge"] / 100)}>{play["medge"]:+.1f}pt</b>'
                f'<div class="mut meta-sub">model {pct_chip_html(play["model_p"], digits=0)} · {ev_txt}</div>'
            )
        elif play["model_p"] is not None:
            model = f'<span class=mut>{pct_chip_html(play["model_p"], digits=0)} · no live #</span>'
        else:
            model = '<span class=mut>—</span>'
        stake = (
            f'<b class="{_VERDICT_CLASS[play["verdict"]]}">{play["stake"]:.1f}u</b>'
            if play["stake"] else '<span class=mut>—</span>'
        )
        return (
            f'<tr><td><button class=gamepick onclick="openGame(\'{e(play["game"])}\')">{e(play["game"])}</button></td>'
            f'<td>{bet}</td><td>{sharp}</td><td>{model}</td>'
            f'<td title="{e(_VERDICT[play["verdict"]][4])}">{verdict_badge(play["verdict"])}</td>'
            f'<td class=num>{stake}</td></tr>'
        )

    rows = "".join(row(play) for play in plays) or (
        '<tr><td class=mut colspan=6>No model markets on slate — sync MLBMA data and rebuild.</td></tr>'
    )
    n_bet = sum(1 for play in plays if play["verdict"] in ("STRONG", "BET"))
    n_lean = sum(1 for play in plays if play["verdict"] in ("LEAN", "MODEL"))
    n_pass = sum(1 for play in plays if play["verdict"] == "CONFLICT")
    exposure = sum(play["stake"] for play in plays)
    top = plays[0] if plays else None
    top_txt = (
        f'{top["game"]} · {MKT_LABEL.get(top["mkt_type"], top["mkt_type"].title())} {top["sel"]}'
        if top else "—"
    )
    top_sub = f'{verdict_label(top["verdict"])} · {_VERDICT[top["verdict"]][4]}' if top else ""
    cal_note = (
        f'<div class="mut mut-sm">{e(thresholds.summary())}</div>'
        if thresholds.calibrated else ""
    )
    return f"""<h2>Markets</h2>
 <div class=cards>
   <div class=card><div class=k>Top play</div><div class="v v-sm">{e(top_txt)}</div>
     <div class="mut mut-sm">{e(top_sub)}</div></div>
   <div class=card><div class=k>Bets</div><div class=v>{n_bet}</div></div>
   <div class=card><div class=k>Leans</div><div class=v>{n_lean}</div></div>
   <div class=card><div class=k>Exposure</div><div class=v>{exposure:.1f}u</div>
     <div class="mut mut-sm">{n_pass} pass</div></div>
 </div>
 <div class=ca-board>{section_head("Decision board", icon="markets")}<div class=body>
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter game or bet…" data-filter-for="markets-table" aria-label="Filter markets"></div>
   <div class=table-scroll><table id=markets-table class=sortable><tr><th>Game</th><th>Bet</th>
   <th title="Sharp-book de-vig minus public">Sharp</th>
   <th title="Model edge vs live price">Model</th>
   <th>Verdict</th><th>Stake</th></tr>{rows}</table></div>
 {cal_note}
 </div></div>"""
