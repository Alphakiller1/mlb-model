"""
mlbmodel.report.app — the unified MLB Model product shell.

ONE coherent application (not separate dashboards) with a 7-section information architecture:
Today · Matchups · Markets · Props · Portfolio · Results · Research. Workflow:
discover -> inspect -> evaluate -> compare -> decide -> track -> review. Each section follows the
page hierarchy: context -> conclusion -> price/opportunity -> evidence -> risks -> action ->
methodology. The user never sees which repo a number came from — it reads as one platform.

    python -m mlbmodel.report.app --game NYY@BOS --out app.html [--no-fetch]
"""
from __future__ import annotations

import argparse
import html
import math
import os

from mlbmodel.baseball.model import model_probabilities
from mlbmodel.baseball.repository import DataRepository
from mlbmodel.market.props import load_prop_board, market_report
from mlbmodel.market.quotes import load_board
from mlbmodel.market import prizepicks, underdog
from mlbmodel import settings
from mlbmodel.portfolio.risk import summarize_positions
from mlbmodel.props.model import build_pitcher_board
from mlbmodel.report import chase_theme
from mlbmodel.trends import build_slate_reports
from mlbmodel.report.matchup import (
    _CSS,
    _headshot,
    _logo,
    _promotion,
    build_report,
    report_body,
)
from mlbmodel.storage.supabase import SupabaseReader

e = html.escape


def _slate(repo):
    m = repo.slate()
    if m is None or "Away" not in m.columns:
        return [], None
    anchors = repo.anchors()
    sd = str(m.iloc[0].get("Slate_Date", "")) if len(m) else ""
    out = []
    for _, row in m.iterrows():
        a, h = str(row["Away"]).upper().strip(), str(row["Home"]).upper().strip()
        rec = {"away": a, "home": h, "time": str(row.get("Time", "") or "")}
        try:
            gd = repo.load_game(a, h)
            pr = model_probabilities(gd, anchors)
            rec.update({"ph": pr.p_home_win, "total": pr.exp_total, "margin": pr.exp_margin,
                        "asp": gd.away_sp, "hsp": gd.home_sp,
                        "ak": gd.away_k, "hk": gd.home_k,
                        "afip": gd.away_fip, "hfip": gd.home_fip,
                        "ahr9": gd.away_hr9, "hhr9": gd.home_hr9,
                        "lean": h if pr.exp_margin > 0 else a, "pk": gd.game_pk})
        except Exception:
            rec["err"] = True
        out.append(rec)
    return out, sd


# ── sections (each = context -> conclusion -> evidence; honest empty states) ──
def _today(slate, sd, sharp_by_pk, sync=None):
    rows = ""
    for g in slate:
        if g.get("err"):
            rows += f'<tr><td>{e(g["away"])}@{e(g["home"])}</td><td colspan=6 class=mut>no model inputs</td></tr>'
            continue
        sc = len(sharp_by_pk.get(g["pk"], []))
        game = f'{g["away"]}@{g["home"]}'
        rows += (f'<tr><td><button class=gamepick onclick="openGame(\'{game}\')">'
                 f'<span class=gcell>{_logo(g["away"],"tlogo sm")}<b>{e(g["away"])}</b>'
                 f'<span class=mut>@</span>{_logo(g["home"],"tlogo sm")}<b>{e(g["home"])}</b></span></button></td>'
                 f'<td class=mut>{e(g["time"])}</td>'
                 f'<td>{g["ph"]*100:.0f}% {e(g["home"])}</td>'
                 f'<td>{g["total"]:.1f}</td><td>{g["margin"]:+.1f}</td>'
                 f'<td class=side>{e(g["lean"])}</td>'
                 f'<td>{("<span class=pill warnc>"+str(sc)+" sharp</span>") if sc else "<span class=mut>—</span>"}</td></tr>')
    ok = [g for g in slate if not g.get("err")]
    n = len(ok)
    nsharp = len(sharp_by_pk)
    sync = sync or {}
    sync_label = "Exact" if sync.get("status") == "exact" else (
        "Live fallback" if sync.get("status") == "fallback" else "Untracked"
    )
    # biggest model leans (proxy for active opportunities until per-game odds load)
    leans = sorted(ok, key=lambda g: -abs(g.get("margin", 0)))[:6]
    lrows = "".join(
        f'<tr><td><button class=gamepick onclick="openGame(\'{g["away"]}@{g["home"]}\')"><b>{e(g["lean"])}</b> <span class=mut>{e(g["away"])}@{e(g["home"])}</span></button></td>'
        f'<td>{abs(g["margin"]):.1f} R</td><td>{max(g["ph"],1-g["ph"])*100:.0f}%</td>'
        f'<td>{g["total"]:.1f}</td></tr>' for g in leans)
    return f"""<h2>Today</h2>
 <div class=ctx>Open a matchup for model, market, risk, and freshness details.</div>
 <div class=cards>
   <div class=card><div class=k>Games</div><div class=v>{n}</div></div>
   <div class=card><div class=k>Slate</div><div class=v style="font-size:16px">{e(sd or "—")}</div></div>
   <div class=card><div class=k>With sharp signal</div><div class=v>{nsharp}</div></div>
   <div class=card><div class=k>MLBMA sync</div><div class=v style="font-size:16px">{e(sync_label)}</div></div>
 </div>
 <div class=cols>
   <div class=sec><h2>Slate</h2><div class=body>
     <div class=table-scroll><table><tr><th>Game</th><th>Time</th><th>Win%(H)</th><th>Proj tot</th><th>Margin</th><th>Lean</th><th>Sharp</th></tr>{rows or '<tr><td class=mut colspan=7>No slate loaded.</td></tr>'}</table></div></div></div>
   <div class=sec><h2>Biggest model leans</h2><div class=body>
     <div class=table-scroll><table><tr><th>Lean</th><th>Margin</th><th>Win%</th><th>Tot</th></tr>{lrows or '<tr><td class=mut colspan=4>—</td></tr>'}</table></div>
     <div class=note>Ranked by projected run margin. Open in <b>Matchups</b> for fair vs market edge.</div></div></div>
 </div>"""


_MKT_LABEL = {
    "moneyline": "Moneyline", "h2h": "Moneyline", "ml": "Moneyline",
    "total": "Total", "totals": "Total",
    "spread": "Run line", "spreads": "Run line", "run_line": "Run line", "runline": "Run line",
    "f5_ml": "F5 ML", "f5_total": "F5 Total", "f5_runline": "F5 Run line",
}


# Verdict tiers, ranked best→worst. Each maps to a tinted badge + a suggested stake (units).
_VERDICT = {
    "STRONG":  (4, 2.0, "#2dd4bf", "rgba(45,212,191,.16)", "Sharp + model agree, price gives value"),
    "BET":     (3, 1.0, "#36d399", "rgba(54,211,153,.14)", "Sharp + model agree at a fair-or-better #"),
    "LEAN":    (2, 0.5, "#f5b14c", "rgba(245,177,76,.14)", "Right side, but the price is gone — wait for a number"),
    "SHARP":   (1, 0.5, "#9A6BFF", "rgba(154,107,255,.14)", "Sharp lean only — model/price hasn't confirmed"),
    "CONFLICT":(0, 0.0, "#f87171", "rgba(248,113,113,.14)", "Sharp and the model disagree — pass"),
}


_VERDICT_LABEL = {"STRONG": "STRONG BET", "BET": "BET", "LEAN": "LEAN",
                  "SHARP": "SHARP-ONLY", "CONFLICT": "PASS"}


def _verdict_label(v):
    return _VERDICT_LABEL[v]


