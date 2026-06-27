"""
mlbmodel.report.app — the unified MLB Model product shell.

ONE coherent application (not separate dashboards) with a 7-section information architecture:
Today · Matchups · Markets · Props · Portfolio · Results · Research. Workflow:
discover -> inspect -> evaluate -> compare -> decide -> track -> review. Each section follows the
page hierarchy: context -> conclusion -> price/opportunity -> evidence -> risks -> action ->
methodology. The user never sees which repo a number came from — it reads as one platform.

    cd <bet-evaluator> && PYTHONPATH=<mlb-model> .venv/bin/python -m mlbmodel.report.app \
        --game NYY@BOS --out app.html [--no-fetch]
"""
from __future__ import annotations

import argparse
import html
import json
import urllib.request
import zlib
from datetime import date

import bet_evaluator as BE
import config

from mlbmodel.report.matchup import _CSS, _logo, build_report, report_body

e = html.escape


def _get(path):
    try:
        if not config.SUPABASE_URL:
            return []
        req = urllib.request.Request(
            config.SUPABASE_URL.rstrip("/") + "/rest/v1/" + path,
            headers={"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {config.SUPABASE_KEY}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []


def _slate():
    m = BE.load("today_matchups.csv")
    if m is None or "Away" not in m.columns:
        return [], None
    anchors = BE.refresh_anchors()
    sd = str(m.iloc[0].get("Slate_Date", "")) if len(m) else ""
    out = []
    for _, row in m.iterrows():
        a, h = str(row["Away"]).upper().strip(), str(row["Home"]).upper().strip()
        rec = {"away": a, "home": h, "time": str(row.get("Time", "") or ""),
               "pk": zlib.crc32(f"{date.today().isoformat()}|{a}|{h}".encode())}
        try:
            gd = BE.load_game(a, h)
            pr = BE.model_probabilities(gd, anchors)
            rec.update({"ph": pr.p_home_win, "total": pr.exp_total, "margin": pr.exp_margin,
                        "asp": gd.away_sp, "hsp": gd.home_sp,
                        "lean": h if pr.exp_margin > 0 else a})
        except Exception:
            rec["err"] = True
        out.append(rec)
    return out, sd


# ── sections (each = context -> conclusion -> evidence; honest empty states) ──
def _today(slate, sd, sharp_by_pk):
    rows = ""
    for g in slate:
        if g.get("err"):
            rows += f'<tr><td>{e(g["away"])}@{e(g["home"])}</td><td colspan=6 class=mut>no model inputs</td></tr>'
            continue
        sc = len(sharp_by_pk.get(g["pk"], []))
        rows += (f'<tr><td><span class=gcell>{_logo(g["away"],"tlogo sm")}<b>{e(g["away"])}</b>'
                 f'<span class=mut>@</span>{_logo(g["home"],"tlogo sm")}<b>{e(g["home"])}</b></span></td>'
                 f'<td class=mut>{e(g["time"])}</td>'
                 f'<td>{g["ph"]*100:.0f}% {e(g["home"])}</td>'
                 f'<td>{g["total"]:.1f}</td><td>{g["margin"]:+.1f}</td>'
                 f'<td class=side>{e(g["lean"])}</td>'
                 f'<td>{("<span class=pill warnc>"+str(sc)+" sharp</span>") if sc else "<span class=mut>—</span>"}</td></tr>')
    ok = [g for g in slate if not g.get("err")]
    n = len(ok)
    nsharp = len(sharp_by_pk)
    # biggest model leans (proxy for active opportunities until per-game odds load)
    leans = sorted(ok, key=lambda g: -abs(g.get("margin", 0)))[:6]
    lrows = "".join(
        f'<tr><td><b>{e(g["lean"])}</b> <span class=mut>{e(g["away"])}@{e(g["home"])}</span></td>'
        f'<td>{abs(g["margin"]):.1f} R</td><td>{max(g["ph"],1-g["ph"])*100:.0f}%</td>'
        f'<td>{g["total"]:.1f}</td></tr>' for g in leans)
    return f"""<h2>Today</h2>
 <div class=ctx>Discover the slate, then open a matchup. Model live; market prices load per game.</div>
 <div class=cards>
   <div class=card><div class=k>Games</div><div class=v>{n}</div></div>
   <div class=card><div class=k>Slate</div><div class=v style="font-size:16px">{e(sd or "—")}</div></div>
   <div class=card><div class=k>With sharp signal</div><div class=v>{nsharp}</div></div>
   <div class=card><div class=k>Lineups</div><div class=v style="font-size:16px">TBD</div></div>
 </div>
 <div class=cols>
   <div class=sec><h2>Slate</h2><div class=body>
     <table><tr><th>Game</th><th>Time</th><th>Win%(H)</th><th>Proj tot</th><th>Margin</th><th>Lean</th><th>Sharp</th></tr>{rows or '<tr><td class=mut colspan=7>No slate loaded.</td></tr>'}</table></div></div>
   <div class=sec><h2>Biggest model leans</h2><div class=body>
     <table><tr><th>Lean</th><th>Margin</th><th>Win%</th><th>Tot</th></tr>{lrows or '<tr><td class=mut colspan=4>—</td></tr>'}</table>
     <div class=note>Ranked by projected run margin. Open in <b>Matchups</b> for fair vs market edge.</div></div></div>
 </div></div>"""


def _markets(slate, sharp_by_pk):
    pkmap = {g["pk"]: f'{g["away"]}@{g["home"]}' for g in slate}
    rows = ""
    for pk, sigs in sharp_by_pk.items():
        for s in sigs:
            d = float(s.get("divergence") or 0) * 100
            tone = "pos" if d > 0 else "neg"
            rows += (f'<tr><td>{e(pkmap.get(pk, str(pk)))}</td><td>{e(s["market_type"])}</td>'
                     f'<td>{e(str(s["selection"]))}</td><td class={tone}>{d:+.1f}pt</td>'
                     f'<td>{"STEAM" if s.get("steam_flag") else "—"}</td></tr>')
    return f"""<h2>Markets</h2>
 <div class=ctx>Sharp-vs-soft de-vig divergence + steam, point-in-time from the warehouse.</div>
 <div class=sec><h2>Sharp money</h2><div class=body>
   <table><tr><th>Game</th><th>Market</th><th>Side</th><th>Divergence</th><th>Steam</th></tr>{rows or '<tr><td class=mut colspan=5>No sharp signals on the current slate.</td></tr>'}</table></div></div>"""


def _results():
    mp = _get("model_predictions?select=verdict&limit=1000")
    go = _get("game_outcomes?select=game_pk&limit=2000")
    brier = _get("v_open_vs_close_brier?select=*")
    b = brier[0] if brier else {}
    return f"""<h2>Results</h2>
 <div class=ctx>Settled performance, CLV and calibration. Builds as the daily settle loop runs.</div>
 <div class=cards>
   <div class=card><div class=k>Predictions logged</div><div class=v>{len(mp)}</div></div>
   <div class=card><div class=k>Games settled</div><div class=v>{len(go)}</div></div>
   <div class=card><div class=k>Open Brier</div><div class=v>{b.get('open_brier','—')}</div></div>
   <div class=card><div class=k>Close Brier</div><div class=v>{b.get('close_brier','—')}</div></div>
 </div>
 <div class=note>Open vs close Brier (n={b.get('n','—')}): the close is better-calibrated → act at the open. CLV/ROI populate once settled bets accrue.</div>"""


def _research():
    cal = _get("v_pm_calibration?select=price_bucket,n,avg_price,actual_win_rate,gap&order=price_bucket&limit=12")
    try:
        from mlbmodel.quant.promotion_gate import promotion_verdict
        from mlbmodel.backtest.walkforward import load_settled_ml_from_env  # noqa
        rows = _get("prediction_market_snapshots?market_type=eq.ml&settled=eq.true&won=not.is.null&open_prob=not.is.null&select=snapshot_time,open_prob,delta,won,implied_probability,volume")
        pv = promotion_verdict(rows) if rows else {"verdict": "ABSTAIN", "reasons": ["no settled sample"]}
    except Exception as exc:
        pv = {"verdict": "ABSTAIN", "reasons": [f"gate unavailable: {exc}"]}
    crows = "".join(
        f'<tr><td>{c["price_bucket"]}</td><td>{c["n"]}</td><td>{c["avg_price"]}</td>'
        f'<td>{c["actual_win_rate"]}</td><td class={"neg" if abs(c.get("gap") or 0)>0.1 else "mut"}>{c.get("gap")}</td></tr>'
        for c in cal) or '<tr><td class=mut colspan=5>No calibration sample.</td></tr>'
    tone = "pos" if pv["verdict"] == "PROMOTE" else "mut"
    return f"""<h2>Research</h2>
 <div class=ctx>Model + data health. Not part of the betting workflow — promotion is gated here.</div>
 <div class=sec><h2>Promotion gate</h2><div class=body>
   <div class="vbar {tone}"><b>{pv['verdict']}</b><span>{e('; '.join(pv.get('reasons', [])))}</span></div>
   <div class=note>OOS lower bound + Deflated-Sharpe + sample gate (Constitution STD-7/10/12). Default ABSTAIN.</div></div></div>
 <div class=sec><h2>Kalshi price calibration</h2><div class=body>
   <table><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div></div>"""


def _empty(title, ctx, items):
    li = "".join(f"<li>{e(x)}</li>" for x in items)
    return f"""<h2>{e(title)}</h2><div class=ctx>{e(ctx)}</div>
 <div class=sec><div class=body><div class=empty>Not yet enabled — planned structure:<ul>{li}</ul></div></div></div>"""


_NAV = [("today", "Today"), ("matchups", "Matchups"), ("markets", "Markets"),
        ("props", "Props"), ("portfolio", "Portfolio"), ("results", "Results"), ("research", "Research")]

_SHELL_CSS = """
body{display:flex;padding:0;min-height:100vh}
#nav{width:208px;flex:0 0 208px;background:linear-gradient(160deg,rgba(17,24,39,.96),rgba(8,13,22,.98));
border-right:1px solid var(--border);padding:18px 12px;position:sticky;top:0;height:100vh;overflow:auto}
#nav .brand{font-family:var(--display);font-weight:800;font-size:17px;background:linear-gradient(90deg,var(--teal),var(--v-light));
-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:2px}
#nav .tagline{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em;margin-bottom:16px}
.navb{display:block;width:100%;text-align:left;background:none;border:1px solid transparent;border-radius:9px;
color:var(--muted);font:600 13.5px var(--sans);padding:9px 11px;margin:3px 0;cursor:pointer}
.navb:hover{color:var(--ink);background:rgba(124,77,255,.08)}
.navb.on{color:var(--ink);background:linear-gradient(135deg,rgba(124,77,255,.2),rgba(45,212,191,.07));border-color:var(--border-violet)}
#main{flex:1;min-width:0;overflow:auto;padding:24px 26px 70px}
.view{display:none}.view.on{display:block}
#main>.view>h2:first-child{font-family:var(--display);font-weight:800;font-size:26px;margin:0 0 4px}
.ctx{color:var(--muted);font-size:13px;margin-bottom:16px}
.note{color:var(--muted);font-size:11.5px;margin-top:10px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:12px}
.card{background:linear-gradient(160deg,rgba(31,34,47,.7),rgba(16,18,27,.85));border:1px solid var(--border-2);border-radius:12px;padding:12px 15px}
.card .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:800}
.card .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:22px;margin-top:3px}
.cols{display:grid;grid-template-columns:1.4fr 1fr;gap:14px;align-items:start}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.gcell{display:inline-flex;align-items:center;gap:5px}
.empty{color:var(--muted);font-size:13px;padding:18px;border:1px dashed var(--border-2);border-radius:12px}
.empty ul{margin:8px 0 0;padding-left:18px}.empty li{margin:3px 0}
@media(max-width:760px){body{flex-direction:column}#nav{width:100%;height:auto;position:static;display:flex;flex-wrap:wrap;gap:4px}
#nav .brand,#nav .tagline{width:100%}.navb{width:auto}.cards{grid-template-columns:repeat(2,1fr)}}
"""


def build_app(featured_game, *, fetch=True):
    slate, sd = _slate()
    pks = {g["pk"] for g in slate}
    sharp = _get("sharp_signals?select=game_pk,market_type,selection,divergence,steam_flag&limit=200")
    sharp_by_pk = {}
    for s in sharp:
        if s["game_pk"] in pks:
            sharp_by_pk.setdefault(s["game_pk"], []).append(s)

    a, h = (s.strip().upper() for s in featured_game.split("@", 1))
    try:
        rep = report_body(build_report(a, h, fetch=fetch))
    except Exception as exc:
        rep = f'<div class=empty>Could not build {e(featured_game)}: {e(str(exc))}</div>'
    matchups = f'<h2>Matchups</h2><div class=ctx>Complete game analysis · featured: {e(featured_game)} · pick another in Today.</div>{rep}'

    views = {
        "today": _today(slate, sd, sharp_by_pk),
        "matchups": matchups,
        "markets": _markets(slate, sharp_by_pk),
        "props": _empty("Props", "Pitcher & hitter player markets.",
                        ["Pitcher props (K/outs/ER) from the projection layer", "Hitter props + platoon effects",
                         "Fair projection vs market price", "Correlation warnings"]),
        "portfolio": _empty("Portfolio", "Open risk & bankroll — paper-trading only.",
                            ["Open positions + entry/CLV", "Bankroll & exposure", "Correlated-risk warnings",
                             "Fractional-Kelly sizing with flat floor", "Hedge considerations"]),
        "results": _results(),
        "research": _research(),
    }
    nav = '<div class=brand>Chase Analytics</div><div class=tagline>MLB Model</div>' + "".join(
        f'<button class="navb{" on" if k == "today" else ""}" data-v="{k}" onclick="show(\'{k}\')">{lbl}</button>'
        for k, lbl in _NAV)
    sections = "".join(f'<section class="view{" on" if k == "today" else ""}" id="v-{k}">{html_}</section>'
                       for k, html_ in views.items())
    js = ("function show(k){document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));"
          "document.getElementById('v-'+k).classList.add('on');"
          "document.querySelectorAll('.navb').forEach(b=>b.classList.toggle('on',b.dataset.v===k));"
          "window.scrollTo(0,0);}")
    return (f'<!DOCTYPE html><html lang=en><head><meta charset=utf-8>'
            f'<meta name=viewport content="width=device-width,initial-scale=1">'
            f'<title>MLB Model — Chase Analytics</title><style>{_CSS}{_SHELL_CSS}</style></head><body>'
            f'<nav id=nav>{nav}</nav><main id=main>{sections}</main>'
            f'<script>{js}</script></body></html>')


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Unified MLB Model product shell.")
    ap.add_argument("--game", default="NYY@BOS", help="featured matchup")
    ap.add_argument("--out", default="mlb_model_app.html")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()
    open(args.out, "w", encoding="utf-8").write(build_app(args.game, fetch=not args.no_fetch))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
