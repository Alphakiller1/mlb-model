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
import os

from mlbmodel.baseball.model import model_probabilities
from mlbmodel.baseball.repository import DataRepository
from mlbmodel.market.props import load_prop_board, market_report
from mlbmodel.market.quotes import load_board
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
            rec.update(
                {
                    "ph": pr.p_home_win,
                    "total": pr.exp_total,
                    "margin": pr.exp_margin,
                    "asp": gd.away_sp,
                    "hsp": gd.home_sp,
                    "ak": gd.away_k,
                    "hk": gd.home_k,
                    "afip": gd.away_fip,
                    "hfip": gd.home_fip,
                    "ahr9": gd.away_hr9,
                    "hhr9": gd.home_hr9,
                    "lean": h if pr.exp_margin > 0 else a,
                    "pk": gd.game_pk,
                }
            )
        except Exception:
            rec["err"] = True
        out.append(rec)
    return out, sd


# ── sections (each = context -> conclusion -> evidence; honest empty states) ──
def _today(slate, sd, sharp_by_pk, sync=None):
    ok = [g for g in slate if not g.get("err")]
    n = len(ok)
    nsharp = len(sharp_by_pk)
    sync = sync or {}
    sync_label = (
        "Exact"
        if sync.get("status") == "exact"
        else ("Live fallback" if sync.get("status") == "fallback" else "Untracked")
    )

    def projected_score(g):
        try:
            total = float(g.get("total") or 0)
            margin = float(g.get("margin") or 0)
        except (TypeError, ValueError):
            return "TBD"
        if total <= 0:
            return "TBD"
        home_runs = (total + margin) / 2
        away_runs = total - home_runs
        return f"{away_runs:.1f}-{home_runs:.1f}"

    rows = ""
    for g in slate:
        away = str(g.get("away") or "TBD")
        home = str(g.get("home") or "TBD")
        game = f"{away}@{home}"
        if g.get("err"):
            rows += (
                '<div class="slate-row slate-row--empty">'
                f"<div class=slate-matchup><div class=slate-teams><b>{e(away)}</b>"
                f"<span class=mut>@</span><b>{e(home)}</b></div>"
                "<span class=slate-sp>No model inputs loaded for this matchup.</span></div>"
                '<span class="slate-time mut">--</span>'
                "<div class=slate-metrics><span class=slate-metric><b>Hold</b>"
                "<i>status</i></span></div></div>"
            )
            continue
        sc = len(sharp_by_pk.get(g["pk"], []))
        sharp = (
            f'<span class="slate-metric slate-metric--sharp"><b>{sc}</b><i>sharp</i></span>'
            if sc
            else "<span class=slate-metric><b>0</b><i>sharp</i></span>"
        )
        rows += f"""<button type=button class=slate-row onclick="openGame('{game}')">
          <span class=slate-matchup>
            <span class=slate-teams>
              <span class=slate-team>{_logo(away, "tlogo sm")}<b>{e(away)}</b></span>
              <span class=mut>@</span>
              <span class=slate-team>{_logo(home, "tlogo sm")}<b>{e(home)}</b></span>
            </span>
            <span class=slate-sp>{e(str(g.get("asp") or "TBD"))} vs {e(str(g.get("hsp") or "TBD"))}</span>
          </span>
          <span class=slate-time>{e(str(g.get("time") or "--"))}</span>
          <span class=slate-metrics>
            <span class=slate-metric><b>{g["ph"] * 100:.0f}%</b><i>{e(home)} win</i></span>
            <span class=slate-metric><b>{projected_score(g)}</b><i>proj score</i></span>
            <span class=slate-metric><b>{g["total"]:.1f}</b><i>proj total</i></span>
            <span class="slate-metric slate-metric--lean"><b>{g["margin"]:+.1f} R</b><i>{e(str(g.get("lean") or ""))}</i></span>
            {sharp}
          </span>
        </button>"""

    # biggest model leans (proxy for active opportunities until per-game odds load)
    leans = sorted(ok, key=lambda g: -abs(g.get("margin", 0)))[:6]
    top = leans[0] if leans else None
    if top:
        top_game = f"{top['away']}@{top['home']}"
        top_card = f"""<button type=button class=lead-lean onclick="openGame('{top_game}')">
          <span class=lead-k>Top model lean</span>
          <b>{e(str(top.get("lean") or "Lean unavailable"))}</b>
          <span>{e(top["away"])} @ {e(top["home"])}</span>
          <span class=lead-strip>
            <i>{abs(top["margin"]):.1f} run gap</i>
            <i>{max(top["ph"], 1 - top["ph"]) * 100:.0f}% win side</i>
            <i>{top["total"]:.1f} total</i>
          </span>
        </button>"""
    else:
        top_card = "<div class=empty>No model leans available for this slate.</div>"

    lean_items = (
        "".join(
            f"""<button type=button class=lean-item onclick="openGame('{g["away"]}@{g["home"]}')">
          <span><b>{e(str(g.get("lean") or ""))}</b><i>{e(g["away"])} @ {e(g["home"])}</i></span>
          <em>{abs(g["margin"]):.1f} R</em>
        </button>"""
            for g in leans
        )
        or "<div class=empty>No slate loaded.</div>"
    )

    return f"""<h2>Today</h2>
 <div class=ctx>Start with the slate board, then open a matchup for model, market, risk, and freshness details.</div>
 <div class=cards>
   <div class=card><div class=k>Games</div><div class=v>{n}</div></div>
   <div class=card><div class=k>Slate</div><div class="v v-sm">{e(sd or "--")}</div></div>
   <div class=card><div class=k>With sharp signal</div><div class=v>{nsharp}</div></div>
   <div class=card><div class=k>MLBMA sync</div><div class="v v-sm">{e(sync_label)}</div></div>
 </div>
 <div class=today-grid>
   <div class="sec slate-command"><h2>Slate command board</h2><div class=body>
     <div class=slate-list>{rows or "<div class=empty>No slate loaded.</div>"}</div>
   </div></div>
   <div class=today-rail>
     <div class=sec><h2>Model focus</h2><div class=body>{top_card}
       <div class=note>Ranked by projected run margin. Open Matchups for fair price, lineup context, and risk gates.</div>
     </div></div>
     <div class=sec><h2>Lean queue</h2><div class=body><div class=lean-list>{lean_items}</div></div></div>
   </div>
 </div>"""


_MKT_LABEL = {
    "moneyline": "Moneyline",
    "h2h": "Moneyline",
    "ml": "Moneyline",
    "total": "Total",
    "totals": "Total",
    "spread": "Run line",
    "spreads": "Run line",
    "run_line": "Run line",
    "runline": "Run line",
    "f5_ml": "F5 ML",
    "f5_total": "F5 Total",
    "f5_runline": "F5 Run line",
}


# Verdict tiers, ranked best-to-worst. Each maps to a semantic badge + stake guide.
_VERDICT = {
    "STRONG": (4, 2.0, "pos", "Sharp + model agree, price gives value"),
    "BET": (3, 1.0, "pos", "Sharp + model agree at a fair-or-better #"),
    "LEAN": (2, 0.5, "warnc", "Right side, but the price is gone - wait for a number"),
    "SHARP": (1, 0.5, "side", "Sharp lean only - model/price hasn't confirmed"),
    "CONFLICT": (0, 0.0, "neg", "Sharp and the model disagree - pass"),
}


_VERDICT_LABEL = {
    "STRONG": "STRONG BET",
    "BET": "BET",
    "LEAN": "LEAN",
    "SHARP": "SHARP-ONLY",
    "CONFLICT": "PASS",
}


def _verdict_label(v):
    return _VERDICT_LABEL[v]


def _verdict_tone(v):
    return _VERDICT[v][2]


def _verdict_reason(v):
    return _VERDICT[v][3]


def _verdict_badge(v):
    return f'<span class="pill {_verdict_tone(v)}">{_VERDICT_LABEL[v]}</span>'


def _sel_match(model_side, sharp_sel):
    return str(model_side or "").strip().lower() == str(sharp_sel or "").strip().lower()


def _decide(s, model_rows):
    """Fuse one sharp signal with the model's read on the same bet → an actionable call.

    Three independent reads: sharp-vs-public divergence, model%-vs-price edge, and the live
    number itself. We bet only where sharp AND model agree the side is underpriced.
    """
    div = float(s.get("divergence") or 0)  # sharp − public (fraction)
    div_pts = div * 100
    sharp_p = float(s.get("sharp_novig_prob") or 0) * 100
    soft_p = float(s.get("soft_novig_prob") or 0) * 100
    mkt_type = str(s.get("market_type") or "").lower()
    sel = str(s.get("selection") or "")

    m = next(
        (
            r
            for r in (model_rows or [])
            if str(r.get("market") or "").lower() == mkt_type and _sel_match(r.get("side"), sel)
        ),
        None,
    )
    model_p = m.get("model") if m else None  # model fair % for this side
    medge = m.get("edge") if m else None  # model% − price-implied% (pts)
    ev = m.get("ev") if m else None  # EV per unit at the executable price
    price = m.get("mkt") if m else None  # the number you'd actually bet
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

    rank, stake, _tone, _why = _VERDICT[verdict]
    # Conviction score for ranking: tier first, then combined edge strength.
    score = rank * 1000 + div_pts + max(0.0, medge or 0)
    return {
        "verdict": verdict,
        "stake": stake,
        "score": score,
        "mkt_type": mkt_type,
        "sel": sel,
        "div_pts": div_pts,
        "sharp_p": sharp_p,
        "soft_p": soft_p,
        "model_p": model_p,
        "medge": medge,
        "ev": ev,
        "price": price,
        "fair": fair,
        "book": book,
        "n_sharp": s.get("n_sharp_books"),
        "n_soft": s.get("n_soft_books"),
        "steam": bool(s.get("steam_flag")),
    }