def _verdict_badge(v):
    _, _, fg, bg, _why = _VERDICT[v]
    return (f'<span class="pill" style="background:{bg};color:{fg};'
            f'border:1px solid {fg}55;font-weight:800">{_VERDICT_LABEL[v]}</span>')


def _sel_match(model_side, sharp_sel):
    return str(model_side or "").strip().lower() == str(sharp_sel or "").strip().lower()


def _decide(s, model_rows):
    """Fuse one sharp signal with the model's read on the same bet → an actionable call.

    Three independent reads: sharp-vs-public divergence, model%-vs-price edge, and the live
    number itself. We bet only where sharp AND model agree the side is underpriced.
    """
    div = float(s.get("divergence") or 0)            # sharp − public (fraction)
    div_pts = div * 100
    sharp_p = float(s.get("sharp_novig_prob") or 0) * 100
    soft_p = float(s.get("soft_novig_prob") or 0) * 100
    mkt_type = str(s.get("market_type") or "").lower()
    sel = str(s.get("selection") or "")

    m = next((r for r in (model_rows or [])
              if str(r.get("market") or "").lower() == mkt_type and _sel_match(r.get("side"), sel)),
             None)
    model_p = m.get("model") if m else None          # model fair % for this side
    medge = m.get("edge") if m else None             # model% − price-implied% (pts)
    ev = m.get("ev") if m else None                  # EV per unit at the executable price
    price = m.get("mkt") if m else None              # the number you'd actually bet
    fair = m.get("fair") if m else None
    book = m.get("book") if m else None

    # Verdict. Directional agreement = model's fair prob for the side ≥ the public's (soft).
    model_supports = model_p is not None and model_p >= soft_p
    has_price = price is not None and medge is not None
    if not m:
        verdict = "SHARP"
    elif has_price and medge >= 2.0 and div_pts >= 1.5 and (ev or 0) > 0:
        verdict = "STRONG"
    elif has_price and medge > 0 and (ev or 0) > 0:
        verdict = "BET"
    elif model_supports:
        verdict = "LEAN"
    else:
        verdict = "CONFLICT"

    rank, stake, _fg, _bg, _why = _VERDICT[verdict]
    # Conviction score for ranking: tier first, then combined edge strength.
    score = rank * 1000 + div_pts + max(0.0, medge or 0)
    return {
        "verdict": verdict, "stake": stake, "score": score,
        "mkt_type": mkt_type, "sel": sel, "div_pts": div_pts,
        "sharp_p": sharp_p, "soft_p": soft_p,
        "model_p": model_p, "medge": medge, "ev": ev,
        "price": price, "fair": fair, "book": book,
        "n_sharp": s.get("n_sharp_books"), "n_soft": s.get("n_soft_books"),
        "steam": bool(s.get("steam_flag")),
    }


def _markets(slate, sharp_by_pk, model_by_pk=None):
    model_by_pk = model_by_pk or {}
    pkmap = {g["pk"]: f'{g["away"]}@{g["home"]}' for g in slate}
    plays = []
    for pk, sigs in sharp_by_pk.items():
        for s in sigs:
            d = _decide(s, model_by_pk.get(pk))
            d["pk"], d["game"] = pk, pkmap.get(pk, str(pk))
            plays.append(d)
    plays.sort(key=lambda d: -d["score"])

    def _num(odds):
        return f"{odds:+d}" if isinstance(odds, int) else "—"

    def row(d):
        mkt = _MKT_LABEL.get(d["mkt_type"], d["mkt_type"].title())
        # The bet: side + the live number you'd take (or a flag that there's no posted price).
        if isinstance(d["price"], int):
            bet = (f'<b>{e(mkt)} {e(d["sel"])}</b> <span class="pill side">{_num(d["price"])}</span>'
                   + (f' <span class=mut>{e(str(d["book"]))}</span>' if d["book"] else "")
                   + (f'<div class=mut style="font-size:11px">fair {_num(d["fair"])}</div>'
                      if isinstance(d["fair"], int) else ""))
        else:
            bet = f'<b>{e(mkt)} {e(d["sel"])}</b><div class=mut style="font-size:11px">no live #</div>'
        # Sharp lean: divergence chip + the sharp→public split that produced it.
        sharp = (f'<b class={_edge_grade(d["div_pts"] / 100)}>+{d["div_pts"]:.1f}pt</b>'
                 f'<div class=mut style="font-size:11px">{d["sharp_p"]:.0f}% vs {d["soft_p"]:.0f}% pub</div>'
                 + ('<span class="pill warnc" style="font-size:10px">STEAM</span>' if d["steam"] else ""))
        # Model: its edge vs the price + EV — does the model confirm the sharp side?
        if d["medge"] is not None:
            ev_txt = f'{d["ev"] * 100:+.1f}% EV' if d["ev"] is not None else ""
            model = (f'<b class={_edge_grade(d["medge"] / 100)}>{d["medge"]:+.1f}pt</b>'
                     f'<div class=mut style="font-size:11px">model {d["model_p"]:.0f}% · {ev_txt}</div>')
        elif d["model_p"] is not None:
            model = f'<span class=mut>{d["model_p"]:.0f}% · no live #</span>'
        else:
            model = '<span class=mut>—</span>'
        stake = (f'<b style="color:{_VERDICT[d["verdict"]][2]}">{d["stake"]:.1f}u</b>'
                 if d["stake"] else '<span class=mut>—</span>')
        return (
            f'<tr><td><button class=gamepick onclick="openGame(\'{e(d["game"])}\')">{e(d["game"])}</button></td>'
            f'<td>{bet}</td><td>{sharp}</td><td>{model}</td>'
            f'<td title="{e(_VERDICT[d["verdict"]][4])}">{_verdict_badge(d["verdict"])}</td>'
            f'<td class=num>{stake}</td></tr>'
        )

    rows = "".join(row(d) for d in plays) or (
        '<tr><td class=mut colspan=6>No sharp-vs-soft divergence on the current slate '
        '(needs the live game-odds feed). When sharp books price a side above the soft '
        'consensus, it surfaces here with the model\'s read.</td></tr>'
    )
    n_bet = sum(1 for d in plays if d["verdict"] in ("STRONG", "BET"))
    n_lean = sum(1 for d in plays if d["verdict"] == "LEAN")
    n_pass = sum(1 for d in plays if d["verdict"] == "CONFLICT")
    exposure = sum(d["stake"] for d in plays)
    top = plays[0] if plays else None
    top_txt = (f'{top["game"]} · {_MKT_LABEL.get(top["mkt_type"], top["mkt_type"].title())} {top["sel"]}'
               if top else "—")
    top_sub = (f'{_verdict_label(top["verdict"])} · {_VERDICT[top["verdict"]][4]}' if top else "")
    return f"""<h2>Markets · Where to bet</h2>
 <div class=ctx>Every play is graded on <b>three independent reads</b>: sharp-book money
   (de-vigged vs the public), the <b>model's</b> own edge vs the live number, and the price itself.
   <b style="color:#2dd4bf">BET</b> = sharp and model agree the side is underpriced;
   <b style="color:#f5b14c">LEAN</b> = right side, the number's gone;
   <b style="color:#f87171">PASS</b> = they disagree.</div>
 <div class=cards>
   <div class=card><div class=k>Top play</div><div class=v style="font-size:17px">{e(top_txt)}</div>
     <div class=mut style="font-size:11px">{e(top_sub)}</div></div>
   <div class=card><div class=k>Confirmed bets</div><div class=v>{n_bet}</div></div>
   <div class=card><div class=k>Leans</div><div class=v>{n_lean}</div></div>
   <div class=card><div class=k>Suggested exposure</div><div class=v>{exposure:.1f}u</div>
     <div class=mut style="font-size:11px">{n_pass} pass</div></div>
 </div>
 <div class=sec><h2>Decision board</h2><div class=body>
   <div class=table-scroll><table><tr><th>Game</th><th>The bet</th>
   <th title="Sharp-book de-vig consensus minus the public consensus">Sharp lean</th>
   <th title="Model fair % minus the live price-implied %, plus EV at the number">Model edge</th>
   <th>Verdict</th><th>Stake</th></tr>{rows}</table></div>
   <div class=note>Bet only where the sharp lean and the model both clear the live price. Divergence
   = sharp − public (de-vigged); model edge = model% − price-implied%; EV is per unit at the posted number.
   Stakes are a conviction guide, not advice. Click a game to open its full matchup.</div>
 </div></div>"""


