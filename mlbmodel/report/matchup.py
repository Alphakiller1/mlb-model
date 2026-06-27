"""
Matchup Intelligence Report — the canonical, scannable output of the unified MLB Model.

A research/trading TERMINAL, not a written report. It follows the Sharp Money Tracker / Chase
Analytics design system (violet, Roboto Condensed + tabular nums, percentile color chips
c-elite..c-poor, premium tables, comparison bars, inline SVG charts). Presentation order:
raw number -> visual context -> comparative meaning -> modeled implication -> (optional) explanation.

Powered by the *actual* validated logic (analytical inheritance, not imitation): bet_evaluator's
expected-runs model + value layer + risk layer, empirical percentiles from the MLBMA pipeline CSVs
(sp_profiles / team_profiles), and sharp signals from the governed warehouse. Every number is
traceable to its source + timestamp + model/metric version. No prose dominates; explanations live
behind progressive disclosure.

Parallel-run: imports legacy bet_evaluator; run with the legacy env on path:
    cd <bet-evaluator> && PYTHONPATH=<mlb-model> .venv/bin/python -m mlbmodel.report.matchup \
        --game NYY@BOS --out report.html
"""
from __future__ import annotations

import argparse
import html
import math
import zlib
from datetime import date, datetime, timezone

import bet_evaluator as BE
import config


# ── stat helpers (raw -> percentile -> semantic chip) ────────────────────────
def _cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _emp_pctile(series, value: float, lower_better: bool) -> float | None:
    """Empirical percentile of `value` within `series` (a pandas Series). 0..100."""
    try:
        import pandas as pd
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty or value is None:
            return None
        p = float((s < value).mean()) * 100
        return round(100 - p if lower_better else p, 0)
    except Exception:
        return None


def _chip(pct: float | None) -> tuple[str, str]:
    """Percentile -> (css class, label) using the Sharp Money Tracker scale."""
    if pct is None:
        return "c-na", "—"
    if pct >= 90:
        return "c-elite", "elite"
    if pct >= 70:
        return "c-good", "strong"
    if pct >= 40:
        return "c-mid", "avg"
    if pct >= 20:
        return "c-weak", "weak"
    return "c-poor", "poor"


def _f(v, nd=2):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "—"


# ── factor decomposition (drivers) ───────────────────────────────────────────
def _factors(gd, anchors):
    out = []

    def f(name, factor, runs_axis, market, conf, priced):
        out.append({"name": name, "pct": round((factor - 1) * 100, 1),
                    "runs": runs_axis, "market": market, "conf": conf, "priced": priced})
    f("Away offense (OSI)", BE.offense_factor(gd.away_osi), "away", "Away TT · Total · ML", "med", "partial")
    f("Home offense (OSI)", BE.offense_factor(gd.home_osi), "home", "Home TT · Total · ML", "med", "partial")
    f("Away SP run-prevent", BE.pitch_factor(gd.away_fip, gd.away_pen_factor), "home", "Home TT · Total · ML", "high", "yes")
    f("Home SP run-prevent", BE.pitch_factor(gd.home_fip, gd.home_pen_factor), "away", "Away TT · Total · ML", "high", "yes")
    f("Park", gd.park_factor, "total", "Total · TT", "high", "yes")
    return sorted(out, key=lambda x: -abs(x["pct"]))