def _markets(slate, sharp_by_pk, model_by_pk=None):
    model_by_pk = model_by_pk or {}
    pkmap = {g["pk"]: f"{g['away']}@{g['home']}" for g in slate}
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
            bet = (
                f'<b>{e(mkt)} {e(d["sel"])}</b> <span class="pill side">{_num(d["price"])}</span>'
                + (f" <span class=mut>{e(str(d['book']))}</span>" if d["book"] else "")
                + (
                    f'<div class="mut microline">fair {_num(d["fair"])}</div>'
                    if isinstance(d["fair"], int)
                    else ""
                )
            )
        else:
            bet = f'<b>{e(mkt)} {e(d["sel"])}</b><div class="mut microline">no live #</div>'
        # Sharp lean: divergence chip + the sharp→public split that produced it.
        sharp = (
            f"<b class={_edge_grade(d['div_pts'] / 100)}>+{d['div_pts']:.1f}pt</b>"
            f'<div class="mut microline">{d["sharp_p"]:.0f}% vs {d["soft_p"]:.0f}% pub</div>'
            + ('<span class="pill warnc pill-tight">STEAM</span>' if d["steam"] else "")
        )
        # Model: its edge vs the price + EV — does the model confirm the sharp side?
        if d["medge"] is not None:
            ev_txt = f"{d['ev'] * 100:+.1f}% EV" if d["ev"] is not None else ""
            model = (
                f"<b class={_edge_grade(d['medge'] / 100)}>{d['medge']:+.1f}pt</b>"
                f'<div class="mut microline">model {d["model_p"]:.0f}% / {ev_txt}</div>'
            )
        elif d["model_p"] is not None:
            model = f"<span class=mut>{d['model_p']:.0f}% · no live #</span>"
        else:
            model = "<span class=mut>—</span>"
        stake = (
            f"<b class={_verdict_tone(d['verdict'])}>{d['stake']:.1f}u</b>"
            if d["stake"]
            else "<span class=mut>—</span>"
        )
        return (
            f"<tr><td><button class=gamepick onclick=\"openGame('{e(d['game'])}')\">{e(d['game'])}</button></td>"
            f"<td>{bet}</td><td>{sharp}</td><td>{model}</td>"
            f'<td title="{e(_verdict_reason(d["verdict"]))}">{_verdict_badge(d["verdict"])}</td>'
            f"<td class=num>{stake}</td></tr>"
        )

    def mobile_card(d):
        mkt = _MKT_LABEL.get(d["mkt_type"], d["mkt_type"].title())
        price = _num(d["price"])
        fair = _num(d["fair"])
        book = e(str(d["book"])) if d["book"] else "No book"
        sharp = f"+{d['div_pts']:.1f}pt / {d['sharp_p']:.0f}% vs {d['soft_p']:.0f}% public"
        if d["medge"] is not None:
            ev_txt = f" / {d['ev'] * 100:+.1f}% EV" if d["ev"] is not None else ""
            model = f"{d['medge']:+.1f}pt / model {d['model_p']:.0f}%{ev_txt}"
        elif d["model_p"] is not None:
            model = f"model {d['model_p']:.0f}% / no live number"
        else:
            model = "Model confirmation pending"
        stake = f"{d['stake']:.1f}u" if d["stake"] else "Pass"
        return f"""<article class=market-card>
      <button class=gamepick onclick="openGame('{e(d["game"])}')">{e(d["game"])}</button>
      <div class=market-card-pick><b>{e(mkt)} {e(d["sel"])}</b><span class="pill side">{price}</span></div>
      <div class=market-card-meta>{book} / fair {fair}</div>
      <div class=market-card-grid>
        <span><b class={_edge_grade(d["div_pts"] / 100)}>{sharp}</b><i>sharp lean</i></span>
        <span><b class={_edge_grade((d["medge"] or 0) / 100)}>{model}</b><i>model edge</i></span>
        <span>{_verdict_badge(d["verdict"])}<i>verdict</i></span>
        <span><b>{stake}</b><i>stake guide</i></span>
      </div>
    </article>"""

    rows = "".join(row(d) for d in plays) or (
        "<tr><td class=mut colspan=6>No sharp-vs-soft divergence on the current slate "
        "(needs the live game-odds feed). When sharp books price a side above the soft "
        "consensus, it surfaces here with the model's read.</td></tr>"
    )
    mobile_cards = "".join(mobile_card(d) for d in plays) or (
        "<div class=empty>No sharp-vs-soft divergence on the current slate. "
        "When the live odds feed is available, this board converts each signal into a compact decision card.</div>"
    )
    n_bet = sum(1 for d in plays if d["verdict"] in ("STRONG", "BET"))
    n_lean = sum(1 for d in plays if d["verdict"] == "LEAN")
    n_pass = sum(1 for d in plays if d["verdict"] == "CONFLICT")
    exposure = sum(d["stake"] for d in plays)
    top = plays[0] if plays else None
    top_txt = (
        f"{top['game']} · {_MKT_LABEL.get(top['mkt_type'], top['mkt_type'].title())} {top['sel']}"
        if top
        else "—"
    )
    top_sub = f"{_verdict_label(top['verdict'])} / {_verdict_reason(top['verdict'])}" if top else ""
    return f"""<h2>Markets · Where to bet</h2>
 <div class=ctx>Every play is graded on <b>three independent reads</b>: sharp-book money
   (de-vigged vs the public), the <b>model's</b> own edge vs the live number, and the price itself.
   <b class=pos>BET</b> = sharp and model agree the side is underpriced;
   <b class=warnc>LEAN</b> = right side, the number's gone;
   <b class=neg>PASS</b> = they disagree.</div>
 <div class=cards>
   <div class=card><div class=k>Top play</div><div class="v v-sm">{e(top_txt)}</div>
     <div class="mut microline">{e(top_sub)}</div></div>
   <div class=card><div class=k>Confirmed bets</div><div class=v>{n_bet}</div></div>
   <div class=card><div class=k>Leans</div><div class=v>{n_lean}</div></div>
   <div class=card><div class=k>Suggested exposure</div><div class=v>{exposure:.1f}u</div>
     <div class="mut microline">{n_pass} pass</div></div>
 </div>
 <div class=sec><h2>Decision board</h2><div class=body>
   <div class=market-mobile-board>{mobile_cards}</div>
   <div class="table-scroll market-desktop-board"><table><tr><th>Game</th><th>The bet</th>
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


def _props(pitchers, prop_board):
    def projection_cell(row, prop):
        value = (row.get("projections") or {}).get(prop) or {}
        if not value:
            return "<td class=mut>—</td>"
        report = next(
            (item for item in row.get("market_report", []) if item["prop"] == prop),
            None,
        )
        # Untrusted (thin-data) projections still show the line, but the edge is greyed —
        # the model's edge there is not reliable enough to act on.
        trusted = row.get("projection_trust") == "trusted"
        edge_cls = _edge_grade(report.get("edge")) if (trusted and report) else "mut"
        market = (
            f'<span class="prop-mkt">{report["side"][0].upper()} {report["line"]:g} '
            f"{report['best_odds']:+d} · "
            f'<b class="{edge_cls}">'
            f"{(report.get('edge') or 0) * 100:+.1f}pt</b></span>"
            if report
            else '<span class="prop-mkt mut">no line</span>'
        )
        return (
            f"<td class=prop-cell><b>{value['mean']:.1f}</b>"
            f"<span class=prop-range>range {value['p10']:.0f}–{value['p90']:.0f}</span>"
            f"{market}</td>"
        )

    def projection_chip(row, prop):
        value = (row.get("projections") or {}).get(prop) or {}
        if not value:
            return f"<span><b>--</b><i>{e(prop)} no projection</i></span>"
        return (
            f"<span><b>{value['mean']:.1f}</b>"
            f"<i>{e(prop)} range {value['p10']:.0f}-{value['p90']:.0f}</i></span>"
        )

    rows = ""
    cards = ""
    all_markets = []
    for index, row in enumerate(pitchers):
        reports = row.get("market_report") or []
        trusted = row.get("projection_trust") == "trusted"
        # Only trusted projections feed the ranked edge board; thin-data pitchers would
        # otherwise dominate it with phantom edges.
        if trusted:
            all_markets.extend([{"pitcher": row.get("pitcher"), **report} for report in reports])
        state = row.get("state", "DATA GAP")
        state_tone = (
            "neg"
            if state == "REGRESSION"
            else ("pos" if state == "PROGRESSION" else "side" if state == "STABLE" else "warnc")
        )
        best = reports[0] if reports else None
        market_state = best.get("state") if best else row.get("market_state", "NO MARKET")
        market_tone = "pos" if market_state in {"BET", "MONITOR"} else "mut"
        if not trusted:
            market_state = "THIN DATA"
            market_tone = "warnc"
        market_copy = (
            f"{e(best['side'].title())} {best['line']:g} at {best['best_odds']:+d} "
            f"({e(best['best_book'])})"
            if best
            else "No paired market line"
        )
        cards += f"""<article class=prop-card>
          <div class=prop-card-head>
            <div class=pitcher-cell>{_headshot(row.get("pitcher_id"))}
              <div><b>{e(str(row.get("pitcher") or "TBD"))}</b>
              <span>{_logo(row.get("team"), "tlogo sm")}{e(str(row.get("team") or ""))}</span></div>
            </div>
            <span class="pill {state_tone}">{e(state)}</span>
          </div>
          <div class=prop-card-vs>
            <span>{_logo(row.get("opponent"), "tlogo sm")}vs {e(str(row.get("opponent") or "TBD"))}</span>
            <span>{_display(row.get("expected_ip"), digits=1)} IP / {_display(row.get("skill_era"), digits=2)} runs/9</span>
          </div>
          <div class=prop-card-grid>
            {projection_chip(row, "K")}
            {projection_chip(row, "BB")}
            {projection_chip(row, "ER")}
            {projection_chip(row, "Outs")}
          </div>
          <div class=prop-card-foot>
            <span class="pill {market_tone}">{e(str(market_state))}</span>
            <i>{market_copy}</i>
          </div>
        </article>"""
        rows += (
            f'<tr class=prop-main onclick="togglePitcher({index})">'
            f"<td><div class=pitcher-cell>{_headshot(row.get('pitcher_id'))}"
            f"<div><b>{e(str(row.get('pitcher') or 'TBD'))}</b>"
            f"<span>{_logo(row.get('team'), 'tlogo sm')}{e(str(row.get('team') or ''))}</span>"
            f"</div></div></td>"
            f"<td><span class=gcell>{_logo(row.get('opponent'), 'tlogo sm')}"
            f"{e(str(row.get('opponent') or ''))}</span></td>"
            f'<td><span class="pill {state_tone}" title="Performance state from results versus underlying pitching skill">{e(state)}</span>'
            f"<span class=prop-sub>{float(row.get('luck_runs') or 0):+.2f} runs</span></td>"
            f"<td class=starter-base><b>{_display(row.get('expected_ip'), digits=1)} IP</b>"
            f"<span>{_display(row.get('skill_era'), digits=2)} runs/9</span></td>"
            f"{projection_cell(row, 'K')}{projection_cell(row, 'BB')}"
            f"{projection_cell(row, 'ER')}{projection_cell(row, 'Outs')}"
            f'<td><span class="pill {market_tone}">{e(str(market_state))}</span>'
            f"<span class=prop-sub>{e(str(row.get('confidence') or 'low'))} confidence</span></td></tr>"
        )
        pitch_rows = (
            "".join(
                f"<tr><td>{e(str(pitch.get('pitch') or ''))}</td>"
                f"<td>{_display(pitch.get('usage_pct'), '%')}</td>"
                f"<td>{_display(pitch.get('pitcher_whiff_pct'), '%')}</td>"
                f"<td>{_display(pitch.get('lineup_whiff_pct'), '%')}</td>"
                f"<td>{_display(pitch.get('pitcher_xwoba'), digits=3)}</td>"
                f"<td>{_display(pitch.get('lineup_xwoba'), digits=3)}</td>"
                f"<td class={'pos' if (pitch.get('k_delta') or 0) > 0 else 'neg'}>"
                f"{float(pitch.get('k_delta') or 0):+.2f} K%</td>"
                f"<td class={'pos' if (pitch.get('er_factor_delta') or 0) < 0 else 'neg'}>"
                f"{float(pitch.get('er_factor_delta') or 0) * 100:+.1f}% runs</td>"
                f"<td>{e(str(pitch.get('edge') or 'neutral'))}</td></tr>"
                for pitch in (row.get("pitch_matchup") or {}).get("pitches", [])[:6]
            )
            or "<tr><td class=mut colspan=9>No reliable pitch-overlap sample.</td></tr>"
        )
        market_rows = (
            "".join(
                f"<tr><td>{e(report['prop'])}</td><td>{e(report['side'].title())} {report['line']:g}</td>"
                f"<td>{report['best_odds']:+d} · {e(report['best_book'])}</td>"
                f"<td>{report['model_probability'] * 100:.1f}%</td>"
                f"<td>{report['market_probability'] * 100:.1f}%</td>"
                f"<td><b class={_edge_grade(report.get('edge'))}>"
                f"{(report.get('edge') or 0) * 100:+.1f}pt</b></td>"
                f"<td class={'pos' if (report.get('ev') or 0) > 0 else 'neg'}>"
                f"{(report.get('ev') or 0) * 100:+.1f}%</td>"
                f'<td><span class="pill {"pos" if report["state"] == "MONITOR" else "mut"}">{e(report["state"])}</span></td></tr>'
                for report in reports
            )
            or "<tr><td class=mut colspan=8>No paired prop price for this pitcher.</td></tr>"
        )
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
        f"<tr><td>{e(str(item['pitcher']))}</td><td>{e(item['prop'])}</td>"
        f"<td>{e(item['side'].title())} {item['line']:g}</td>"
        f"<td>{item['best_odds']:+d} · {e(item['best_book'])}</td>"
        f"<td>{item['model_probability'] * 100:.1f}%</td>"
        f"<td>{item['market_probability'] * 100:.1f}%</td>"
        f"<td><b class={_edge_grade(item.get('edge'))}>"
        f"{(item.get('edge') or 0) * 100:+.1f}pt</b></td>"
        f'<td><span class="pill {"pos" if item["state"] == "MONITOR" else "mut"}">{e(item["state"])}</span></td></tr>'
        for item in all_markets[:12]
    ) or (
        "<tr><td class=mut colspan=8>No paired pitcher-prop snapshot is loaded. "
        "Projections remain visible; price decisions remain NO MARKET.</td></tr>"
    )
    market_report_body = (
        "<div class=table-scroll><table><tr><th>Pitcher</th><th>Prop</th><th>Bet</th>"
        "<th>Best price</th><th>Model</th><th>Market</th><th>Edge</th><th>State</th></tr>"
        f"{report_rows}</table></div>"
        if all_markets
        else (
            "<div class=empty>No paired pitcher-prop snapshot is loaded. "
            "Projections remain visible; price decisions remain NO MARKET.</div>"
        )
    )
    confirmed = sum(1 for row in pitchers if row.get("lineup_status") == "confirmed")
    return f"""<h2>Pitcher Props</h2>
 <div class=ctx>Projection distributions, opponent pitch response, and executable price comparison.</div>
 <div class=cards>
   <div class=card><div class=k>Probable starters</div><div class=v>{len(pitchers)}</div></div>
   <div class=card><div class=k>Confirmed lineups</div><div class=v>{confirmed}/30</div></div>
   <div class=card><div class=k>Priced prop sides</div><div class=v>{len(all_markets)}</div></div>
   <div class=card><div class=k>Price feed</div><div class="v v-sm">{"LIVE" if all_markets else "NO SNAPSHOT"}</div></div>
 </div>
 <div class="sec prop-market-report"><h2>Prop market report</h2><div class=body>
   {market_report_body}</div></div>
 <div class=sec><h2>Pitcher board</h2><div class=body>
   <div class=prop-mobile-list>{cards or "<div class=empty>No pitcher inputs loaded.</div>"}</div>
   <div class="table-scroll prop-desktop-table"><table class=prop-table><tr><th>Starter</th><th>vs</th>
   <th>Performance</th><th title="Projected innings and expected runs allowed per nine">Starter baseline</th><th>K</th><th>BB</th>
   <th>ER</th><th>Outs</th><th>Market</th></tr>{rows or "<tr><td class=mut colspan=9>No pitcher inputs loaded.</td></tr>"}</table></div>
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
   <div class=card><div class=k>Auto sizing</div><div class="v v-sm">{sizing_state}</div></div>
 </div>
 <div class=sec><h2>Portfolio readiness</h2><div class=body>
   <div class=empty>Portfolio store unavailable: {e(result.error)}. Apply the paper-portfolio migration and configure warehouse read access to enable this view.</div>
   <div class=fallback-grid>
     <span class=fallback-card><b>Schema</b><span>Apply migrations/0002_paper_portfolio.sql so open positions can be read.</span><i>required</i></span>
     <span class=fallback-card><b>Warehouse</b><span>Configure Supabase read credentials for paper_positions.</span><i>data source</i></span>
     <span class=fallback-card><b>Gate</b><span>Auto sizing stays disabled until promotion rules clear.</span><i>risk control</i></span>
   </div>
 </div></div>"""

    positions = result.rows
    summary = summarize_positions(positions)
    pkmap = {int(game["pk"]): f"{game['away']}@{game['home']}" for game in slate if "pk" in game}
    rows = ""
    for position in positions:
        game_pk = int(position["game_pk"])
        line = position.get("line")
        selection = e(str(position.get("selection") or "—"))
        if line is not None:
            selection += f" <span class=mut>{float(line):+g}</span>"
        entry_odds = int(position["entry_odds"])
        model_p = _display(float(position["model_probability"]) * 100, "%")
        market_raw = position.get("market_probability")
        market_p = _display(float(market_raw) * 100, "%") if market_raw is not None else "—"
        rows += (
            f"<tr><td>{e(pkmap.get(game_pk, str(game_pk)))}</td>"
            f"<td>{e(str(position.get('market_type') or '—'))}</td>"
            f"<td>{selection}</td><td>{entry_odds:+d}</td>"
            f"<td>{model_p}</td><td>{market_p}</td>"
            f"<td>{_display(position.get('stake_units'), 'u', digits=2)}</td>"
            f"<td class=mut>{e(str(position.get('entry_time') or '—')[:16])}</td></tr>"
        )
    concentration = ""
    if summary.concentrated_games:
        labels = ", ".join(
            e(pkmap.get(game_pk, str(game_pk))) for game_pk in summary.concentrated_games
        )
        concentration = (
            f'<div class="vbar neg"><b>Concentration warning</b>'
            f"<span>More than 2.0u exposed on {labels}.</span></div>"
        )
    gate_note = (
        "Fractional-Kelly paper sizing is enabled by the promotion gate."
        if promoted
        else "Sizing is disabled until an executable strategy passes the promotion gate."
    )
    empty_guidance = (
        """<div class=fallback-grid>
     <span class=fallback-card><b>No open tickets</b><span>The portfolio is clean for the current slate.</span><i>state</i></span>
     <span class=fallback-card><b>Await signals</b><span>Paper positions populate only after executable model edges are logged.</span><i>workflow</i></span>
     <span class=fallback-card><b>Gate check</b><span>Position sizing remains tied to the promotion verdict.</span><i>control</i></span>
   </div>"""
        if not positions
        else ""
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
   {rows or "<tr><td class=mut colspan=8>No open paper positions.</td></tr>"}</table></div>
   {empty_guidance}
   <div class=note>{e(gate_note)} Live-money execution is outside this model.</div>
 </div></div>"""