def _display(value, suffix="", digits=1):
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _edge_grade(edge_fraction):
    """chase-style 5-tier color for a prop value edge (stored as a fraction; *100 = pts)."""
    if edge_fraction is None:
        return "c-na"
    pts = edge_fraction * 100
    if pts >= 6:
        return "c-elite"
    if pts >= 3:
        return "c-good"
    if pts >= 1:
        return "c-mid"
    if pts >= 0:
        return "c-weak"
    return "c-poor"


def _p_over(line, mean, sd):
    """P(stat > line) via a normal approximation of the simulated distribution.

    PrizePicks lines sit on the half-point so there is no push; the sim's own sd captures the
    right spread (fantasy score is a sum → near-normal; counts are close enough for a lean).
    """
    if sd is None or sd <= 0:
        return 1.0 if mean > line else (0.0 if mean < line else 0.5)
    return 1.0 - 0.5 * (1.0 + math.erf((line - mean) / (sd * math.sqrt(2))))


# Order the pick'em board surfaces PrizePicks pitcher markets (fantasy first, then the rest).
_PICKEM_ORDER = ["PP_Fantasy", "K", "Outs", "ER", "H", "BB"]


def _pickem_rows(pitchers, sources):
    """Grade each pitcher's model projection against pick'em lines from one or more books.

    ``sources`` is a list of (book_label, board) where board maps normalized-name -> proj_key ->
    line. Rows are grouped by pitcher, then book, with a Book column so the same market can be
    compared across books.
    """
    rows = ""
    count = 0
    for row in pitchers:
        name_key = prizepicks.normalize_name(row.get("pitcher"))
        projections = row.get("projections") or {}
        pitcher_cell = (
            f'<td><div class=pitcher-cell>{_headshot(row.get("pitcher_id"))}'
            f'<div><b>{e(str(row.get("pitcher") or "TBD"))}</b>'
            f'<span>{_logo(row.get("team"), "tlogo sm")}{e(str(row.get("team") or ""))}</span>'
            f'</div></div></td>'
        )
        for label, board in sources:
            lines = board.get(name_key, {})
            if not lines:
                continue
            for key in _PICKEM_ORDER:
                line, proj = lines.get(key), projections.get(key)
                if not line or not proj:
                    continue
                mean, sd = proj.get("mean"), proj.get("sd")
                p_over = _p_over(line["line"], mean, sd or 0)
                lean = "OVER" if p_over >= 0.5 else "UNDER"
                tone = "pos" if abs(p_over - 0.5) >= 0.08 else "mut"
                variant = (
                    "" if line.get("odds_type") == "standard"
                    else f' <span class="mut" style="font-size:9px">{e(str(line.get("odds_type")))}</span>'
                )
                count += 1
                rows += (
                    f'<tr>{pitcher_cell}'
                    f'<td><span class="pill mut">{e(label)}</span></td>'
                    f'<td>{prizepicks.STAT_LABEL.get(key, key)}{variant}</td>'
                    f'<td><b>{line["line"]:g}</b></td>'
                    f'<td>{mean:.1f}</td>'
                    f'<td>{p_over * 100:.0f}%</td>'
                    f'<td><span class="pill {tone}">{lean}</span></td></tr>'
                )
    return rows, count