# ── advantage matrix (team vs team, with empirical percentiles) ──────────────
def _advantage(gd, anchors):
    sp = BE.load("sp_profiles.csv")
    tp = BE.load("team_profiles.csv")
    fip_s = sp["FIP"] if sp is not None and "FIP" in sp.columns else None
    k_s = sp["K_pct"] if sp is not None and "K_pct" in sp.columns else None
    hr_s = sp["HR9"] if sp is not None and "HR9" in sp.columns else None
    osi_s = tp["osi"] if tp is not None and "osi" in tp.columns else None

    rows = []

    def row(cat, a_val, h_val, series, lower_better, impact):
        ap = _emp_pctile(series, a_val, lower_better) if series is not None else None
        hp = _emp_pctile(series, h_val, lower_better) if series is not None else None
        # edge side: who is better (higher pctile = better)
        edge = "—"
        if ap is not None and hp is not None:
            edge = gd.away if ap > hp else (gd.home if hp > ap else "even")
        rows.append({"cat": cat, "a_val": a_val, "h_val": h_val, "a_pct": ap, "h_pct": hp,
                     "edge": edge, "impact": impact})

    row("Starting pitching (FIP)", gd.away_fip, gd.home_fip, fip_s, True,
        f"{(BE.pitch_factor(gd.home_fip, gd.home_pen_factor) - BE.pitch_factor(gd.away_fip, gd.away_pen_factor)) * anchors['league_runs']:+.2f} R")
    row("SP strikeout (K%)", gd.away_k, gd.home_k, k_s, False, "K props · Total")
    row("SP home-run risk (HR/9)", gd.away_hr9, gd.home_hr9, hr_s, True, "Total · TT")
    row("Offense (OSI)", gd.away_osi, gd.home_osi, osi_s, False,
        f"{(BE.offense_factor(gd.away_osi) - BE.offense_factor(gd.home_osi)) * anchors['league_runs']:+.2f} R")
    row("Bullpen (factor)", gd.away_pen_factor, gd.home_pen_factor, None, True, "Late ML · Total")
    return rows


def _market_row(market, side, line, ou, gd, probs, anchors, odds):
    p, desc = BE.market_probability(market, side, line, gd, probs, anchors, ou)
    p = BE.clip(p, 0.02, 0.98)
    row = {"label": desc, "model": round(p * 100, 1), "fair": BE.prob_to_american(p),
           "mkt": None, "impl": None, "edge": None, "ev": None, "max": BE.prob_to_american(p),
           "state": "NO-EDGE", "tone": "mut"}
    if odds is not None:
        v = BE.value_layer(p, odds)
        impl = BE.american_to_implied(odds) * 100
        row.update({"mkt": odds, "impl": round(impl, 1), "edge": round(p * 100 - impl, 1),
                    "ev": round(v["ev_per_unit"], 3)})
        if v["verdict"] == "PLAY":
            row.update({"state": "BET", "tone": "pos"})
        elif v["verdict"] == "REVIEW":
            row.update({"state": "MONITOR", "tone": "warnc"})
        elif row["edge"] and row["edge"] > 0:
            row.update({"state": "MONITOR", "tone": "warnc"})
        else:
            row.update({"state": "AVOID", "tone": "neg"})
    return row