def _results(reader):
    mp = reader.get("model_predictions?select=*&limit=1000")
    go = reader.get("game_outcomes?select=game_pk&limit=2000")
    brier = reader.get("v_open_vs_close_brier?select=*")
    sharp = reader.get("sharp_observations?settled=eq.true&select=won,push,market_type&limit=1000")
    errors = [result.error for result in (mp, go) if result.error]
    warehouse_note = (
        f"<div class=empty>Warehouse unavailable: {e('; '.join(dict.fromkeys(errors)))}</div>"
        if errors
        else ""
    )
    mp_rows = [] if mp.error else mp.rows
    go_rows = [] if go.error else go.rows
    brier_rows = [] if brier.error else brier.rows
    b = brier_rows[0] if brier_rows else {}

    def pick(row, *names, default=None):
        for name in names:
            if name in row and row.get(name) is not None:
                return row.get(name)
        return default

    def pct(value):
        if value is None:
            return "--"
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return str(value)

    def num(value, digits=3):
        if value is None:
            return "--"
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return str(value)

    settled_predictions = [
        row
        for row in mp_rows
        if bool(row.get("settled")) or row.get("won") is not None or row.get("push")
    ]
    wins = sum(1 for row in settled_predictions if row.get("won") is True)
    pushes = sum(1 for row in settled_predictions if row.get("push") is True)
    decisions = [row for row in settled_predictions if not row.get("push")]
    hit_rate = (wins / len(decisions)) if decisions else None
    pending = max(0, len(mp_rows) - len(settled_predictions))
    progress = (len(settled_predictions) / len(mp_rows) * 100) if mp_rows else 0
    sharp_rows = [] if sharp.error else sharp.rows
    sharp_decisions = [row for row in sharp_rows if not row.get("push")]
    sharp_wins = sum(1 for row in sharp_decisions if row.get("won") is True)
    sharp_rate = (sharp_wins / len(sharp_decisions)) if sharp_decisions else None

    verdict_counts = {}
    for row in mp_rows:
        label = str(pick(row, "verdict", "status", default="UNLABELED") or "UNLABELED")
        verdict_counts[label] = verdict_counts.get(label, 0) + 1
    verdict_rows = (
        "".join(
            f"<span><b>{e(label)}</b><i>{count}</i></span>"
            for label, count in sorted(
                verdict_counts.items(), key=lambda item: (-item[1], item[0])
            )[:5]
        )
        or "<span><b>No predictions</b><i>0</i></span>"
    )

    ledger_rows = ""
    for row in mp_rows[:8]:
        game = pick(row, "game", "matchup", "game_pk", default="unlinked")
        side = pick(row, "selection", "predicted_winner", "team", "side", default="--")
        model_p = pick(row, "model_probability", "probability", "p_home_win")
        verdict = pick(row, "verdict", "status", default="--")
        state = (
            "PUSH"
            if row.get("push")
            else "WIN"
            if row.get("won") is True
            else "LOSS"
            if row.get("won") is False
            else "PENDING"
        )
        tone = (
            "pos"
            if state == "WIN"
            else "neg"
            if state == "LOSS"
            else "warnc"
            if state == "PUSH"
            else "mut"
        )
        ledger_rows += (
            f"<tr><td>{e(str(game))}</td><td>{e(str(side))}</td>"
            f'<td>{pct(model_p)}</td><td><span class="pill mut">{e(str(verdict))}</span></td>'
            f'<td><span class="pill {tone}">{state}</span></td></tr>'
        )
    if not ledger_rows:
        ledger_rows = "<tr><td class=mut colspan=5>No model predictions logged yet.</td></tr>"
    readiness_panel = (
        """<div class=sec><h2>Settlement readiness</h2><div class=body>
   <div class=fallback-grid>
     <span class=fallback-card><b>Daily settle loop</b><span>mlb-model-settle grades model rows after finals land.</span><i>automation</i></span>
     <span class=fallback-card><b>Prediction IDs</b><span>Each prediction needs a stable id or prediction_id to write results back.</span><i>contract</i></span>
     <span class=fallback-card><b>Outcome fields</b><span>ML, totals, team totals, runlines, and F5 grade only when their final score fields exist.</span><i>data</i></span>
   </div>
 </div></div>"""
        if errors or not mp_rows
        else ""
    )

    return f"""<h2>Results</h2>
 <div class=ctx>Projection grading, settlement coverage, and market calibration. Builds as the daily settle loop runs.</div>
 <div class=cards>
   <div class=card><div class=k>Predictions logged</div><div class=v>{len(mp_rows)}</div></div>
   <div class=card><div class=k>Predictions settled</div><div class=v>{len(settled_predictions)}</div></div>
   <div class=card><div class=k>Model hit rate</div><div class=v>{pct(hit_rate)}</div></div>
   <div class=card><div class=k>Games settled</div><div class=v>{len(go_rows)}</div></div>
 </div>
 {warehouse_note}
 <div class=tracker-grid>
   <div class=sec><h2>Grading progress</h2><div class=body>
     <div class=progress-hero>
       <span><b>{progress:.0f}%</b><i>prediction settlement coverage</i></span>
       <div class=progress-meter><i style="width:{progress:.0f}%"></i></div>
     </div>
     <div class=result-status-grid>
       <span><b>{len(mp_rows)}</b><i>logged</i></span>
       <span><b>{len(settled_predictions)}</b><i>graded</i></span>
       <span><b>{pending}</b><i>awaiting finals</i></span>
       <span><b>{pushes}</b><i>pushes</i></span>
     </div>
     <div class=verdict-pile>{verdict_rows}</div>
   </div></div>
   <div class=sec><h2>Calibration snapshot</h2><div class=body>
     <div class=calibration-cards>
       <span><b>{num(b.get("open_brier"))}</b><i>open brier</i></span>
       <span><b>{num(b.get("close_brier"))}</b><i>close brier</i></span>
       <span><b>{len(sharp_decisions)}</b><i>sharp settled</i></span>
       <span><b>{pct(sharp_rate)}</b><i>sharp hit rate</i></span>
     </div>
     <div class=note>Open-versus-close calibration describes market learning. It does not, by itself, establish a profitable entry rule.</div>
   </div></div>
 </div>
 {readiness_panel}
 <div class=sec><h2>Prediction ledger</h2><div class=body>
   <div class=table-scroll><table><tr><th>Game</th><th>Side</th><th>Model</th><th>Verdict</th><th>Result</th></tr>{ledger_rows}</table></div>
 </div></div>"""