def _props(pitchers, prop_board, pp_board=None, ud_board=None):
    pp_board = pp_board or {}
    ud_board = ud_board or {}

    def projection_cell(row, prop, model_only=False):
        value = (row.get("projections") or {}).get(prop) or {}
        if not value:
            return '<td class=mut>—</td>'
        report = next(
            (item for item in row.get("market_report", []) if item["prop"] == prop),
            None,
        )
        # Untrusted (thin-data) projections still show the line, but the edge is greyed —
        # the model's edge there is not reliable enough to act on.
        trusted = row.get("projection_trust") == "trusted"
        edge_cls = _edge_grade(report.get("edge")) if (trusted and report) else "mut"
        if model_only:
            # Hits allowed and fantasy points are model projections (no book line surfaced here).
            market = '<span class="prop-mkt mut">model proj</span>'
        else:
            market = (
                f'<span class="prop-mkt">{report["side"][0].upper()} {report["line"]:g} '
                f'{report["best_odds"]:+d} · '
                f'<b class="{edge_cls}">'
                f'{(report.get("edge") or 0) * 100:+.1f}pt</b></span>'
                if report else '<span class="prop-mkt mut">no line</span>'
            )
        return (
            f'<td class=prop-cell><b>{value["mean"]:.1f}</b>'
            f'<span class=prop-range>range {value["p10"]:.0f}–{value["p90"]:.0f}</span>'
            f'{market}</td>'
        )

    rows = ""
    all_markets = []
    for index, row in enumerate(pitchers):
        reports = row.get("market_report") or []
        trusted = row.get("projection_trust") == "trusted"
        # Only trusted projections feed the ranked edge board; thin-data pitchers would
        # otherwise dominate it with phantom edges.
        if trusted:
            all_markets.extend(
                [{"pitcher": row.get("pitcher"), **report} for report in reports]
            )
        state = row.get("state", "DATA GAP")
        state_tone = "neg" if state == "REGRESSION" else (
            "pos" if state == "PROGRESSION" else "side" if state == "STABLE" else "warnc"
        )
        best = reports[0] if reports else None
        market_state = best.get("state") if best else row.get("market_state", "NO MARKET")
        market_tone = "pos" if market_state in {"BET", "MONITOR"} else "mut"
        if not trusted:
            market_state = "THIN DATA"
            market_tone = "warnc"
        rows += (
            f'<tr class=prop-main onclick="togglePitcher({index})">'
            f'<td><div class=pitcher-cell>{_headshot(row.get("pitcher_id"))}'
            f'<div><b>{e(str(row.get("pitcher") or "TBD"))}</b>'
            f'<span>{_logo(row.get("team"), "tlogo sm")}{e(str(row.get("team") or ""))}</span>'
            f'</div></div></td>'
            f'<td><span class=gcell>{_logo(row.get("opponent"), "tlogo sm")}'
            f'{e(str(row.get("opponent") or ""))}</span></td>'
            f'<td><span class="pill {state_tone}" title="Performance state from results versus underlying pitching skill">{e(state)}</span>'
            f'<span class=prop-sub>{float(row.get("luck_runs") or 0):+.2f} runs</span></td>'
            f'<td class=starter-base><b>{_display(row.get("expected_ip"), digits=1)} IP</b>'
            f'<span>{_display(row.get("skill_era"), digits=2)} runs/9</span></td>'
            f'{projection_cell(row, "K")}{projection_cell(row, "BB")}'
            f'{projection_cell(row, "ER")}{projection_cell(row, "Outs")}'
            f'{projection_cell(row, "H", model_only=True)}'
            f'{projection_cell(row, "Fantasy", model_only=True)}'
            f'<td><span class="pill {market_tone}">{e(str(market_state))}</span>'
            f'<span class=prop-sub>{e(str(row.get("confidence") or "low"))} confidence</span></td></tr>'
        )
        pitch_rows = "".join(
            f'<tr><td>{e(str(pitch.get("pitch") or ""))}</td>'
            f'<td>{_display(pitch.get("usage_pct"), "%")}</td>'
            f'<td>{_display(pitch.get("pitcher_whiff_pct"), "%")}</td>'
            f'<td>{_display(pitch.get("lineup_whiff_pct"), "%")}</td>'
            f'<td>{_display(pitch.get("pitcher_xwoba"), digits=3)}</td>'
            f'<td>{_display(pitch.get("lineup_xwoba"), digits=3)}</td>'
            f'<td class={"pos" if (pitch.get("k_delta") or 0) > 0 else "neg"}>'
            f'{float(pitch.get("k_delta") or 0):+.2f} K%</td>'
            f'<td class={"pos" if (pitch.get("er_factor_delta") or 0) < 0 else "neg"}>'
            f'{float(pitch.get("er_factor_delta") or 0) * 100:+.1f}% runs</td>'
            f'<td>{e(str(pitch.get("edge") or "neutral"))}</td></tr>'
            for pitch in (row.get("pitch_matchup") or {}).get("pitches", [])[:6]
        ) or '<tr><td class=mut colspan=9>No reliable pitch-overlap sample.</td></tr>'
        market_rows = "".join(
            f'<tr><td>{e(report["prop"])}</td><td>{e(report["side"].title())} {report["line"]:g}</td>'
            f'<td>{report["best_odds"]:+d} · {e(report["best_book"])}</td>'
            f'<td>{report["model_probability"] * 100:.1f}%</td>'
            f'<td>{report["market_probability"] * 100:.1f}%</td>'
            f'<td><b class={_edge_grade(report.get("edge"))}>'
            f'{(report.get("edge") or 0) * 100:+.1f}pt</b></td>'
            f'<td class={"pos" if (report.get("ev") or 0) > 0 else "neg"}>'
            f'{(report.get("ev") or 0) * 100:+.1f}%</td>'
            f'<td><span class="pill {"pos" if report["state"] == "MONITOR" else "mut"}">{e(report["state"])}</span></td></tr>'
            for report in reports
        ) or '<tr><td class=mut colspan=8>No paired prop price for this pitcher.</td></tr>'
        pitch_matchup = row.get("pitch_matchup") or {}
        lineup = row.get("lineup") or {}
        rows += f"""<tr class=prop-detail id=prop-detail-{index}><td colspan=9>
          <div class=prop-detail-grid>
            <div class=sec><h2>Arsenal vs opponent production</h2><div class=body>
              <div class=detail-strip>
                <span><b>{e(str(row.get("lineup_status") or "unavailable"))}</b> lineup</span>
                <span>{e(str(pitch_matchup.get("response_source") or "no response source"))}</span>
                <span>{pitch_matchup.get("coverage_pct", 0)}% arsenal covered</span>
                <span>{pitch_matchup.get("lineup_batters_matched", 0)}/9 batters matched</span>
              </div>
              <div class=table-scroll><table><tr><th>Pitch</th><th>Usage</th>
                <th>Pitcher whiff</th><th>Opponent whiff</th>
                <th title="Pitcher's expected weighted on-base average allowed">Pitcher contact</th>
                <th title="Opponent expected weighted on-base average against this pitch">Opponent contact</th>
                <th>K effect</th><th>Run effect</th><th>Who benefits</th></tr>{pitch_rows}</table></div>
              <div class=note>Opponent values switch from team results to batting-order-weighted player results when at least six posted hitters match.</div>
            </div></div>
            <div class=sec><h2>Market report</h2><div class=body>
              <div class=table-scroll><table><tr><th>Prop</th><th>Bet</th><th>Best price</th>
                <th>Model</th><th>Market</th><th>Edge</th><th>EV</th><th>State</th></tr>{market_rows}</table></div>
              <div class=detail-strip>
                <span>Projected innings <b>{_display(row.get("expected_ip"), digits=1)}</b></span>
                <span>Lineup score <b>{_display(lineup.get("score"), digits=1)}</b></span>
                <span>Coverage <b>{row.get("data_coverage_pct", 0)}%</b></span>
              </div>
            </div></div>
          </div>
        </td></tr>"""

    all_markets.sort(key=lambda row: -(row.get("edge") or -1))
    report_rows = "".join(
        f'<tr><td>{e(str(item["pitcher"]))}</td><td>{e(item["prop"])}</td>'
        f'<td>{e(item["side"].title())} {item["line"]:g}</td>'
        f'<td>{item["best_odds"]:+d} · {e(item["best_book"])}</td>'
        f'<td>{item["model_probability"] * 100:.1f}%</td>'
        f'<td>{item["market_probability"] * 100:.1f}%</td>'
        f'<td><b class={_edge_grade(item.get("edge"))}>'
        f'{(item.get("edge") or 0) * 100:+.1f}pt</b></td>'
        f'<td><span class="pill {"pos" if item["state"] == "MONITOR" else "mut"}">{e(item["state"])}</span></td></tr>'
        for item in all_markets[:12]
    ) or (
        '<tr><td class=mut colspan=8>No paired pitcher-prop snapshot is loaded. '
        'Projections remain visible; price decisions remain NO MARKET.</td></tr>'
    )
    pickem_rows, pickem_count = _pickem_rows(
        pitchers, [("PrizePicks", pp_board), ("Underdog", ud_board)]
    )
    pickem_rows = pickem_rows or (
        '<tr><td class=mut colspan=7>No PrizePicks or Underdog pitcher lines loaded '
        '(off-hours or feed unavailable).</td></tr>'
    )
    confirmed = sum(1 for row in pitchers if row.get("lineup_status") == "confirmed")
    return f"""<h2>Pitcher Props</h2>
 <div class=ctx>Projection distributions, opponent pitch response, and executable price comparison.</div>
 <div class=cards>
   <div class=card><div class=k>Probable starters</div><div class=v>{len(pitchers)}</div></div>
   <div class=card><div class=k>Confirmed lineups</div><div class=v>{confirmed}/30</div></div>
   <div class=card><div class=k>Priced prop sides</div><div class=v>{len(all_markets)}</div></div>
   <div class=card><div class=k>Price feed</div><div class=v style="font-size:16px">{"LIVE" if all_markets else "NO SNAPSHOT"}</div></div>
 </div>
 <div class=sec><h2>Prop market report</h2><div class=body>
   <div class=table-scroll><table><tr><th>Pitcher</th><th>Prop</th><th>Bet</th>
   <th>Best price</th><th>Model</th><th>Market</th><th>Edge</th><th>State</th></tr>
   {report_rows}</table></div></div></div>
 <div class=sec><h2>Pick&apos;em boards <span class="mut" style="font-weight:600;font-size:11px">PrizePicks + Underdog · model vs line · {pickem_count} lines</span></h2><div class=body>
   <div class=table-scroll><table><tr><th>Pitcher</th><th>Book</th><th>Market</th><th>Line</th><th>Model</th><th>P(over)</th><th>Lean</th></tr>{pickem_rows}</table></div>
   <div class=note>Fantasy score uses each book&apos;s pitcher formula (Out +1, K +3, ER −3, quality start +4, win +6 — win modeled; PrizePicks and Underdog scoring match). Hits / strikeouts / earned runs / outs / walks grade directly against the projection. P(over) is a normal approximation of the simulated distribution; leans ≥58% are highlighted. Not betting advice.</div>
 </div></div>
 <div class=sec><h2>Pitcher board</h2><div class=body>
   <div class=table-scroll><table class=prop-table><tr><th>Starter</th><th>vs</th>
   <th>Performance</th><th title="Projected innings and expected runs allowed per nine">Starter baseline</th><th>K</th><th>BB</th>
   <th>ER</th><th>Outs</th><th title="Projected hits allowed">Hits</th><th title="DraftKings pitcher fantasy points: IP*2.25 + K*2 - ER*2 - H*0.6 - BB*0.6">DK Pts</th><th>Market</th></tr>{rows or '<tr><td class=mut colspan=11>No pitcher inputs loaded.</td></tr>'}</table></div>
 </div></div>"""


