"""Sharp + model decision fusion for the Markets board."""
from __future__ import annotations

import html

from mlbmodel.report.html_fmt import edge_grade, section_head

from mlbmodel.leans.decision_calibration import DecisionThresholds, DEFAULT_THRESHOLDS

e = html.escape

MKT_LABEL = {
    "moneyline": "Moneyline", "h2h": "Moneyline", "ml": "Moneyline",
    "total": "Total", "totals": "Total",
    "spread": "Run line", "spreads": "Run line", "run_line": "Run line", "runline": "Run line",
    "f5_ml": "F5 ML", "f5_total": "F5 Total", "f5_runline": "F5 Run line",
}

_VERDICT = {
    "STRONG":  (4, 2.0, "#2dd4bf", "rgba(45,212,191,.16)", "Sharp + model agree, price gives value"),
    "BET":     (3, 1.0, "#36d399", "rgba(54,211,153,.14)", "Sharp + model agree at a fair-or-better #"),
    "LEAN":    (2, 0.5, "#f5b14c", "rgba(245,177,76,.14)", "Right side, but the price is gone — wait for a number"),
    "SHARP":   (1, 0.5, "#9A6BFF", "rgba(154,107,255,.14)", "Sharp lean only — model/price hasn't confirmed"),
    "CONFLICT":(0, 0.0, "#f87171", "rgba(248,113,113,.14)", "Sharp and the model disagree — pass"),
}

_VERDICT_LABEL = {
    "STRONG": "STRONG BET", "BET": "BET", "LEAN": "LEAN",
    "SHARP": "SHARP-ONLY", "CONFLICT": "PASS",
}


def verdict_label(verdict: str) -> str:
    return _VERDICT_LABEL[verdict]


_VERDICT_CLASS = {
    "STRONG": "pos",
    "BET": "pos",
    "LEAN": "warnc",
    "SHARP": "mut",
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

    match = next(
        (
            row for row in (model_rows or [])
            if str(row.get("market") or "").lower() == mkt_type
            and _sel_match(row.get("side"), sel)
        ),
        None,
    )
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


def collect_market_plays(
    slate,
    sharp_by_pk,
    model_by_pk,
    thresholds: DecisionThresholds | None = None,
) -> list[dict]:
    pkmap = {g["pk"]: f'{g["away"]}@{g["home"]}' for g in slate if "pk" in g}
    plays = []
    for pk, sigs in sharp_by_pk.items():
        for sig in sigs:
            play = decide(sig, model_by_pk.get(pk), thresholds)
            play["pk"], play["game"] = pk, pkmap.get(pk, str(pk))
            plays.append(play)
    plays.sort(key=lambda row: -row["score"])
    return plays


def markets_html(
    slate,
    sharp_by_pk,
    model_by_pk=None,
    thresholds: DecisionThresholds | None = None,
) -> str:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    plays = collect_market_plays(slate, sharp_by_pk, model_by_pk or {}, thresholds)

    def _num(odds):
        return f"{odds:+d}" if isinstance(odds, int) else "—"

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
        else:
            bet = f'<b>{e(mkt)} {e(play["sel"])}</b><div class="mut meta-sub">no live #</div>'
        sharp = (
            f'<b class={edge_grade(play["div_pts"] / 100)}>+{play["div_pts"]:.1f}pt</b>'
            f'<div class="mut meta-sub">{play["sharp_p"]:.0f}% vs {play["soft_p"]:.0f}% pub</div>'
            + ('<span class="pill warnc hold-tag">STEAM</span>' if play["steam"] else "")
        )
        if play["medge"] is not None:
            ev_txt = f'{play["ev"] * 100:+.1f}% EV' if play["ev"] is not None else ""
            model = (
                f'<b class={edge_grade(play["medge"] / 100)}>{play["medge"]:+.1f}pt</b>'
                f'<div class="mut meta-sub">model {play["model_p"]:.0f}% · {ev_txt}</div>'
            )
        elif play["model_p"] is not None:
            model = f'<span class=mut>{play["model_p"]:.0f}% · no live #</span>'
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
        '<tr><td class=mut colspan=6>No sharp-vs-soft divergence on the current slate '
        '(needs the live game-odds feed). When sharp books price a side above the soft '
        'consensus, it surfaces here with the model\'s read.</td></tr>'
    )
    n_bet = sum(1 for play in plays if play["verdict"] in ("STRONG", "BET"))
    n_lean = sum(1 for play in plays if play["verdict"] == "LEAN")
    n_pass = sum(1 for play in plays if play["verdict"] == "CONFLICT")
    exposure = sum(play["stake"] for play in plays)
    top = plays[0] if plays else None
    top_txt = (
        f'{top["game"]} · {MKT_LABEL.get(top["mkt_type"], top["mkt_type"].title())} {top["sel"]}'
        if top else "—"
    )
    top_sub = f'{verdict_label(top["verdict"])} · {_VERDICT[top["verdict"]][4]}' if top else ""
    cal_note = (
        f'<div class=note>Decision thresholds: {e(thresholds.summary())}.</div>'
        if thresholds.calibrated else ""
    )
    return f"""<h2>Markets · Where to bet</h2>
 <div class="ctx verdict-hint">Every play is graded on <b>three independent reads</b>: sharp-book money
   (de-vigged vs the public), the <b>model's</b> own edge vs the live number, and the price itself.
   <span class=bet>BET</span> = sharp and model agree the side is underpriced;
   <span class=lean>LEAN</span> = right side, the number's gone;
   <span class=pass>PASS</span> = they disagree.</div>
 <div class=cards>
   <div class=card><div class=k>Top play</div><div class="v v-sm">{e(top_txt)}</div>
     <div class="mut mut-sm">{e(top_sub)}</div></div>
   <div class=card><div class=k>Confirmed bets</div><div class=v>{n_bet}</div></div>
   <div class=card><div class=k>Leans</div><div class=v>{n_lean}</div></div>
   <div class=card><div class=k>Suggested exposure</div><div class=v>{exposure:.1f}u</div>
     <div class="mut mut-sm">{n_pass} pass</div></div>
 </div>
 <div class=ca-board>{section_head("Decision board", icon="markets")}<div class=body>
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter game or bet…" data-filter-for="markets-table" aria-label="Filter markets"></div>
   <div class=table-scroll><table id=markets-table class=sortable><tr><th>Game</th><th>The bet</th>
   <th title="Sharp-book de-vig consensus minus the public consensus">Sharp lean</th>
   <th title="Model fair % minus the live price-implied %, plus EV at the number">Model edge</th>
   <th>Verdict</th><th>Stake</th></tr>{rows}</table></div>
   <div class=note>Bet only where the sharp lean and the model both clear the live price. Divergence
   = sharp − public (de-vigged); model edge = model% − price-implied%; EV is per unit at the posted number.
   Stakes are a conviction guide, not advice. Click a game to open its full matchup.</div>
 {cal_note}
 </div></div>"""