_CAT_LABEL = {
    "bullpen_fatigue": "BULLPEN",
    "form_vs_hand": "FORM vs HAND",
    "starter_quality": "SP QUALITY",
    "park": "PARK",
}
_CAT_TONE = {
    "bullpen_fatigue": "warnc",
    "form_vs_hand": "side",
    "starter_quality": "pos",
    "park": "mut",
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
        f"<b class={cls}>{score:.0f}</b></div>"
    )


def _trends(reports):
    if not reports:
        return (
            "<h2>Situational Trends</h2><div class=ctx>No slate loaded.</div>"
            "<div class=empty>No games to analyze.</div>"
        )
    # slate-wide dominant-trend board
    flat = []
    for r in reports:
        for t in r.trends:
            if t.category == "park":
                continue
            flat.append((r, t))
    flat.sort(key=lambda rt: rt[1].trend_score, reverse=True)
    board = (
        "".join(
            f"<tr><td><button class=gamepick onclick=\"openGame('{e(r.game)}')\">"
            f"{e(r.game)}</button></td>"
            f"<td><span class=gcell>{_logo(t.team, 'tlogo sm')}{e(t.team)}</span></td>"
            f'<td><span class="pill {_CAT_TONE.get(t.category, "mut")}">{_CAT_LABEL.get(t.category, t.category.upper())}</span></td>'
            f"<td class=trend-sig>{e(t.trend_description)}</td>"
            f"<td><b class={_mag_grade(t.effect_size)}>{t.effect_size:.1f}σ</b></td>"
            f"<td>{t.sample_size or '—'}</td>"
            f"<td class={_bet_tone(t.betting_implications[0] if t.betting_implications else '')}>"
            f"{e(t.betting_implications[0]) if t.betting_implications else '—'}</td></tr>"
            for r, t in flat[:14]
        )
        or "<tr><td class=mut colspan=7>No dominant situational trends cleared the threshold today.</td></tr>"
    )
    mobile_board = (
        "".join(
            f"""<article class=trend-card>
      <div class=trend-card-head>
        <button class=gamepick onclick="openGame('{e(r.game)}')">{e(r.game)}</button>
        <span class="pill {_CAT_TONE.get(t.category, "mut")}">{_CAT_LABEL.get(t.category, t.category.upper())}</span>
      </div>
      <div class=trend-card-team>{_logo(t.team, "tlogo sm")}<b>{e(t.team)}</b></div>
      <p>{e(t.trend_description)}</p>
      <div class=trend-card-foot>
        <span><b class={_mag_grade(t.effect_size)}>{t.effect_size:.1f}σ</b><i>signal</i></span>
        <span><b>{t.sample_size or "—"}</b><i>sample</i></span>
        <span><b class={_bet_tone(t.betting_implications[0] if t.betting_implications else "")}>{e(t.betting_implications[0]) if t.betting_implications else "—"}</b><i>lean</i></span>
      </div>
    </article>"""
            for r, t in flat[:14]
        )
        or "<div class=empty>No dominant situational trends cleared the threshold today.</div>"
    )

    # per-game cards
    cards = ""
    for r in sorted(reports, key=lambda x: -abs(x.away_edge_score - x.home_edge_score)):
        lean_txt = (
            f"edge <b class=side>{e(r.edge_lean)}</b>"
            if r.edge_lean != "even"
            else "edge <b class=mut>even</b>"
        )
        bullets = (
            "".join(
                f'<li><span class="pill {_CAT_TONE.get(t.category, "mut")}">{_CAT_LABEL.get(t.category, t.category.upper())}</span> '
                f"{e(t.trend_description)} "
                f"<span class=mut>· {e(t.mechanistic_explanation)}</span> "
                f"<b class={_bet_tone(t.betting_implications[0] if t.betting_implications else '')}>"
                f"→ {e(t.betting_implications[0]) if t.betting_implications else ''}</b></li>"
                for t in r.trends[:5]
            )
            or "<li class=mut>No dominant trends cleared the magnitude/sample threshold.</li>"
        )
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
   <div class=card><div class=k>Source</div><div class="v v-sm">MLBMA logs</div></div>
 </div>
 <div class=sec><h2>Dominant trend board</h2><div class=body>
   <div class=trend-mobile-board>{mobile_board}</div>
   <div class="table-scroll trend-desktop-board"><table><tr><th>Game</th><th>Team</th><th>Type</th><th>Signal</th>
   <th>Mag</th><th>n</th><th>Lean / bet</th></tr>{board}</table></div>
   <div class=note>Ranked by blended score (magnitude × sample × relevance). σ = SDs from the league baseline.</div></div></div>
 {cards}"""


def _research(reader, pv, f5_board=None):
    cal_result = reader.get(
        "v_pm_calibration?select=price_bucket,n,avg_price,actual_win_rate,gap"
        "&order=price_bucket&limit=12"
    )
    cal = [] if cal_result.error else cal_result.rows
    cal_n = sum(int(c.get("n") or 0) for c in cal)
    worst_gap = max((abs(float(c.get("gap") or 0)) for c in cal), default=0)
    crows = (
        "".join(
            f"<tr><td>{c['price_bucket']}</td><td>{c['n']}</td><td>{c['avg_price']}</td>"
            f"<td>{c['actual_win_rate']}</td><td class={'neg' if abs(c.get('gap') or 0) > 0.1 else 'mut'}>{c.get('gap')}</td></tr>"
            for c in cal
        )
        or "<tr><td class=mut colspan=5>No calibration sample.</td></tr>"
    )
    cal_cards = (
        "".join(
            f"<span><b>{e(str(c['price_bucket']))}</b><i>n={c['n']} / gap {c.get('gap')}</i></span>"
            for c in cal[:8]
        )
        or "<span><b>No sample</b><i>calibration pending</i></span>"
    )
    cal_note = (
        f"<div class=empty>Calibration view unavailable: {e(cal_result.error)}.</div>"
        if cal_result.error
        else ""
    )
    tone = "pos" if pv["verdict"] == "PROMOTE" else "mut"

    # First-5 (F5) board — the same graded F5 rows surfaced across the model, ranked by edge.
    f5 = sorted(
        (item for item in (f5_board or []) if item[1].get("edge") is not None),
        key=lambda item: -(item[1].get("edge") or 0),
    )
    if f5:
        f5_cards = "".join(
            f"""<article class=f5-card>
              <div><b>{e(g)}</b><span>{e(_MKT_LABEL.get(m["market"], m["market"]))}</span></div>
              <strong>{e(str(m.get("side")))}</strong>
              <i>{m.get("model"):.0f}% model / {m["edge"]:+.1f}pt edge</i>
              <span class="pill {m.get("tone", "mut")}">{e(str(m.get("state")))}</span>
            </article>"""
            for g, m in f5[:8]
        )
        f5rows = "".join(
            f"<tr><td><button class=gamepick onclick=\"openGame('{e(g)}')\">{e(g)}</button></td>"
            f'<td><span class="pill side">{e(_MKT_LABEL.get(m["market"], m["market"]))}</span></td>'
            f"<td><b>{e(str(m.get('side')))}</b></td><td class=num>{m.get('model'):.0f}%</td>"
            f"<td class=num>{(str(m['mkt']) if isinstance(m.get('mkt'), int) and m['mkt'] >= 0 else str(m.get('mkt'))) if m.get('mkt') is not None else '—'}</td>"
            f"<td><b class={_edge_grade((m.get('edge') or 0) / 100)}>{m['edge']:+.1f}pt</b></td>"
            f'<td><span class="pill {m.get("tone", "mut")}">{e(str(m.get("state")))}</span></td></tr>'
            for g, m in f5
        )
        f5_note = "First-5 markets, de-vigged and graded against the model - priced when live F5 odds are in the feed."
    else:
        f5_cards = "<div class=empty>No live F5 prices on the slate yet. Each matchup still shows model-fair F5 values.</div>"
        f5rows = "<tr><td class=mut colspan=7>No live F5 prices on the slate yet — F5 shows as model fair values in each matchup.</td></tr>"
        f5_note = "F5 prices appear here when the live F5 feed returns them."
    f5_panel = (
        f"<div class=sec><h2>First 5 (F5) edges</h2><div class=body>"
        f"<div class=f5-card-list>{f5_cards}</div>"
        f'<div class="table-scroll f5-table"><table><tr><th>Game</th><th>Market</th><th>Side</th>'
        f"<th>Model%</th><th>Price</th><th>Edge</th><th>State</th></tr>{f5rows}</table></div>"
        f"<div class=note>{f5_note}</div></div></div>"
    )
    research_readiness = (
        """<div class=sec><h2>Research readiness</h2><div class=body>
   <div class=fallback-grid>
     <span class=fallback-card><b>Calibration sample</b><span>v_pm_calibration needs enough settled rows to explain price buckets.</span><i>sample</i></span>
     <span class=fallback-card><b>F5 pricing</b><span>F5 edges appear only when the live feed returns first-five markets.</span><i>market feed</i></span>
     <span class=fallback-card><b>Promotion</b><span>Promotion requires signal time, entry price, out-of-sample history, and settlement coverage.</span><i>gate</i></span>
   </div>
 </div></div>"""
        if cal_result.error or not cal or not f5
        else ""
    )

    return f"""<h2>Research</h2>
 <div class=ctx>Model health, price calibration, and challenger-market evidence. Promotion is gated here before anything graduates.</div>
 <div class=research-grid>
   <div class=sec><h2>Promotion gate</h2><div class=body>
     <div class="gate-card {tone}">
       <span>Current state</span>
       <b>{pv["verdict"]}</b>
       <i>{e("; ".join(pv.get("reasons", [])) or "No gate reason returned.")}</i>
     </div>
     <div class=note>Promotion also requires an executable signal timestamp and entry price. Open-to-close hindsight cannot qualify.</div>
   </div></div>
   <div class=sec><h2>Research sample</h2><div class=body>
     <div class=calibration-cards>
       <span><b>{len(cal)}</b><i>price buckets</i></span>
       <span><b>{cal_n}</b><i>calibration games</i></span>
       <span><b>{worst_gap:.2f}</b><i>largest gap</i></span>
       <span><b>{len(f5)}</b><i>priced F5 edges</i></span>
     </div>
   </div></div>
 </div>
 {f5_panel}
 {research_readiness}
 <div class=sec><h2>Kalshi price calibration</h2><div class=body>
   {cal_note}
   <div class=calibration-list>{cal_cards}</div>
   <div class=table-scroll><table><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div>
 </div></div>"""


# All 8 sections are always reachable -- each has an honest empty/unavailable state instead
# of being hidden, so the nav itself never implies a section doesn't exist yet.
_NAV = [
    ("today", "Today"),
    ("matchups", "Matchups"),
    ("trends", "Trends"),
    ("markets", "Markets"),
    ("props", "Props"),
    ("portfolio", "Portfolio"),
    ("results", "Results"),
    ("research", "Research"),
]

_NAV_MARKS = {
    "today": "TD",
    "matchups": "MU",
    "trends": "TR",
    "markets": "MK",
    "props": "PP",
    "portfolio": "PF",
    "results": "RS",
    "research": "RL",
}

_SHELL_CSS = """
:root{
--ink:var(--text);--ink2:var(--text-2);--muted:var(--text-3);--muted-2:var(--text-4);
--accent:var(--ca-brand);--v-deep:var(--ca-purple-dark)
}
body{padding:0;min-height:100vh;overflow-x:hidden}
*,*::before,*::after{box-sizing:border-box}
#appshell{display:flex;min-height:calc(100vh - 68px);background:
linear-gradient(90deg,rgba(255,255,255,.026) 1px,transparent 1px),
linear-gradient(180deg,rgba(255,255,255,.018) 1px,transparent 1px),
radial-gradient(ellipse 78% 55% at 82% 2%,rgba(124,77,255,.13),transparent 62%);
background-size:28px 28px,28px 28px,auto}
#nav{width:212px;flex:0 0 212px;background:linear-gradient(180deg,rgba(14,16,24,.98),rgba(8,9,15,.995));
border-right:1px solid rgba(54,59,77,.82);padding:16px 12px;position:sticky;top:68px;height:calc(100vh - 68px);overflow:auto;box-shadow:18px 0 50px rgba(0,0,0,.20)}
.rail-brand{display:flex;align-items:center;gap:10px;padding:7px 6px 15px;margin-bottom:8px;border-bottom:1px solid rgba(54,59,77,.72)}
.rail-brand-mark{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,rgba(154,107,255,.24),rgba(91,43,224,.20));border:1px solid rgba(154,107,255,.34);font:900 12px var(--display);color:var(--ca-purple-light);box-shadow:0 0 24px rgba(124,77,255,.16)}
#nav .brand{font-family:var(--display);font-weight:900;font-size:16px;line-height:1;color:var(--ink);letter-spacing:.01em;text-transform:uppercase}
#nav .tagline{color:var(--muted);font-size:9.5px;text-transform:uppercase;letter-spacing:.12em;margin-top:4px}
.navb{display:flex;align-items:center;gap:10px;width:100%;text-align:left;background:transparent;border:1px solid transparent;border-radius:10px;
color:var(--muted);font:700 13px var(--sans);padding:9px 10px;margin:4px 0;cursor:pointer;min-height:44px}
.navb .navmark{display:inline-flex;align-items:center;justify-content:center;width:27px;height:27px;border-radius:8px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.055);font:900 9px var(--display);letter-spacing:.04em;color:var(--text-3)}
.navb:hover{color:var(--ink);background:rgba(124,77,255,.08);border-color:rgba(124,77,255,.18)}
.navb:hover .navmark{color:var(--ca-purple-light);border-color:rgba(154,107,255,.24)}
.navb.on{color:var(--ink);background:linear-gradient(135deg,rgba(124,77,255,.22),rgba(154,107,255,.06));border-color:rgba(154,107,255,.42);box-shadow:inset 3px 0 0 var(--ca-purple)}
.navb.on .navmark{color:var(--text-bright);background:var(--v-grad);border-color:transparent}
#main{flex:1;min-width:0;overflow:auto;padding:24px 28px 72px}
.view{display:none}.view.on{display:block}
#main>.view>h2:first-child{font-family:var(--display);font-weight:900;font-size:30px;line-height:1;margin:0 0 4px;background:linear-gradient(180deg,var(--text-bright) 0%,var(--heading-sheen-1) 42%,var(--text-2) 64%,var(--text-bright) 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.ctx{color:var(--ink2);font-size:13px;margin-bottom:16px;max-width:860px;line-height:1.5;overflow-wrap:anywhere}
.note{color:var(--muted);font-size:11.5px;margin-top:10px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:14px}
.card{background:linear-gradient(180deg,rgba(24,27,38,.90),rgba(13,15,23,.96));border:1px solid rgba(54,59,77,.86);border-radius:10px;padding:13px 15px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.card .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:800}
.card .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:22px;margin-top:3px}
.card .v.v-sm{font-size:16px}
.microline{font-size:11px;line-height:1.35}
.pill-tight{font-size:10px;padding:2px 8px}
.pill.side{background:rgba(124,77,255,.13);color:var(--side);border-color:rgba(154,107,255,.24)}
.fallback-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:12px}
.fallback-card{min-width:0;min-height:112px;padding:13px 14px;border:1px solid rgba(54,59,77,.78);border-radius:10px;background:linear-gradient(180deg,rgba(24,27,38,.82),rgba(13,15,23,.94));box-shadow:inset 0 1px 0 rgba(255,255,255,.035);overflow-wrap:anywhere}
.fallback-card b{display:block;color:var(--ink);font:900 16px var(--display);overflow-wrap:anywhere}
.fallback-card span{display:block;color:var(--ink2);font-size:12px;line-height:1.45;margin-top:7px;overflow-wrap:anywhere}
.fallback-card i{display:block;color:var(--muted);font-style:normal;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.06em;margin-top:10px}
.cols{display:grid;grid-template-columns:1.4fr 1fr;gap:14px;align-items:start}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.today-grid{display:grid;grid-template-columns:minmax(0,1.48fr) minmax(300px,.82fr);gap:14px;align-items:start}
.today-rail{display:flex;flex-direction:column;gap:14px}
.slate-list,.lean-list{display:flex;flex-direction:column;gap:8px}
.slate-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 14px;align-items:center;width:100%;min-height:106px;padding:12px 14px;text-align:left;color:inherit;background:linear-gradient(180deg,rgba(28,31,44,.82),rgba(13,15,23,.92));border:1px solid rgba(54,59,77,.86);border-radius:10px;box-shadow:inset 0 1px 0 rgba(255,255,255,.045);cursor:pointer}
.slate-row:hover,.slate-row:focus-visible{outline:0;border-color:rgba(154,107,255,.55);background:linear-gradient(180deg,rgba(35,38,55,.92),rgba(16,18,28,.96));box-shadow:0 0 0 3px rgba(124,77,255,.12),inset 3px 0 0 var(--ca-purple)}
.slate-row--empty{cursor:default;border-style:dashed;color:var(--muted)}
.slate-matchup{min-width:0;display:block}.slate-teams{display:flex;align-items:center;gap:8px;font-family:var(--display);font-weight:900;font-size:17px;line-height:1.1;color:var(--ink);min-width:0}
.slate-team{display:inline-flex;align-items:center;gap:5px;min-width:0}.slate-team b{white-space:nowrap}.slate-sp{display:block;margin-top:6px;color:var(--muted);font-size:11px;line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.slate-time{font:900 13px var(--display);color:var(--ink2);text-align:center;letter-spacing:.02em}
.slate-metrics{display:grid;grid-column:1/-1;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;min-width:0}
.slate-metric{display:block;min-height:46px;padding:7px 8px;border:1px solid rgba(54,59,77,.72);border-radius:8px;background:rgba(255,255,255,.034);min-width:0}
.slate-metric b{display:block;color:var(--ink);font:900 15px var(--display);line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.slate-metric i{display:block;margin-top:5px;color:var(--muted);font-style:normal;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.slate-metric--lean b{color:var(--side)}.slate-metric--sharp{border-color:rgba(var(--rgb-gold),.35);background:rgba(var(--rgb-gold),.08)}.slate-metric--sharp b{color:var(--gold)}
.lead-lean{display:flex;flex-direction:column;align-items:flex-start;gap:7px;width:100%;min-height:150px;padding:15px;text-align:left;color:inherit;background:linear-gradient(145deg,rgba(124,77,255,.24),rgba(20,22,34,.98) 54%,rgba(45,212,191,.08));border:1px solid rgba(154,107,255,.42);border-radius:10px;box-shadow:inset 0 1px 0 rgba(255,255,255,.055);cursor:pointer}
.lead-lean:hover,.lead-lean:focus-visible{outline:0;border-color:rgba(45,212,191,.45);box-shadow:0 0 0 3px rgba(45,212,191,.09),inset 0 1px 0 rgba(255,255,255,.07)}
.lead-k{font-size:10px;font-weight:900;letter-spacing:.09em;text-transform:uppercase;color:var(--teal)}.lead-lean>b{font:900 31px/1 var(--display);color:var(--ink)}.lead-lean>span:not(.lead-k):not(.lead-strip){color:var(--ink2);font-size:13px}
.lead-strip{display:flex;gap:6px;flex-wrap:wrap;margin-top:auto}.lead-strip i{font-style:normal;padding:6px 8px;border-radius:999px;background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.075);color:var(--ink2);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.04em}
.lean-item{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:48px;padding:9px 10px;text-align:left;color:inherit;background:rgba(255,255,255,.028);border:1px solid rgba(54,59,77,.70);border-radius:9px;cursor:pointer}
.lean-item:hover,.lean-item:focus-visible{outline:0;border-color:rgba(154,107,255,.35);background:rgba(124,77,255,.08)}.lean-item span{min-width:0}.lean-item b{display:block;color:var(--ink);font:900 15px var(--display)}.lean-item i{display:block;color:var(--muted);font-style:normal;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.lean-item em{font-style:normal;font:900 13px var(--display);color:var(--side);white-space:nowrap}
@media(min-width:1500px){.slate-row{grid-template-columns:minmax(260px,1fr) 68px minmax(390px,1.08fr);min-height:78px}.slate-metrics{grid-column:auto}}
@media(max-width:1140px){.today-grid{grid-template-columns:1fr}}
@media(max-width:920px){.slate-row{grid-template-columns:1fr}.slate-time{text-align:left}.slate-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}}
.gcell{display:inline-flex;align-items:center;gap:5px}
.gamepick{border:0;background:none;color:inherit;font:inherit;padding:0;cursor:pointer;text-align:left}
.gamepick:hover b{color:var(--teal)}
.pagehead{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:14px}
.pagehead h2{font-family:var(--display);font-size:26px;margin:0 0 4px}
.pagehead .ctx{margin:0}
.pagehead select{min-width:180px;background:var(--card);color:var(--ink);border:1px solid var(--border-2);border-radius:8px;padding:10px 12px;font:700 13px var(--sans)}
.matchup-report{display:none}.matchup-report.on{display:block}
.deployment-notice{border:1px solid var(--border-violet);border-radius:8px;padding:10px 12px;
background:rgba(124,77,255,.08);color:var(--ink2);font-size:12px;margin-bottom:16px}
.empty{color:var(--muted);font-size:13px;line-height:1.45;overflow-wrap:anywhere;padding:18px;border:1px dashed var(--border-2);border-radius:10px;background:rgba(18,20,29,.62)}
.empty ul{margin:8px 0 0;padding-left:18px}.empty li{margin:3px 0}
.prop-table{min-width:960px}.prop-main{cursor:pointer}.prop-main:hover{background:rgba(124,77,255,.06)}
.prop-table th:first-child,.prop-table td:first-child{position:sticky;left:0;z-index:2;background:var(--card)}
.prop-table th:first-child{z-index:3}.prop-main:hover td:first-child{background:var(--bg-4)}
.prop-mobile-list{display:none}.prop-card{padding:12px;border:1px solid rgba(54,59,77,.82);border-radius:10px;background:linear-gradient(180deg,rgba(24,27,38,.90),rgba(13,15,23,.96));box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.prop-card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}.prop-card-vs{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:11px;margin-bottom:10px}.prop-card-vs span{display:inline-flex;align-items:center;gap:5px}
.prop-card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.prop-card-grid span{min-height:48px;padding:8px;border-radius:8px;border:1px solid rgba(54,59,77,.72);background:rgba(255,255,255,.032)}.prop-card-grid b{display:block;color:var(--ink);font:900 17px var(--display)}.prop-card-grid i{display:block;margin-top:4px;color:var(--muted);font-style:normal;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.05em}
.prop-card-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px}.prop-card-foot i{color:var(--muted);font-style:normal;font-size:11px;text-align:right}
.tracker-grid,.research-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start;margin-bottom:14px}
.progress-hero{display:flex;align-items:center;gap:14px;margin-bottom:12px}.progress-hero span{flex:0 0 136px}.progress-hero b{display:block;color:var(--ink);font:900 31px/1 var(--display)}.progress-hero i{display:block;color:var(--muted);font-style:normal;font-size:10px;font-weight:900;letter-spacing:.06em;text-transform:uppercase;margin-top:5px}
.progress-meter{position:relative;flex:1;height:12px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden;border:1px solid rgba(255,255,255,.075)}.progress-meter i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--ca-purple),var(--teal))}
.result-status-grid,.calibration-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.result-status-grid span,.calibration-cards span,.calibration-list span{min-height:58px;padding:9px 10px;border:1px solid rgba(54,59,77,.74);border-radius:9px;background:rgba(255,255,255,.032)}.result-status-grid b,.calibration-cards b,.calibration-list b{display:block;color:var(--ink);font:900 18px var(--display)}.result-status-grid i,.calibration-cards i,.calibration-list i{display:block;color:var(--muted);font-style:normal;font-size:9px;font-weight:900;letter-spacing:.06em;text-transform:uppercase;margin-top:4px}
.verdict-pile{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.verdict-pile span{display:inline-flex;align-items:center;gap:8px;min-height:34px;padding:7px 10px;border-radius:999px;background:rgba(124,77,255,.08);border:1px solid rgba(154,107,255,.24)}.verdict-pile b{font:900 11px var(--display);color:var(--ink)}.verdict-pile i{font-style:normal;color:var(--muted);font-size:11px}
.gate-card{min-height:150px;padding:16px;border:1px solid rgba(54,59,77,.86);border-radius:10px;background:linear-gradient(145deg,rgba(24,27,38,.96),rgba(10,12,19,.98));box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}.gate-card.pos{border-color:rgba(60,203,127,.34);background:linear-gradient(145deg,rgba(60,203,127,.14),rgba(10,12,19,.98) 62%)}.gate-card span{display:block;color:var(--teal);font-size:10px;font-weight:900;letter-spacing:.09em;text-transform:uppercase}.gate-card b{display:block;color:var(--ink);font:900 34px/1 var(--display);margin:8px 0}.gate-card i{display:block;color:var(--ink2);font-style:normal;font-size:12px;line-height:1.45}
.f5-card-list{display:none}.f5-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:11px 12px;border:1px solid rgba(54,59,77,.78);border-radius:9px;background:rgba(255,255,255,.032)}.f5-card b{display:block;color:var(--ink);font:900 15px var(--display)}.f5-card span:not(.pill){display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.f5-card strong{color:var(--ink);font:900 18px var(--display);text-align:right}.f5-card i{grid-column:1/-1;color:var(--muted);font-style:normal;font-size:11px}.f5-card .pill{justify-self:start}
.calibration-list{display:none;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:12px}
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
.trend-mobile-board,.market-mobile-board{display:none}
.trend-card,.market-card{padding:12px;border:1px solid rgba(54,59,77,.82);border-radius:10px;background:linear-gradient(180deg,rgba(24,27,38,.90),rgba(13,15,23,.96));box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.trend-card-head,.market-card-pick{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px}
.trend-card-head .gamepick,.market-card .gamepick{font-family:var(--display);font-weight:900;color:var(--ink)}
.trend-card-team{display:flex;align-items:center;gap:7px;margin-bottom:8px;color:var(--ink)}
.trend-card-team b{font-family:var(--display);font-weight:900}
.trend-card p{margin:0;color:var(--ink2);font-size:12.5px;line-height:1.45}
.trend-card-foot,.market-card-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:10px}
.trend-card-foot span,.market-card-grid span{min-height:56px;padding:8px;border:1px solid rgba(54,59,77,.72);border-radius:8px;background:rgba(255,255,255,.032);min-width:0}
.trend-card-foot b,.market-card-grid b{display:block;font:900 14px/1.15 var(--display);overflow-wrap:anywhere}
.trend-card-foot b:not([class]),.market-card-grid b:not([class]){color:var(--ink)}
.trend-card-foot i,.market-card-grid i{display:block;margin-top:5px;color:var(--muted);font-style:normal;font-size:9px;font-weight:900;letter-spacing:.06em;text-transform:uppercase}
.market-card{display:flex;flex-direction:column;gap:7px}
.market-card-pick{margin-bottom:0}.market-card-pick b{font:900 17px/1.1 var(--display);color:var(--ink)}
.market-card-meta{color:var(--muted);font-size:11px}
.market-card-grid{grid-template-columns:repeat(2,minmax(0,1fr));margin-top:3px}
@media(max-width:760px){#appshell{flex-direction:column}#nav{width:100%;height:auto;flex:0 0 auto;position:static;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;overflow:hidden}
.rail-brand{grid-column:1/-1;width:100%;margin-bottom:4px}.navb{width:100%;min-width:0;margin:0}.navb span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ca-shell-meta__item{flex:1 1 100%;min-width:0}.cards{grid-template-columns:1fr}.pagehead{align-items:stretch;flex-direction:column}.pagehead select{width:100%;min-width:0}#appshell,#main,.view{max-width:100%;overflow-x:hidden}#main{width:100%;padding:18px 14px 64px}.sec,.card,.empty{max-width:100%}.trend-desktop-board,.market-desktop-board{display:none}.trend-mobile-board,.market-mobile-board{display:flex;flex-direction:column;gap:10px}}
@media(max-width:480px){.ca-shell-meta__item{flex:1 1 100%;min-width:0}.cards{grid-template-columns:1fr}.pagehead{align-items:stretch;flex-direction:column}.pagehead select{width:100%;min-width:0}.trend-card-foot,.market-card-grid{grid-template-columns:1fr}}
@media(max-width:760px){.today-grid{gap:12px}.slate-row{padding:11px;gap:10px;min-height:0}.slate-teams{flex-wrap:wrap;font-size:16px}.slate-sp{white-space:normal}.slate-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.lead-lean{min-height:132px}.lead-lean>b{font-size:26px}}
@media(max-width:760px){.prop-market-report .table-scroll{max-width:100%;overflow-x:auto}.prop-desktop-table{display:none}.prop-mobile-list{display:flex;flex-direction:column;gap:10px}.prop-card .pitcher-cell{min-width:0}.prop-card .pitcher-cell .phead{width:44px;height:44px;flex-basis:44px}.prop-card-head{align-items:flex-start;flex-direction:column}.prop-card-foot{align-items:flex-start;flex-direction:column}.prop-card-foot i{text-align:left}}
@media(max-width:760px){.tracker-grid,.research-grid,.fallback-grid{grid-template-columns:1fr}.progress-hero{align-items:flex-start;flex-direction:column}.progress-hero span{flex:auto}.progress-meter{width:100%}.result-status-grid,.calibration-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.f5-card-list{display:flex;flex-direction:column;gap:8px}.f5-table{display:none}.calibration-list{display:grid;grid-template-columns:1fr 1fr}.calibration-list+.table-scroll{display:none}.gate-card{min-height:128px}.gate-card b{font-size:28px}}
@media(max-width:520px){.slate-metrics{grid-template-columns:1fr}.lead-strip i{width:100%;text-align:center}.lean-item{align-items:flex-start;flex-direction:column}.lean-item em{align-self:flex-end}}
@media(max-width:520px){.ctx,.empty{max-width:340px}.prop-card-grid{grid-template-columns:1fr}.prop-card-vs{align-items:flex-start;flex-direction:column}.prop-card-head{align-items:flex-start}.prop-card-head>.pill{margin-top:4px}.result-status-grid,.calibration-cards,.calibration-list{grid-template-columns:1fr}.f5-card{grid-template-columns:1fr}.f5-card strong{text-align:left}}
"""


def build_app(featured_game, *, fetch=True, data_dir=None):
    repo = DataRepository(data_dir)
    reader = SupabaseReader()
    board = load_board(fetch=fetch)
    prop_prices = load_prop_board(fetch=fetch)
    gate = _promotion(reader)
    pitchers = build_pitcher_board(repo)
    promotion_status = "PROMOTE" if gate.get("verdict") == "PROMOTE" else "HOLD/ABSTAIN"
    for pitcher in pitchers:
        pitcher["market_report"] = market_report(
            pitcher,
            prop_prices,
            promotion_status=promotion_status,
        )
    slate, sd = _slate(repo)
    sync = repo.sync_manifest()
    games = [f"{g['away']}@{g['home']}" for g in slate if not g.get("err")]
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
            q
            for q in quotes
            if q.sharp_divergence is not None
            and q.sharp_divergence >= 0.006
            and q.sharp_book_count >= 1
            and q.soft_book_count >= 1
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda q: q.sharp_divergence)
        sharp_by_pk[game["pk"]] = [
            {
                "market_type": best.market,
                "selection": best.selection,
                "divergence": round(best.sharp_divergence, 4),
                "sharp_novig_prob": best.sharp_probability,
                "soft_novig_prob": best.soft_probability,
                "n_sharp_books": best.sharp_book_count,
                "n_soft_books": best.soft_book_count,
                "line_current": best.best_odds,
                "steam_flag": best.sharp_divergence >= 0.05,
            }
        ]
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
        game_name = f"{game['away']}@{game['home']}"
        try:
            r = build_report(
                game["away"],
                game["home"],
                fetch=False,
                data_dir=data_dir,
                board=board,
                reader=reader,
                gate=gate,
                pitcher_rows=[
                    pitcher
                    for pitcher in pitchers
                    if pitcher.get("team") in {game["away"], game["home"]}
                ],
            )
            # Capture the model's own read on each market (model%, edge vs price, EV) so the
            # Markets decision board can confirm or fade the sharp lean against the live number.
            if "pk" in game:
                model_by_pk[game["pk"]] = r.get("markets", [])
            report = report_body(r)
        except Exception as exc:
            report = f"<div class=empty>Could not build {e(game_name)}: {e(str(exc))}</div>"
        active = " on" if game_name == featured_game.upper() else ""
        matchup_reports.append(
            f'<div class="matchup-report{active}" data-game="{e(game_name)}">{report}</div>'
        )
    option_rows = []
    for game in slate:
        game_name = f"{game['away']}@{game['home']}"
        selected = " selected" if game_name == featured_game.upper() else ""
        option_rows.append(
            f'<option value="{game_name}"{selected}>{game["away"]} @ {game["home"]}</option>'
        )
    options = "".join(option_rows)
    matchups = (
        f"<div class=pagehead><div><h2>Matchups</h2>"
        f"<div class=ctx>Projected runs, fair prices, and matchup impacts.</div></div>"
        f'<select id=gameSelect aria-label="Matchup" onchange="switchGame(this.value)">{options}</select></div>'
        f"{''.join(matchup_reports)}"
    )

    try:
        slate_reports = build_slate_reports(repo)
    except Exception:
        slate_reports = []

    # Slate-wide F5 board (for Research) — the same graded F5 rows the matchups produce.
    pkmap = {g["pk"]: f"{g['away']}@{g['home']}" for g in slate if "pk" in g}
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
        "props": _props(pitchers, prop_prices),
        "portfolio": _portfolio(reader, gate, slate),
        "results": _results(reader),
        "research": _research(reader, gate, f5_board),
    }
    nav = (
        "<div class=rail-brand><span class=rail-brand-mark>CA</span>"
        "<div><div class=brand>Chase Analytics</div><div class=tagline>MLB Model</div></div></div>"
        + "".join(
            f'<button class="navb{" on" if k == "today" else ""}" data-v="{k}" '
            f"onclick=\"show('{k}')\"><span class=navmark aria-hidden=true>"
            f"{_NAV_MARKS[k]}</span><span>{lbl}</span></button>"
            for k, lbl in _NAV
        )
    )
    sections = "".join(
        f'<section class="view{" on" if k == "today" else ""}" id="v-{k}">{html_}</section>'
        for k, html_ in views.items()
    )
    deployment_notice = os.getenv("MLB_MODEL_DEPLOYMENT_NOTICE", "").strip()
    sync_notice = str(sync.get("message") or "").strip()
    notice_text = " ".join(part for part in (deployment_notice, sync_notice) if part)
    notice = f"<div class=deployment-notice>{e(notice_text)}</div>" if notice_text else ""
    sync_label = (
        "Exact slate"
        if sync.get("status") == "exact"
        else ("Live fallback" if sync.get("status") == "fallback" else "Untracked")
    )
    gate_label = str(gate.get("verdict") or "HOLD/ABSTAIN")
    meta = (
        "<div class=ca-shell-meta>"
        f'<div class="ca-shell-meta__item is-live"><b>Slate</b><span>{e(sd or "No slate")}</span></div>'
        f"<div class=ca-shell-meta__item><b>Games</b><span>{len(games)}</span></div>"
        f"<div class=ca-shell-meta__item><b>MLBMA Sync</b><span>{e(sync_label)}</span></div>"
        f'<div class="ca-shell-meta__item is-watch"><b>Gate</b><span>{e(gate_label)}</span></div>'
        "</div>"
    )
    js = (
        "function show(k,persist=true){const target=document.getElementById('v-'+k);if(!target)return;"
        "document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));"
        "target.classList.add('on');"
        "document.querySelectorAll('.navb').forEach(b=>b.classList.toggle('on',b.dataset.v===k));"
        "if(persist&&location.hash.slice(1)!==k)history.replaceState(null,'','#'+k);"
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
        "b.classList.add('on');r.querySelector('[data-panel=\"'+k+'\"]').classList.add('on');}"
        "window.addEventListener('hashchange',()=>show(location.hash.slice(1),false));"
        "if(location.hash)show(location.hash.slice(1),false);"
    )
    # Brand bar only -- the left sidebar below already handles section navigation for this
    # product's 8-view information architecture (kept, per the shared design contract's
    # allowance for product-specific IA); duplicating the same links in both would just be
    # two navs fighting for the same job.
    chase_nav = chase_theme.nav_html([], "today", "MLB Model")
    return (
        f"<!DOCTYPE html><html lang=en><head><meta charset=utf-8>"
        f'<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>MLB Model — Chase Analytics</title>"
        f"<style>{chase_theme.theme_css()}{_CSS}{_SHELL_CSS}</style></head><body>"
        f"{chase_nav}"
        f"<div id=appshell><nav id=nav>{nav}</nav><main id=main>{notice}{meta}{sections}</main></div>"
        f"<script>{js}</script></body></html>"
    )


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