def _portfolio(reader, gate, slate):
    result = reader.get(
        "paper_positions?status=eq.open&select=game_pk,market_type,selection,line,"
        "entry_odds,model_probability,market_probability,stake_units,entry_time,"
        "strategy_version&order=entry_time.desc&limit=200"
    )
    promoted = gate.get("verdict") == "PROMOTE"
    sizing_state = "Enabled" if promoted else "Disabled"
    if result.error:
        return f"""<h2>Portfolio</h2>
 <div class=ctx>Paper positions, bankroll exposure, and correlated risk.</div>
 <div class=cards>
   <div class=card><div class=k>Open positions</div><div class=v>—</div></div>
   <div class=card><div class=k>Units at risk</div><div class=v>—</div></div>
   <div class=card><div class=k>Games exposed</div><div class=v>—</div></div>
   <div class=card><div class=k>Auto sizing</div><div class=v style="font-size:16px">{sizing_state}</div></div>
 </div>
 <div class=empty>Portfolio store unavailable: {e(result.error)}. Apply the paper-portfolio migration and configure warehouse read access to enable this view.</div>"""

    positions = result.rows
    summary = summarize_positions(positions)
    pkmap = {
        int(game["pk"]): f'{game["away"]}@{game["home"]}'
        for game in slate if "pk" in game
    }
    rows = ""
    for position in positions:
        game_pk = int(position["game_pk"])
        line = position.get("line")
        selection = e(str(position.get("selection") or "—"))
        if line is not None:
            selection += f' <span class=mut>{float(line):+g}</span>'
        entry_odds = int(position["entry_odds"])
        model_p = _display(float(position["model_probability"]) * 100, "%")
        market_raw = position.get("market_probability")
        market_p = (
            _display(float(market_raw) * 100, "%") if market_raw is not None else "—"
        )
        rows += (
            f'<tr><td>{e(pkmap.get(game_pk, str(game_pk)))}</td>'
            f'<td>{e(str(position.get("market_type") or "—"))}</td>'
            f'<td>{selection}</td><td>{entry_odds:+d}</td>'
            f'<td>{model_p}</td><td>{market_p}</td>'
            f'<td>{_display(position.get("stake_units"), "u", digits=2)}</td>'
            f'<td class=mut>{e(str(position.get("entry_time") or "—")[:16])}</td></tr>'
        )
    concentration = ""
    if summary.concentrated_games:
        labels = ", ".join(
            e(pkmap.get(game_pk, str(game_pk)))
            for game_pk in summary.concentrated_games
        )
        concentration = (
            f'<div class="vbar neg"><b>Concentration warning</b>'
            f'<span>More than 2.0u exposed on {labels}.</span></div>'
        )
    gate_note = (
        "Fractional-Kelly paper sizing is enabled by the promotion gate."
        if promoted else
        "Sizing is disabled until an executable strategy passes the promotion gate."
    )
    return f"""<h2>Portfolio</h2>
 <div class=ctx>Paper positions, bankroll exposure, and correlated risk.</div>
 <div class=cards>
   <div class=card><div class=k>Open positions</div><div class=v>{summary.open_positions}</div></div>
   <div class=card><div class=k>Units at risk</div><div class=v>{summary.total_units_at_risk:.2f}u</div></div>
   <div class=card><div class=k>Games exposed</div><div class=v>{summary.games_exposed}</div></div>
   <div class=card><div class=k>Largest game</div><div class=v>{summary.largest_game_exposure:.2f}u</div></div>
 </div>
 {concentration}
 <div class=sec><h2>Open paper positions</h2><div class=body>
   <div class=table-scroll><table><tr><th>Game</th><th>Market</th><th>Selection</th>
   <th>Entry</th><th>Model</th><th>Market</th><th>Risk</th><th>Entered</th></tr>
   {rows or '<tr><td class=mut colspan=8>No open paper positions.</td></tr>'}</table></div>
   <div class=note>{e(gate_note)} Live-money execution is outside this model.</div>
 </div></div>"""


def _results(reader):
    mp = reader.get("model_predictions?select=verdict&limit=1000")
    go = reader.get("game_outcomes?select=game_pk&limit=2000")
    brier = reader.get("v_open_vs_close_brier?select=*")
    errors = [result.error for result in (mp, go, brier) if result.error]
    if errors:
        return f"""<h2>Results</h2><div class=ctx>Settled performance and calibration.</div>
 <div class=empty>Warehouse unavailable: {e("; ".join(errors))}</div>"""
    mp_rows, go_rows, brier_rows = mp.rows, go.rows, brier.rows
    b = brier_rows[0] if brier_rows else {}
    return f"""<h2>Results</h2>
 <div class=ctx>Settled performance, CLV and calibration. Builds as the daily settle loop runs.</div>
 <div class=cards>
	   <div class=card><div class=k>Predictions logged</div><div class=v>{len(mp_rows)}</div></div>
	   <div class=card><div class=k>Games settled</div><div class=v>{len(go_rows)}</div></div>
   <div class=card><div class=k>Open Brier</div><div class=v>{b.get('open_brier','—')}</div></div>
   <div class=card><div class=k>Close Brier</div><div class=v>{b.get('close_brier','—')}</div></div>
 </div>
 <div class=note>Open-versus-close calibration describes market learning. It does not, by itself, establish a profitable entry rule.</div>"""


_CAT_LABEL = {
    "bullpen_fatigue": "BULLPEN", "form_vs_hand": "FORM vs HAND",
    "starter_quality": "SP QUALITY", "park": "PARK",
}
_CAT_TONE = {
    "bullpen_fatigue": "warnc", "form_vs_hand": "side",
    "starter_quality": "pos", "park": "mut",
}


def _bet_tone(implication):
    """Color a bet by direction: OVER green, UNDER red, else neutral."""
    u = (implication or "").upper()
    if "OVER" in u:
        return "pos"
    if "UNDER" in u:
        return "neg"
    return "mut"


def _mag_grade(effect_size):
    """chase 5-tier color for a trend's standardized magnitude (in SD)."""
    if effect_size is None:
        return "c-na"
    if effect_size >= 1.5:
        return "c-elite"
    if effect_size >= 0.9:
        return "c-good"
    if effect_size >= 0.6:
        return "c-mid"
    if effect_size >= 0.3:
        return "c-weak"
    return "c-poor"


def _edge_bar(score):
    """A 0–100 situational-edge meter, graded by distance from neutral (50)."""
    cls = _mag_grade(abs(score - 50) / 12.0)
    return (
        f'<div class=edgebar><i style="width:{max(2, min(100, score)):.0f}%"></i>'
        f'<b class={cls}>{score:.0f}</b></div>'
    )