def build_report(away, home, *, odds_map=None):
    anchors = BE.refresh_anchors()
    gd = BE.load_game(away, home)
    probs = BE.model_probabilities(gd, anchors)
    odds_map = odds_map or {}
    markets = [
        _market_row("ml", gd.home, None, None, gd, probs, anchors, odds_map.get(("ml", gd.home))),
        _market_row("ml", gd.away, None, None, gd, probs, anchors, odds_map.get(("ml", gd.away))),
        _market_row("total", "over", round(probs.exp_total * 2) / 2, None, gd, probs, anchors, odds_map.get(("total", "over"))),
        _market_row("total", "under", round(probs.exp_total * 2) / 2, None, gd, probs, anchors, odds_map.get(("total", "under"))),
        _market_row("runline", gd.home if probs.exp_margin > 0 else gd.away, -1.5, None, gd, probs, anchors, None),
    ]
    gpk = zlib.crc32(f"{date.today().isoformat()}|{away}|{home}".encode())
    return {"away": away, "home": home, "gd": gd, "probs": probs, "anchors": anchors,
            "markets": markets, "factors": _factors(gd, anchors), "advantage": _advantage(gd, anchors),
            "risks": BE.risk_layer(gd, "ml", anchors), "sharp": _sharp_for(gpk), "game_pk": gpk,
            "model_version": config.MODEL_VERSION, "metric_version": config.METRIC_VERSION,
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _sharp_for(gpk):
    try:
        import json
        import urllib.request
        if not config.SUPABASE_URL:
            return []
        url = (config.SUPABASE_URL.rstrip("/") + "/rest/v1/sharp_signals"
               f"?game_pk=eq.{gpk}&select=market_type,selection,divergence,steam_flag")
        req = urllib.request.Request(url, headers={"apikey": config.SUPABASE_KEY,
                                                   "Authorization": f"Bearer {config.SUPABASE_KEY}"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []


# ── inline SVG charts (every chart answers a decision question) ───────────────
def _svg_winprob(ph, pa, home, away):
    hw = round(ph * 100)
    return (f'<svg viewBox="0 0 300 26" width="100%" height="26" preserveAspectRatio="none">'
            f'<rect x="0" y="6" width="{hw*3}" height="14" rx="4" fill="#2dd4bf"/>'
            f'<rect x="{hw*3}" y="6" width="{(100-hw)*3}" height="14" rx="4" fill="#9A6BFF"/></svg>'
            f'<div class="cap"><span class="pos">{home} {hw}%</span>'
            f'<span class="side">{away} {100-hw}%</span></div>')


def _svg_rundist(exp_a, exp_h, sd, away, home):
    """Two expected-run bell curves (away violet, home teal) over 0..12 runs."""
    def path(mu, color):
        pts = []
        for i in range(0, 121):
            x = i / 10
            y = math.exp(-((x - mu) ** 2) / (2 * sd ** 2))
            pts.append(f"{i*2.4:.1f},{70 - y*60:.1f}")
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>'
    grid = "".join(f'<line x1="{r*24}" y1="0" x2="{r*24}" y2="70" stroke="rgba(148,163,184,.10)"/>'
                   f'<text x="{r*24}" y="82" fill="#707687" font-size="9">{r}</text>' for r in range(0, 13, 2))
    return (f'<svg viewBox="0 0 290 88" width="100%" height="92">{grid}'
            f'{path(exp_a, "#9A6BFF")}{path(exp_h, "#2dd4bf")}</svg>'
            f'<div class="cap"><span class="side">{away} μ{exp_a:.1f}</span>'
            f'<span class="pos">{home} μ{exp_h:.1f}</span></div>')


def _bar(pct, tone):
    w = max(2, min(100, abs(pct) * 4))
    return f'<span class="dbar"><i style="width:{w}%;background:var(--{tone})"></i></span>'


# ── render (Chase Analytics / Sharp Money Tracker design contract) ────────────
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Roboto+Condensed:wght@700;800&family=DM+Sans:wght@400;500;600;700;800&display=swap');
:root{color-scheme:dark;--bg:#08090F;--card:#12141D;--card-2:#181B26;--raised:#20232F;--border:#262A38;--border-2:#363B4D;
--ink:#F8F9FC;--ink2:#BCC0CC;--muted:#9196A6;--muted-2:#707687;--v-light:#C4B0FF;--accent:#9A6BFF;--v-deep:#5B2BE0;
--v-grad:linear-gradient(135deg,#9A6BFF,#5B2BE0);--green:#3CCB7F;--red:#F2545B;--gold:#E8C24A;--teal:#2DD4BF;--side:#C4B0FF;
--display:"Roboto Condensed",system-ui,sans-serif;--sans:"DM Sans",system-ui,sans-serif}
*{box-sizing:border-box}body{margin:0;color:var(--ink);font-family:var(--sans);font-size:15px;
background:radial-gradient(ellipse 90% 60% at 78% -8%,rgba(124,77,255,.14),transparent 58%),var(--bg);background-attachment:fixed}
.wrap{max-width:1180px;margin:0 auto;padding:22px 20px 70px;display:flex;flex-direction:column;gap:18px}
.num,td,th,.chip,.mval{font-variant-numeric:tabular-nums}.pos{color:var(--green)}.neg{color:var(--red)}.warnc{color:var(--gold)}.side{color:var(--side)}.mut{color:var(--muted)}
.c-elite{color:#4ADE80}.c-good{color:#7BDC5A}.c-mid{color:#FBBF24}.c-weak{color:#FB923C}.c-poor{color:#F87171}.c-na{color:var(--muted)}
/* header */
.hd{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;border-bottom:1px solid var(--border);padding-bottom:14px;flex-wrap:wrap}
.hd h1{font-family:var(--display);font-weight:800;font-size:34px;letter-spacing:-.02em;margin:0;line-height:1}
.hd .sp{color:var(--ink2);font-size:13px;margin-top:6px}.hd .sp b{color:var(--ink)}
.hd .meta{color:var(--muted-2);font-size:11px;text-align:right;line-height:1.5}.fresh{color:var(--green);font-weight:700}
/* strip chips */
.strip{display:grid;grid-template-columns:repeat(8,1fr);gap:9px}
@media(max-width:880px){.strip{grid-template-columns:repeat(4,1fr)}}
.chipc{background:var(--raised);border:1px solid var(--border);border-radius:11px;padding:9px 10px;text-align:center}
.chipc .k{color:var(--muted);font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.chipc .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:19px;margin-top:3px}
/* section */
.sec{border:1px solid var(--border-2);border-radius:14px;background:var(--card);overflow:hidden;position:relative}
.sec::before{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:var(--v-grad);opacity:.6}
.sec h2{font-family:var(--display);font-weight:800;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--v-light);margin:0;padding:13px 16px 0}
.sec .body{padding:12px 16px 16px}
/* tables */
table{width:100%;border-collapse:collapse}
th{color:var(--ink2);font-size:11px;letter-spacing:.05em;text-transform:uppercase;font-weight:800;text-align:right;padding:9px 12px;border-bottom:1px solid var(--border-2);white-space:nowrap}
th:first-child{text-align:left}
td{padding:9px 12px;text-align:right;border-bottom:1px solid rgba(255,255,255,.06);font-size:14px}
td:first-child{text-align:left;font-weight:600}tbody tr:last-child td{border-bottom:none}tbody tr:hover td{background:rgba(124,77,255,.08)}
.chip{font-family:var(--display);font-weight:800}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:10.5px;font-weight:800;letter-spacing:.04em;border:1px solid transparent}
.pill.pos{background:rgba(60,203,127,.13);color:#7BDC5A;border-color:rgba(60,203,127,.22)}
.pill.warnc{background:rgba(232,194,74,.12);color:var(--gold);border-color:rgba(232,194,74,.22)}
.pill.neg{background:rgba(242,84,91,.12);color:#FCA5A5;border-color:rgba(242,84,91,.22)}
.pill.mut{background:rgba(255,255,255,.06);color:var(--ink2)}
/* comparison + driver bars */
.dbar{display:inline-block;width:64px;height:7px;border-radius:4px;background:rgba(255,255,255,.07);vertical-align:middle;overflow:hidden}
.dbar i{display:block;height:100%;border-radius:4px}
.advbar{display:flex;align-items:center;gap:8px;justify-content:flex-end}
.advbar .seg{height:8px;border-radius:3px}.advbar .a{background:#9A6BFF}.advbar .h{background:#2dd4bf}
/* charts */
.charts{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:880px){.charts{grid-template-columns:1fr}}
.cap{display:flex;justify-content:space-between;font-size:11px;font-weight:700;margin-top:3px}
/* drawer */
details{border-top:1px solid var(--border);padding:12px 16px}summary{cursor:pointer;color:var(--ink2);font-weight:700;font-size:13px;list-style:none}
summary::before{content:"▸ ";color:var(--accent)}details[open] summary::before{content:"▾ "}
details ul{margin:8px 0 0;padding-left:18px}details li{font-size:12.5px;color:var(--muted);margin:4px 0}
"""


def _td_signed(v, suffix="", good_pos=True):
    if v is None:
        return '<td class="mut">—</td>'
    tone = "pos" if (v > 0) == good_pos else "neg"
    if v == 0:
        tone = "mut"
    return f'<td class="{tone}">{v:+g}{suffix}</td>'


def render_html(r):
    gd, p, e = r["gd"], r["probs"], html.escape
    sd_t = r["anchors"]["team_sd"]
    w = gd.weather or {}
    wx = "Dome" if w.get("dome") else f"{w.get('temp_f','?')}°F · {w.get('wind_mph','?')}mph"

    # projection strip
    best_edge = max((m["edge"] for m in r["markets"] if m["edge"] is not None), default=None)
    strip = [
        ("Win %", f'<span class="pos">{p.p_home_win*100:.0f}</span>/<span class="side">{p.p_away_win*100:.0f}</span>'),
        ("Proj score", f'{e(gd.home)} {p.exp_home_runs:.1f}–{p.exp_away_runs:.1f}'),
        ("Proj total", f'{p.exp_total:.1f}'),
        ("Fair total", f'{p.exp_total:.1f}'),
        ("Fair ML (H)", f'{BE.prob_to_american(p.p_home_win):+d}'),
        ("F5 (≈½)", f'{p.exp_total/2:.1f}'),
        ("Margin", f'{p.exp_margin:+.2f}'),
        ("Best edge", (f'<span class="{"pos" if best_edge and best_edge>0 else "mut"}">{best_edge:+.1f}pt</span>' if best_edge is not None else "—")),
    ]
    strip_html = "".join(f'<div class=chipc><div class=k>{e(k)}</div><div class=v>{v}</div></div>' for k, v in strip)

    # market grid
    def mrow(m):
        return (f'<tr><td>{e(m["label"])}</td>'
                f'<td>{(f"{m['mkt']:+d}") if m["mkt"] is not None else "—"}</td>'
                f'<td>{m["fair"]:+d}</td>'
                f'<td>{(f"{m['impl']}%") if m["impl"] is not None else "—"}</td>'
                f'<td>{m["model"]}%</td>'
                f'{_td_signed(m["edge"], "pt")}'
                f'{_td_signed(m["ev"], "")}'
                f'<td>{m["max"]:+d}</td>'
                f'<td><span class="pill {m["tone"]}">{m["state"]}</span></td></tr>')
    mrows = "".join(mrow(m) for m in r["markets"])

    # advantage matrix
    def arow(a):
        ac, al = _chip(a["a_pct"]); hc, hl = _chip(a["h_pct"])
        aw = (a["a_pct"] or 0); hw = (a["h_pct"] or 0)
        bar = (f'<div class=advbar><span class="seg a" style="width:{aw*0.6:.0f}px"></span>'
               f'<span class="seg h" style="width:{hw*0.6:.0f}px"></span></div>')
        edge = e(str(a["edge"]))
        return (f'<tr><td>{e(a["cat"])}</td>'
                f'<td class=side>{_f(a["a_val"])} <span class="chip {ac}">{al}</span></td>'
                f'<td>{bar}</td>'
                f'<td class=pos>{_f(a["h_val"])} <span class="chip {hc}">{hl}</span></td>'
                f'<td>{edge}</td><td class=mut>{e(str(a["impact"]))}</td></tr>')
    arows = "".join(arow(a) for a in r["advantage"])

    # key drivers (ranked contribution bars)
    def drow(f_):
        tone = "pos" if f_["pct"] > 0 else "neg"
        return (f'<tr><td>{e(f_["name"])}</td>'
                f'<td>{_bar(f_["pct"], tone)} <span class="{tone}">{f_["pct"]:+.1f}%</span></td>'
                f'<td class=mut>{e(f_["runs"])} runs</td><td>{e(f_["conf"])}</td>'
                f'<td class=mut>{e(f_["market"])}</td><td>{e(f_["priced"])}</td></tr>')
    drows = "".join(drow(f_) for f_ in r["factors"])

    sharp = (r["sharp"] and "".join(
        f'<tr><td>{e(s["market_type"])}</td><td>{e(str(s["selection"]))}</td>'
        f'{_td_signed(round(float(s.get("divergence") or 0)*100,1),"pt")}'
        f'<td>{"STEAM" if s.get("steam_flag") else "—"}</td></tr>' for s in r["sharp"])) \
        or '<tr><td class=mut colspan=4>No sharp signal recorded.</td></tr>'
    risks = "".join(f"<li>{e(x)}</li>" for x in r["risks"]) or "<li>None flagged.</li>"

    return f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{e(r['away'])}@{e(r['home'])} — MLB Model</title><style>{_CSS}</style></head><body><div class=wrap>
 <div class=hd>
   <div><h1>{e(r['away'])} <span class=mut style="font:inherit">@</span> {e(r['home'])}</h1>
     <div class=sp><b>{e(gd.away_sp)}</b> {e(gd.away_hand)}HP · FIP {gd.away_fip} &nbsp;vs&nbsp;
       <b>{e(gd.home_sp)}</b> {e(gd.home_hand)}HP · FIP {gd.home_fip} &nbsp;·&nbsp; {e(gd.home)} park {gd.park_factor} · {e(wx)}</div></div>
   <div class=meta><span class=fresh>● live model</span><br>model {e(r['model_version'])} · metrics {e(r['metric_version'])}<br>{e(r['generated'][:16])}Z · pk {r['game_pk']}</div>
 </div>

 <div class=strip>{strip_html}</div>

 <div class=charts>
   <div class=sec><h2>Win probability</h2><div class=body>{_svg_winprob(p.p_home_win,p.p_away_win,e(r['home']),e(r['away']))}</div></div>
   <div class=sec><h2>Expected-run distribution</h2><div class=body>{_svg_rundist(p.exp_away_runs,p.exp_home_runs,sd_t,e(r['away']),e(r['home']))}</div></div>
 </div>

 <div class=sec><h2>Market grid · fair vs available (net of vig) · max entry = break-even</h2><div class=body>
   <table><tr><th>Market</th><th>Mkt</th><th>Fair</th><th>Impl</th><th>Model</th><th>Edge</th><th>EV/u</th><th>Max</th><th>State</th></tr>{mrows}</table>
 </div></div>

 <div class=sec><h2>Matchup advantage matrix · raw · percentile · modeled impact</h2><div class=body>
   <table><tr><th>Category</th><th>{e(r['away'])}</th><th>vs</th><th>{e(r['home'])}</th><th>Edge</th><th>Impact</th></tr>{arows}</table>
 </div></div>

 <div class=sec><h2>Key drivers · ranked contribution to expected runs</h2><div class=body>
   <table><tr><th>Factor</th><th>Effect</th><th>Axis</th><th>Conf</th><th>Markets</th><th>Priced?</th></tr>{drows}</table>
 </div></div>

 <div class=sec><h2>Sharp money &amp; line movement</h2><div class=body>
   <table><tr><th>Market</th><th>Side</th><th>Divergence</th><th>Steam</th></tr>{sharp}</table></div></div>

 <div class=sec><details open><summary>Risks &amp; counter-signals</summary><ul>{risks}</ul></details>
   <details><summary>Methodology &amp; audit</summary><ul>
     <li>Expected-runs model (OSI·FIP·park·bullpen, regressed); anchors from settled finals: league {r['anchors']['league_runs']}, home-win {r['anchors']['home_winp']}, margin SD {r['anchors']['margin_sd']}.</li>
     <li>Percentiles empirical from MLBMA pipeline sp_profiles / team_profiles. Sharp from warehouse sharp_signals (de-vig + steam).</li>
     <li>Uncalibrated prior; no validated OOS edge clears the promotion gate; OSI is a team proxy; weather not yet in the runs model.</li></ul></details></div>
</div></body></html>"""


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Matchup Intelligence Report (terminal).")
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", default="matchup_report.html")
    args = ap.parse_args()
    away, home = (s.strip().upper() for s in args.game.split("@", 1))
    r = build_report(away, home)
    open(args.out, "w", encoding="utf-8").write(render_html(r))
    print(f"wrote {args.out}  ({r['away']}@{r['home']})")


if __name__ == "__main__":
    main()
