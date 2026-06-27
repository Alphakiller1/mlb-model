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
from mlbmodel.market.quotes import load_board
from mlbmodel.portfolio.risk import summarize_positions
from mlbmodel.report.matchup import (
    _CSS,
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
def _today(slate, sd, sharp_by_pk):
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
   <div class=card><div class=k>Lineups</div><div class=v style="font-size:16px">TBD</div></div>
 </div>
 <div class=cols>
   <div class=sec><h2>Slate</h2><div class=body>
     <div class=table-scroll><table><tr><th>Game</th><th>Time</th><th>Win%(H)</th><th>Proj tot</th><th>Margin</th><th>Lean</th><th>Sharp</th></tr>{rows or '<tr><td class=mut colspan=7>No slate loaded.</td></tr>'}</table></div></div></div>
   <div class=sec><h2>Biggest model leans</h2><div class=body>
     <div class=table-scroll><table><tr><th>Lean</th><th>Margin</th><th>Win%</th><th>Tot</th></tr>{lrows or '<tr><td class=mut colspan=4>—</td></tr>'}</table></div>
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
   <div class=table-scroll><table><tr><th>Game</th><th>Market</th><th>Side</th><th>Divergence</th><th>Steam</th></tr>{rows or '<tr><td class=mut colspan=5>No sharp signals on the current slate.</td></tr>'}</table></div></div></div>"""


def _display(value, suffix="", digits=1):
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _props(slate):
    rows = ""
    starters = 0
    for game in slate:
        if game.get("err"):
            continue
        for side, pitcher, opponent, k_rate, fip, hr9 in (
            (game["away"], game.get("asp"), game["home"], game.get("ak"),
             game.get("afip"), game.get("ahr9")),
            (game["home"], game.get("hsp"), game["away"], game.get("hk"),
             game.get("hfip"), game.get("hhr9")),
        ):
            if pitcher and str(pitcher).strip().upper() not in {"TBD", "NONE", "NAN"}:
                starters += 1
            rows += (
                f'<tr><td><span class=gcell>{_logo(side, "tlogo sm")}'
                f'<b>{e(str(pitcher or "TBD"))}</b></span></td>'
                f'<td>{e(side)}</td><td class=mut>vs {e(opponent)}</td>'
                f'<td>{_display(k_rate, "%")}</td><td>{_display(fip, digits=2)}</td>'
                f'<td>{_display(hr9, digits=2)}</td>'
                '<td><span class="pill warnc">RESEARCH</span></td></tr>'
            )
    return f"""<h2>Props</h2>
 <div class=ctx>Starting-pitcher research from the same inputs used by each matchup model.</div>
 <div class=cards>
   <div class=card><div class=k>Starters named</div><div class=v>{starters}</div></div>
   <div class=card><div class=k>Slate pitchers</div><div class=v>{len(slate) * 2}</div></div>
   <div class=card><div class=k>Prop prices</div><div class=v style="font-size:16px">Not connected</div></div>
   <div class=card><div class=k>Action state</div><div class=v style="font-size:16px">Research only</div></div>
 </div>
 <div class=sec><h2>Pitcher board</h2><div class=body>
   <div class=table-scroll><table><tr><th>Starter</th><th>Team</th><th>Opponent</th>
   <th title="season strikeout rate">K%</th><th title="fielding independent pitching">FIP</th>
   <th title="home runs allowed per nine innings">HR/9</th><th>State</th></tr>
   {rows or '<tr><td class=mut colspan=7>No pitcher inputs loaded.</td></tr>'}</table></div>
   <div class=note>K%, FIP, and HR/9 are research inputs, not prop projections. No play can be issued until player lines, limits, and an independently validated prop model are available.</div>
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


def _research(reader, pv):
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
    return f"""<h2>Research</h2>
 <div class=ctx>Model + data health. Not part of the betting workflow — promotion is gated here.</div>
 <div class=sec><h2>Promotion gate</h2><div class=body>
   <div class="vbar {tone}"><b>{pv['verdict']}</b><span>{e('; '.join(pv.get('reasons', [])))}</span></div>
	   <div class=note>Promotion also requires an executable signal timestamp and entry price. Open-to-close hindsight cannot qualify.</div></div></div>
 <div class=sec><h2>Kalshi price calibration</h2><div class=body>
   <div class=table-scroll><table><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div></div></div>"""


_NAV = [("today", "Today"), ("matchups", "Matchups"), ("markets", "Markets"),
        ("props", "Props"), ("portfolio", "Portfolio"), ("results", "Results"), ("research", "Research")]

_SHELL_CSS = """
body{display:flex;padding:0;min-height:100vh}
#nav{width:208px;flex:0 0 208px;background:linear-gradient(160deg,rgba(17,24,39,.96),rgba(8,13,22,.98));
border-right:1px solid var(--border);padding:18px 12px;position:sticky;top:0;height:100vh;overflow:auto}
#nav .brand{font-family:var(--display);font-weight:800;font-size:17px;background:linear-gradient(90deg,var(--teal),var(--v-light));
-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:2px}
#nav .tagline{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em;margin-bottom:16px}
.navb{display:block;width:100%;text-align:left;background:none;border:1px solid transparent;border-radius:8px;
color:var(--muted);font:600 13.5px var(--sans);padding:9px 11px;margin:3px 0;cursor:pointer}
.navb:hover{color:var(--ink);background:rgba(124,77,255,.08)}
.navb.on{color:var(--ink);background:linear-gradient(135deg,rgba(124,77,255,.2),rgba(45,212,191,.07));border-color:var(--border-violet)}
#main{flex:1;min-width:0;overflow:auto;padding:24px 26px 70px}
.view{display:none}.view.on{display:block}
#main>.view>h2:first-child{font-family:var(--display);font-weight:800;font-size:26px;margin:0 0 4px}
.ctx{color:var(--muted);font-size:13px;margin-bottom:16px}
.note{color:var(--muted);font-size:11.5px;margin-top:10px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:12px}
.card{background:linear-gradient(160deg,rgba(31,34,47,.7),rgba(16,18,27,.85));border:1px solid var(--border-2);border-radius:8px;padding:12px 15px}
.card .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:800}
.card .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:22px;margin-top:3px}
.cols{display:grid;grid-template-columns:1.4fr 1fr;gap:14px;align-items:start}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.gcell{display:inline-flex;align-items:center;gap:5px}
.gamepick{border:0;background:none;color:inherit;font:inherit;padding:0;cursor:pointer;text-align:left}
.gamepick:hover b{color:var(--teal)}
.pagehead{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:14px}
.pagehead h2{font-family:var(--display);font-size:26px;margin:0 0 4px}
.pagehead .ctx{margin:0}
.pagehead select{min-width:180px;background:var(--card);color:var(--ink);border:1px solid var(--border-2);border-radius:8px;padding:9px 12px;font:600 13px var(--sans)}
.matchup-report{display:none}.matchup-report.on{display:block}
.deployment-notice{border:1px solid var(--border-violet);border-radius:8px;padding:10px 12px;
background:rgba(124,77,255,.08);color:var(--ink2);font-size:12px;margin-bottom:16px}
.empty{color:var(--muted);font-size:13px;padding:18px;border:1px dashed var(--border-2);border-radius:8px}
.empty ul{margin:8px 0 0;padding-left:18px}.empty li{margin:3px 0}
@media(max-width:760px){body{flex-direction:column}#nav{width:100%;height:auto;position:static;display:flex;flex-wrap:wrap;gap:4px}
#nav .brand,#nav .tagline{width:100%}.navb{width:auto}.cards{grid-template-columns:repeat(2,1fr)}}
"""


def build_app(featured_game, *, fetch=True, data_dir=None):
    repo = DataRepository(data_dir)
    reader = SupabaseReader()
    board = load_board(fetch=fetch)
    gate = _promotion(reader)
    slate, sd = _slate(repo)
    games = [f'{g["away"]}@{g["home"]}' for g in slate if not g.get("err")]
    if games and featured_game.upper() not in games:
        featured_game = games[0]
    pks = {g["pk"] for g in slate if "pk" in g}
    sharp_result = reader.get(
        "sharp_signals?select=game_pk,market_type,selection,divergence,steam_flag&limit=200"
    )
    sharp = sharp_result.rows
    sharp_by_pk = {}
    for s in sharp:
        if s["game_pk"] in pks:
            sharp_by_pk.setdefault(s["game_pk"], []).append(s)

    matchup_reports = []
    for game in slate:
        game_name = f'{game["away"]}@{game["home"]}'
        try:
            report = report_body(
                build_report(
                    game["away"], game["home"], fetch=False, data_dir=data_dir,
                    board=board, reader=reader, gate=gate,
                )
            )
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
        f'<div class=ctx>Decision first; evidence and methodology on demand.</div></div>'
        f'<select id=gameSelect aria-label="Matchup" onchange="switchGame(this.value)">{options}</select></div>'
        f'{"".join(matchup_reports)}'
    )

    views = {
        "today": _today(slate, sd, sharp_by_pk),
        "matchups": matchups,
        "markets": _markets(slate, sharp_by_pk),
        "props": _props(slate),
        "portfolio": _portfolio(reader, gate, slate),
        "results": _results(reader),
        "research": _research(reader, gate),
    }
    nav = '<div class=brand>Chase Analytics</div><div class=tagline>MLB Model</div>' + "".join(
        f'<button class="navb{" on" if k == "today" else ""}" data-v="{k}" onclick="show(\'{k}\')">{lbl}</button>'
        for k, lbl in _NAV)
    sections = "".join(f'<section class="view{" on" if k == "today" else ""}" id="v-{k}">{html_}</section>'
                       for k, html_ in views.items())
    deployment_notice = os.getenv("MLB_MODEL_DEPLOYMENT_NOTICE", "").strip()
    notice = (
        f'<div class=deployment-notice>{e(deployment_notice)}</div>'
        if deployment_notice else ""
    )
    js = ("function show(k){document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));"
          "document.getElementById('v-'+k).classList.add('on');"
          "document.querySelectorAll('.navb').forEach(b=>b.classList.toggle('on',b.dataset.v===k));"
          "window.scrollTo(0,0);}"
          "function switchGame(g){document.querySelectorAll('.matchup-report').forEach(x=>"
          "x.classList.toggle('on',x.dataset.game===g));const s=document.getElementById('gameSelect');"
          "if(s)s.value=g;}"
          "function openGame(g){switchGame(g);show('matchups');}"
          "function showReportTab(b,k){const r=b.closest('.rtabs');"
          "r.querySelectorAll('.rtabbar button').forEach(x=>x.classList.remove('on'));"
          "r.querySelectorAll('.pn').forEach(x=>x.classList.remove('on'));"
          "b.classList.add('on');r.querySelector('[data-panel=\"'+k+'\"]').classList.add('on');}")
    return (f'<!DOCTYPE html><html lang=en><head><meta charset=utf-8>'
            f'<meta name=viewport content="width=device-width,initial-scale=1">'
            f'<title>MLB Model — Chase Analytics</title><style>{_CSS}{_SHELL_CSS}</style></head><body>'
            f'<nav id=nav>{nav}</nav><main id=main>{notice}{sections}</main>'
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