def _trends(reports):
    if not reports:
        return ("<h2>Situational Trends</h2><div class=ctx>No slate loaded.</div>"
                "<div class=empty>No games to analyze.</div>")
    # slate-wide dominant-trend board
    flat = []
    for r in reports:
        for t in r.trends:
            if t.category == "park":
                continue
            flat.append((r, t))
    flat.sort(key=lambda rt: rt[1].trend_score, reverse=True)
    board = "".join(
        f'<tr><td><button class=gamepick onclick="openGame(\'{e(r.game)}\')">'
        f'{e(r.game)}</button></td>'
        f'<td><span class=gcell>{_logo(t.team, "tlogo sm")}{e(t.team)}</span></td>'
        f'<td><span class="pill {_CAT_TONE.get(t.category, "mut")}">{_CAT_LABEL.get(t.category, t.category.upper())}</span></td>'
        f'<td class=trend-sig>{e(t.trend_description)}</td>'
        f'<td><b class={_mag_grade(t.effect_size)}>{t.effect_size:.1f}σ</b></td>'
        f'<td>{t.sample_size or "—"}</td>'
        f'<td class={_bet_tone(t.betting_implications[0] if t.betting_implications else "")}>'
        f'{e(t.betting_implications[0]) if t.betting_implications else "—"}</td></tr>'
        for r, t in flat[:14]
    ) or '<tr><td class=mut colspan=7>No dominant situational trends cleared the threshold today.</td></tr>'

    # per-game cards
    cards = ""
    for r in sorted(reports, key=lambda x: -abs(x.away_edge_score - x.home_edge_score)):
        lean_txt = (f'edge <b class=side>{e(r.edge_lean)}</b>' if r.edge_lean != "even"
                    else 'edge <b class=mut>even</b>')
        bullets = "".join(
            f'<li><span class="pill {_CAT_TONE.get(t.category, "mut")}">{_CAT_LABEL.get(t.category, t.category.upper())}</span> '
            f'{e(t.trend_description)} '
            f'<span class=mut>· {e(t.mechanistic_explanation)}</span> '
            f'<b class={_bet_tone(t.betting_implications[0] if t.betting_implications else "")}>'
            f'→ {e(t.betting_implications[0]) if t.betting_implications else ""}</b></li>'
            for t in r.trends[:5]
        ) or '<li class=mut>No dominant trends cleared the magnitude/sample threshold.</li>'
        cards += f"""<div class=sec><h2>{e(r.game)} · {lean_txt}</h2><div class=body>
          <div class=edge-row>
            <div class=edge-cell><span class=k>{e(r.away)}</span>{_edge_bar(r.away_edge_score)}</div>
            <div class=edge-cell><span class=k>{e(r.home)}</span>{_edge_bar(r.home_edge_score)}</div>
          </div>
          <ul class=trend-list>{bullets}</ul>
        </div></div>"""

    total = sum(len(r.trends) for r in reports)
    strongest = flat[0][1].effect_size if flat else 0.0
    return f"""<h2>Situational Trends</h2>
 <div class=ctx>Context-matched situational edges — bullpen fatigue, recent form vs the opposing
   hand, starter-quality interactions, and park. Standalone read; not folded into projections.</div>
 <div class=cards>
   <div class=card><div class=k>Games analyzed</div><div class=v>{len(reports)}</div></div>
   <div class=card><div class=k>Dominant trends</div><div class=v>{total}</div></div>
   <div class=card><div class=k>Strongest signal</div><div class=v>{strongest:.1f}σ</div></div>
   <div class=card><div class=k>Source</div><div class=v style="font-size:16px">MLBMA logs</div></div>
 </div>
 <div class=sec><h2>Dominant trend board</h2><div class=body>
   <div class=table-scroll><table><tr><th>Game</th><th>Team</th><th>Type</th><th>Signal</th>
   <th>Mag</th><th>n</th><th>Lean / bet</th></tr>{board}</table></div>
   <div class=note>Ranked by blended score (magnitude × sample × relevance). σ = SDs from the league baseline.</div></div></div>
 {cards}"""


def _research(reader, pv, f5_board=None):
    cal_result = reader.get(
        "v_pm_calibration?select=price_bucket,n,avg_price,actual_win_rate,gap"
        "&order=price_bucket&limit=12"
    )
    cal = cal_result.rows
    crows = "".join(
        f'<tr><td>{c["price_bucket"]}</td><td>{c["n"]}</td><td>{c["avg_price"]}</td>'
        f'<td>{c["actual_win_rate"]}</td><td class={"neg" if abs(c.get("gap") or 0)>0.1 else "mut"}>{c.get("gap")}</td></tr>'
        for c in cal) or '<tr><td class=mut colspan=5>No calibration sample.</td></tr>'
    tone = "pos" if pv["verdict"] == "PROMOTE" else "mut"

    # First-5 (F5) board — the same graded F5 rows surfaced across the model, ranked by edge.
    f5 = sorted(
        (item for item in (f5_board or []) if item[1].get("edge") is not None),
        key=lambda item: -(item[1].get("edge") or 0),
    )
    if f5:
        f5rows = "".join(
            f'<tr><td><button class=gamepick onclick="openGame(\'{e(g)}\')">{e(g)}</button></td>'
            f'<td><span class="pill side">{e(_MKT_LABEL.get(m["market"], m["market"]))}</span></td>'
            f'<td><b>{e(str(m.get("side")))}</b></td><td class=num>{m.get("model"):.0f}%</td>'
            f'<td class=num>{(str(m["mkt"]) if isinstance(m.get("mkt"), int) and m["mkt"]>=0 else str(m.get("mkt"))) if m.get("mkt") is not None else "—"}</td>'
            f'<td><b class={_edge_grade((m.get("edge") or 0)/100)}>{m["edge"]:+.1f}pt</b></td>'
            f'<td><span class="pill {m.get("tone","mut")}">{e(str(m.get("state")))}</span></td></tr>'
            for g, m in f5)
        f5_note = "First-5 markets, de-vigged and graded against the model — priced when live F5 odds are in the feed."
    else:
        f5rows = '<tr><td class=mut colspan=7>No live F5 prices on the slate yet — F5 shows as model fair values in each matchup.</td></tr>'
        f5_note = "F5 prices appear here when the live F5 feed returns them."
    f5_panel = (f'<div class=sec><h2>First 5 (F5) edges</h2><div class=body>'
                f'<div class=table-scroll><table><tr><th>Game</th><th>Market</th><th>Side</th>'
                f'<th>Model%</th><th>Price</th><th>Edge</th><th>State</th></tr>{f5rows}</table></div>'
                f'<div class=note>{f5_note}</div></div></div>')

    return f"""<h2>Research</h2>
 <div class=ctx>Model + data health. Not part of the betting workflow — promotion is gated here.</div>
 <div class=sec><h2>Promotion gate</h2><div class=body>
   <div class="vbar {tone}"><b>{pv['verdict']}</b><span>{e('; '.join(pv.get('reasons', [])))}</span></div>
	   <div class=note>Promotion also requires an executable signal timestamp and entry price. Open-to-close hindsight cannot qualify.</div></div></div>
 {f5_panel}
 <div class=sec><h2>Kalshi price calibration</h2><div class=body>
   <div class=table-scroll><table><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div></div></div>"""


# All 8 sections are always reachable -- each has an honest empty/unavailable state instead
# of being hidden, so the nav itself never implies a section doesn't exist yet.
_NAV = [("today", "Today"), ("matchups", "Matchups"), ("trends", "Trends"), ("markets", "Markets"),
        ("props", "Props"), ("portfolio", "Portfolio"), ("results", "Results"), ("research", "Research")]

_SHELL_CSS = """
body{padding:0;min-height:100vh}
#appshell{display:flex;min-height:calc(100vh - 68px)}
/* --- sidebar nav: glass rail with an accent-bar active state --- */
#nav{width:214px;flex:0 0 214px;background:linear-gradient(180deg,rgba(20,23,34,.94),rgba(8,11,19,.98));
border-right:1px solid var(--border);padding:20px 12px;position:sticky;top:68px;height:calc(100vh - 68px);overflow:auto;
backdrop-filter:blur(8px)}
#nav .brand{font-family:var(--display);font-weight:800;font-size:17px;letter-spacing:.01em;
background:linear-gradient(90deg,var(--teal),var(--v-light));
-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:2px}
#nav .tagline{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.14em;margin-bottom:18px}
.navb{position:relative;display:block;width:100%;text-align:left;background:none;border:1px solid transparent;border-radius:10px;
color:var(--muted);font:600 13.5px var(--sans);padding:11px 12px 11px 15px;margin:3px 0;cursor:pointer;min-height:44px;
transition:color .15s ease,background .15s ease}
.navb:hover{color:var(--ink);background:rgba(124,77,255,.09)}
.navb.on{color:var(--ink);background:linear-gradient(135deg,rgba(124,77,255,.22),rgba(45,212,191,.06));
border-color:var(--border-violet);box-shadow:0 6px 20px rgba(124,77,255,.14)}
.navb.on::before{content:"";position:absolute;left:0;top:9px;bottom:9px;width:3px;border-radius:0 3px 3px 0;
background:linear-gradient(180deg,var(--v-light),var(--teal))}
#main{max-width:1240px;margin:0 auto;padding:26px 28px 72px}
.view{display:none}.view.on{display:block;animation:viewin .28s ease both}
@keyframes viewin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){.view.on{animation:none}.card{transition:none}}
#main>.view>h2:first-child{font-family:var(--display);font-weight:800;font-size:30px;font-variation-settings:'wdth' 125;
letter-spacing:-.02em;margin:0 0 5px;line-height:1.05}
.ctx{color:var(--muted);font-size:13px;margin-bottom:18px}
.note{color:var(--muted);font-size:11.5px;margin-top:10px}
/* --- stat tiles: glass panel, gradient accent hairline, hover lift --- */
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin-bottom:16px}
.card{position:relative;background:var(--ca-panel-glass);border:1px solid var(--border-2);border-radius:14px;
padding:15px 16px 14px;overflow:hidden;box-shadow:var(--ca-card-shadow);
transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:var(--v-grad);opacity:.7}
.card:hover{transform:translateY(-2px);border-color:var(--ca-panel-border);
box-shadow:0 10px 34px rgba(0,0,0,.5),0 0 0 1px rgba(196,176,255,.12)}
.card .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em;font-weight:800}
.card .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:26px;font-variation-settings:'wdth' 120;
margin-top:4px;line-height:1.05;letter-spacing:-.01em}
.cols{display:grid;grid-template-columns:1.4fr 1fr;gap:14px;align-items:start}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.gcell{display:inline-flex;align-items:center;gap:5px}
.gamepick{border:0;background:none;color:inherit;font:inherit;padding:0;cursor:pointer;text-align:left}
.gamepick:hover b{color:var(--teal)}
.pagehead{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:16px}
.pagehead h2{font-family:var(--display);font-weight:800;font-size:30px;font-variation-settings:'wdth' 125;letter-spacing:-.02em;margin:0 0 5px;line-height:1.05}
.pagehead .ctx{margin:0}
.pagehead select{min-width:180px;background:var(--card);color:var(--ink);border:1px solid var(--border-2);border-radius:10px;padding:10px 13px;font:600 13px var(--sans);transition:border-color .15s ease}
.pagehead select:hover{border-color:var(--ca-panel-border)}
.matchup-report{display:none}.matchup-report.on{display:block}
.deployment-notice{position:relative;border:1px solid var(--border-violet);border-radius:12px;padding:11px 14px 11px 16px;
background:linear-gradient(135deg,rgba(124,77,255,.12),rgba(45,212,191,.04));color:var(--ink2);font-size:12px;margin-bottom:18px;overflow:hidden}
.deployment-notice::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(180deg,var(--v-light),var(--teal))}
.empty{color:var(--muted);font-size:13px;padding:18px;border:1px dashed var(--border-2);border-radius:8px}
.empty ul{margin:8px 0 0;padding-left:18px}.empty li{margin:3px 0}
.prop-table{min-width:960px}.prop-main{cursor:pointer}.prop-main:hover{background:rgba(124,77,255,.06)}
.prop-table th:first-child,.prop-table td:first-child{position:sticky;left:0;z-index:2;background:var(--card)}
.prop-table th:first-child{z-index:3}.prop-main:hover td:first-child{background:#181A27}
.pitcher-cell{display:flex;align-items:center;gap:9px;min-width:190px}.pitcher-cell .phead{width:40px;height:40px;flex:0 0 40px}
.pitcher-cell>div>span{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:11px;margin-top:3px}
.starter-base{min-width:88px}.starter-base b{display:block}.starter-base span{display:block;color:var(--muted);font-size:10px;margin-top:2px;white-space:nowrap}
.prop-cell{min-width:82px}.prop-cell>b{display:block;font:800 17px var(--display)}
.prop-range{display:block;font-size:10px;color:var(--muted);white-space:nowrap}.prop-mkt{display:block;font-size:10px;margin-top:3px;white-space:nowrap}
.prop-sub{display:block;color:var(--muted);font-size:10px;margin-top:4px}
.prop-detail{display:none;background:rgba(6,10,18,.6)}.prop-detail.on{display:table-row}
.prop-detail>td{padding:14px!important}.prop-detail-grid{display:grid;grid-template-columns:1fr;gap:12px}
.detail-strip{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin:0 0 10px}
.detail-strip b{color:var(--ink)}
.trend-sig{text-align:left;color:var(--ink2);font-size:12.5px;max-width:560px;white-space:normal;line-height:1.4}
.edge-row{display:flex;gap:18px;margin:2px 0 14px}.edge-cell{flex:1;min-width:0}
.edge-cell .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.edgebar{position:relative;height:20px;margin-top:5px;background:rgba(255,255,255,.06);border-radius:6px;overflow:hidden}
.edgebar i{position:absolute;left:0;top:0;height:100%;background:linear-gradient(90deg,rgba(124,77,255,.5),var(--teal));border-radius:6px}
.edgebar b{position:absolute;right:8px;top:0;line-height:20px;font-family:var(--display);font-weight:800;font-size:12px}
.trend-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px}
.trend-list li{font-size:12.5px;line-height:1.5;color:var(--ink2);padding-left:2px}
.trend-list .pill{margin-right:6px;vertical-align:middle}
@media(max-width:760px){#appshell{flex-direction:column}#nav{width:100%;height:auto;position:static;display:flex;flex-wrap:wrap;gap:4px}
#nav .brand,#nav .tagline{width:100%}.navb{width:auto}.cards{grid-template-columns:repeat(2,1fr)}}
"""


def build_app(featured_game, *, fetch=True, data_dir=None):
    repo = DataRepository(data_dir)
    reader = SupabaseReader()
    board = load_board(fetch=fetch)
    prop_prices = load_prop_board(fetch=fetch)
    pp_board = prizepicks.board_by_player(
        prizepicks.load_lines(settings.CACHE_DIR / "prizepicks_lines.json")
    )
    ud_board = prizepicks.board_by_player(
        underdog.load_lines(settings.CACHE_DIR / "underdog_lines.json")
    )
    gate = _promotion(reader)
    pitchers = build_pitcher_board(repo)
    promotion_status = (
        "PROMOTE" if gate.get("verdict") == "PROMOTE" else "HOLD/ABSTAIN"
    )
    for pitcher in pitchers:
        pitcher["market_report"] = market_report(
            pitcher,
            prop_prices,
            promotion_status=promotion_status,
        )
    slate, sd = _slate(repo)
    sync = repo.sync_manifest()
    games = [f'{g["away"]}@{g["home"]}' for g in slate if not g.get("err")]
    if games and featured_game.upper() not in games:
        featured_game = games[0]
    pks = {g["pk"] for g in slate if "pk" in g}
    # Sharp-vs-soft board, computed live from the odds board (self-contained — SMT parity).
    # We surface the strongest sharp lean PER GAME even when it's sub-2pt: today's market is
    # often efficient, and an empty board reads as broken. The 2pt "actionable" line is shown
    # via the graded divergence chip (≥2pt grades up; below that is a weak lean). 0.6pt floor
    # drops pure de-vig noise.
    sharp_by_pk = {}
    for game in slate:
        if game.get("err") or "pk" not in game:
            continue
        try:
            quotes = board.game_quotes(game["away"], game["home"])
        except Exception:
            quotes = []
        candidates = [
            q for q in quotes
            if q.sharp_divergence is not None and q.sharp_divergence >= 0.006
            and q.sharp_book_count >= 1 and q.soft_book_count >= 1
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda q: q.sharp_divergence)
        sharp_by_pk[game["pk"]] = [{
            "market_type": best.market,
            "selection": best.selection,
            "divergence": round(best.sharp_divergence, 4),
            "sharp_novig_prob": best.sharp_probability,
            "soft_novig_prob": best.soft_probability,
            "n_sharp_books": best.sharp_book_count,
            "n_soft_books": best.soft_book_count,
            "line_current": best.best_odds,
            "steam_flag": best.sharp_divergence >= 0.05,
        }]
    if not sharp_by_pk:
        for s in reader.get(
            "sharp_signals?select=game_pk,market_type,selection,divergence,steam_flag,"
            "sharp_novig_prob,soft_novig_prob,n_sharp_books,n_soft_books,line_current&limit=200"
        ).rows:
            if s.get("game_pk") in pks:
                sharp_by_pk.setdefault(s["game_pk"], []).append(s)

    matchup_reports = []
    model_by_pk = {}
    for game in slate:
        game_name = f'{game["away"]}@{game["home"]}'
        try:
            r = build_report(
                game["away"], game["home"], fetch=False, data_dir=data_dir,
                board=board, reader=reader, gate=gate,
                pitcher_rows=[
                    pitcher for pitcher in pitchers
                    if pitcher.get("team") in {game["away"], game["home"]}
                ],
            )
            # Capture the model's own read on each market (model%, edge vs price, EV) so the
            # Markets decision board can confirm or fade the sharp lean against the live number.
            if "pk" in game:
                model_by_pk[game["pk"]] = r.get("markets", [])
            report = report_body(r)
        except Exception as exc:
            report = f'<div class=empty>Could not build {e(game_name)}: {e(str(exc))}</div>'
        active = " on" if game_name == featured_game.upper() else ""
        matchup_reports.append(
            f'<div class="matchup-report{active}" data-game="{e(game_name)}">{report}</div>'
        )
    option_rows = []
    for game in slate:
        game_name = f'{game["away"]}@{game["home"]}'
        selected = " selected" if game_name == featured_game.upper() else ""
        option_rows.append(
            f'<option value="{game_name}"{selected}>'
            f'{game["away"]} @ {game["home"]}</option>'
        )
    options = "".join(option_rows)
    matchups = (
        f'<div class=pagehead><div><h2>Matchups</h2>'
        f'<div class=ctx>Projected runs, fair prices, and matchup impacts.</div></div>'
        f'<select id=gameSelect aria-label="Matchup" onchange="switchGame(this.value)">{options}</select></div>'
        f'{"".join(matchup_reports)}'
    )

    try:
        slate_reports = build_slate_reports(repo)
    except Exception:
        slate_reports = []

    # Slate-wide F5 board (for Research) — the same graded F5 rows the matchups produce.
    pkmap = {g["pk"]: f'{g["away"]}@{g["home"]}' for g in slate if "pk" in g}
    f5_board = [
        (pkmap.get(pk, str(pk)), m)
        for pk, rows in model_by_pk.items()
        for m in rows
        if str(m.get("market") or "").startswith("f5_")
    ]
    views = {
        "today": _today(slate, sd, sharp_by_pk, sync),
        "matchups": matchups,
        "trends": _trends(slate_reports),
        "markets": _markets(slate, sharp_by_pk, model_by_pk),
        "props": _props(pitchers, prop_prices, pp_board, ud_board),
        "portfolio": _portfolio(reader, gate, slate),
        "results": _results(reader),
        "research": _research(reader, gate, f5_board),
    }
    # Real Chase Analytics header nav: the 8 product views live in the top chase-nav-links,
    # switched in-page via show(). (The old left sidebar is retired in favor of the shared header.)
    nav_items = [(k, lbl, f"show('{k}')") for k, lbl in _NAV]
    sections = "".join(f'<section class="view{" on" if k == "today" else ""}" id="v-{k}">{html_}</section>'
                       for k, html_ in views.items())
    deployment_notice = os.getenv("MLB_MODEL_DEPLOYMENT_NOTICE", "").strip()
    sync_notice = str(sync.get("message") or "").strip()
    notice_text = " ".join(part for part in (deployment_notice, sync_notice) if part)
    notice = (
        f'<div class=deployment-notice>{e(notice_text)}</div>'
        if notice_text else ""
    )
    js = ("function show(k){document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));"
          "document.getElementById('v-'+k).classList.add('on');"
          "document.querySelectorAll('.chase-nav-link').forEach(b=>b.classList.toggle('active',b.dataset.v===k));"
          "window.scrollTo(0,0);}"
          "function switchGame(g){document.querySelectorAll('.matchup-report').forEach(x=>"
          "x.classList.toggle('on',x.dataset.game===g));const s=document.getElementById('gameSelect');"
          "if(s)s.value=g;}"
          "function openGame(g){switchGame(g);show('matchups');}"
          "function togglePitcher(i){const r=document.getElementById('prop-detail-'+i);"
          "if(r)r.classList.toggle('on');}"
          "function showReportTab(b,k){const r=b.closest('.rtabs');"
          "r.querySelectorAll('.rtabbar button').forEach(x=>x.classList.remove('on'));"
          "r.querySelectorAll('.pn').forEach(x=>x.classList.remove('on'));"
          "b.classList.add('on');r.querySelector('[data-panel=\"'+k+'\"]').classList.add('on');}")
    # The real Chase Analytics header carries the section nav; the body wears the production
    # stadium-outfield background via the same body classes the live dashboards use.
    chase_nav = chase_theme.nav_html(nav_items, "today", "MLB Model", status=(sd or "Live"))
    return (f'<!DOCTYPE html><html lang=en class=view-opening><head><meta charset=utf-8>'
            f'<meta name=viewport content="width=device-width,initial-scale=1">'
            f'<title>MLB Model — Chase Analytics</title>'
            f'<style>{chase_theme.theme_css()}{_CSS}{_SHELL_CSS}</style></head>'
            f'<body class="platform-dashboard opening-dashboard ca-bg-outfield">'
            f'{chase_nav}'
            f'<main id=main class=ca-page-shell>{notice}{sections}</main>'
            f'<script>{js}</script></body></html>')


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Unified MLB Model product shell.")
    ap.add_argument("--game", default="NYY@BOS", help="featured matchup")
    ap.add_argument("--out", default="mlb_model_app.html")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--data-dir")
    args = ap.parse_args()
    open(args.out, "w", encoding="utf-8").write(
        build_app(args.game, fetch=not args.no_fetch, data_dir=args.data_dir)
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
