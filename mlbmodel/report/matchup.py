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

try:
    import market_data as MD  # live odds (best price per side) — analytical inheritance
except Exception:  # pragma: no cover
    MD = None


def _live_odds(away, home, fetch=True):
    """Populate {(market,side): american_odds} + the posted total line from live/cached odds.
    Without this the market grid is empty (the failure that prompted this fix)."""
    om, line = {}, None
    if MD is None:
        return om, line
    try:
        if fetch:
            MD.fetch_game(away, home)
    except (SystemExit, Exception):  # never let an odds hiccup break the report
        pass
    for team in (home, away):
        bp = MD.best_price(away, home, "ml", team, None)
        if bp:
            om[("ml", team)] = bp["odds"]
    try:
        import pandas as pd
        df = MD._load_latest()
        if df is not None:
            t = df[(df["away"].astype(str).str.upper() == away)
                   & (df["home"].astype(str).str.upper() == home)
                   & (df["market"].astype(str) == "total")]
            ln = pd.to_numeric(t["line"], errors="coerce").dropna() if len(t) else None
            if ln is not None and len(ln):
                line = float(ln.mode().iloc[0])
    except Exception:
        pass
    if line is not None:
        for s in ("over", "under"):
            bp = MD.best_price(away, home, "total", s, line)
            if bp:
                om[("total", s)] = bp["odds"]
    return om, line


# ── visual identity: official MLB team logos + pitcher headshots (CDN) ───────
_MLB_ID = {"ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112, "CHW": 145,
           "CIN": 113, "CLE": 114, "COL": 115, "DET": 116, "HOU": 117, "KCR": 118,
           "LAA": 108, "LAD": 119, "MIA": 146, "MIL": 158, "MIN": 142, "NYM": 121,
           "NYY": 147, "ATH": 133, "PHI": 143, "PIT": 134, "SDP": 135, "SFG": 137,
           "SEA": 136, "STL": 138, "TBR": 139, "TEX": 140, "TOR": 141, "WSN": 120}


def _logo(abbr, cls="tlogo"):
    a = str(abbr).upper().strip()
    i = _MLB_ID.get(a)
    if not i:
        return f'<span class="tlf {cls}">{html.escape(a)}</span>'
    return (f'<img class="{cls}" src="https://www.mlbstatic.com/team-logos/{i}.svg" '
            f'alt="{html.escape(a)}" loading="lazy" '
            f'onerror="this.outerHTML=&quot;<span class=\'tlf {cls}\'>{html.escape(a)}</span>&quot;">')


def _headshot(pid):
    if not pid:
        return '<span class="phead phead-na"></span>'
    return (f'<img class=phead loading="lazy" alt="" '
            f'src="https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/'
            f'w_120,q_auto:best/v1/people/{int(pid)}/headshot/67/current" '
            f'onerror="this.classList.add(&quot;phead-na&quot;)">')


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


_DEF = {
    "FIP": "Fielding-Independent Pitching — ERA from what a pitcher controls (K/BB/HR). Lower is better.",
    "K%": "Strikeout rate. Higher = more swings-and-misses, fewer balls in play.",
    "HR/9": "Home runs allowed per 9 innings. Lower is better.",
    "OSI": "Offense Strength Index (50 = league average). Higher = stronger lineup.",
    "wOBA": "Weighted On-Base Average — overall offensive value. Higher is better (~.320 avg).",
    "OBR": "Baserunning index (50 = average). Higher = better baserunning.",
    "Bullpen": "Relief run-prevention. Lower factor / ERA is better.",
    "Park": "Park run environment (1.00 = neutral; >1 boosts scoring).",
}


def _cat_def(cat):
    for k, v in _DEF.items():
        if k in cat:
            return v
    return ""


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


# ── advantage matrix (team vs team, with empirical percentiles + rank) ────────
def _rank(pct, n):
    """Rank (1 = best) implied by a percentile within n peers."""
    if pct is None or not n:
        return None
    return max(1, round((100 - pct) / 100 * n) + 1)


def _col(df, name):
    return df[name] if df is not None and name in df.columns else None


def _tv(idx, team, col):
    import pandas as pd
    r = idx.get(str(team).upper().strip())
    if r is None or col not in r:
        return None
    v = pd.to_numeric(r[col], errors="coerce")
    return None if pd.isna(v) else float(v)


def _advantage(gd, anchors):
    import pandas as pd
    sp = BE.load("sp_profiles.csv")
    tp = BE.load("team_profiles.csv")
    fip_s, k_s, hr_s = _col(sp, "FIP"), _col(sp, "K_pct"), _col(sp, "HR9")
    osi_s = _col(tp, "osi")
    idx = {str(r["team"]).upper().strip(): r for _, r in tp.iterrows()} if tp is not None and "team" in tp.columns else {}
    # pooled series for split-based baselines
    plat_s = pd.concat([s for s in (_col(tp, "osi_vs_lhp"), _col(tp, "osi_vs_rhp")) if s is not None]) if tp is not None else None
    woba_s = pd.concat([s for s in (_col(tp, "home_woba"), _col(tp, "away_woba")) if s is not None]) if tp is not None else None
    obr_s = _col(tp, "obr")
    bhl_s = _col(tp, "bullpen_high_lev_era")
    a_plat_col = "osi_vs_lhp" if gd.home_hand == "L" else "osi_vs_rhp"   # away faces home SP hand
    h_plat_col = "osi_vs_lhp" if gd.away_hand == "L" else "osi_vs_rhp"   # home faces away SP hand

    def _mean(series, default):
        try:
            import pandas as pd
            s = pd.to_numeric(series, errors="coerce").dropna()
            return (round(float(s.mean()), 2), int(s.shape[0])) if len(s) else (default, 0)
        except Exception:
            return (default, 0)

    rows = []

    def row(cat, a_val, h_val, series, lower_better, base_default, impact, unit=""):
        ap = _emp_pctile(series, a_val, lower_better) if series is not None else None
        hp = _emp_pctile(series, h_val, lower_better) if series is not None else None
        base, n = _mean(series, base_default) if series is not None else (base_default, None)
        edge = "—"
        if ap is not None and hp is not None:
            edge = gd.away if ap > hp else (gd.home if hp > ap else "even")
        # stat-presentation standard: raw + baseline + delta + percentile + sample
        ad = (round(a_val - base, 2) if isinstance(a_val, (int, float)) and base is not None else None)
        hd = (round(h_val - base, 2) if isinstance(h_val, (int, float)) and base is not None else None)
        rows.append({"cat": cat, "a_val": a_val, "h_val": h_val, "a_pct": ap, "h_pct": hp,
                     "base": base, "a_d": ad, "h_d": hd, "n": n, "edge": edge,
                     "a_rank": _rank(ap, n), "h_rank": _rank(hp, n),
                     "impact": impact, "unit": unit, "lower_better": lower_better})

    # pitching
    row("Starting pitching (FIP)", gd.away_fip, gd.home_fip, fip_s, True, config.LEAGUE_FIP,
        f"{(BE.pitch_factor(gd.home_fip, gd.home_pen_factor) - BE.pitch_factor(gd.away_fip, gd.away_pen_factor)) * anchors['league_runs']:+.2f} R")
    row("SP strikeout (K%)", gd.away_k, gd.home_k, k_s, False, 22.0, "K props · Total", "%")
    row("SP home-run risk (HR/9)", gd.away_hr9, gd.home_hr9, hr_s, True, 1.25, "Total · TT")
    # offense
    row("Offense (OSI)", gd.away_osi, gd.home_osi, osi_s, False, 50.0,
        f"{(BE.offense_factor(gd.away_osi) - BE.offense_factor(gd.home_osi)) * anchors['league_runs']:+.2f} R")
    row(f"Platoon (OSI vs {gd.home_hand}HP/{gd.away_hand}HP)", _tv(idx, gd.away, a_plat_col), _tv(idx, gd.home, h_plat_col),
        plat_s, False, 50.0, "Total · ML")
    row("Lineup quality (wOBA)", _tv(idx, gd.away, "away_woba"), _tv(idx, gd.home, "home_woba"), woba_s, False, 0.320, "Total · ML")
    row("Baserunning (OBR)", _tv(idx, gd.away, "obr"), _tv(idx, gd.home, "obr"), obr_s, False, 50.0, "ML · close games")
    # relief + environment
    row("Bullpen (factor)", gd.away_pen_factor, gd.home_pen_factor, None, True, 1.00, "Late ML · Total")
    row("Bullpen high-leverage (ERA)", _tv(idx, gd.away, "bullpen_high_lev_era"), _tv(idx, gd.home, "bullpen_high_lev_era"),
        bhl_s, True, 4.00, "Late ML · live")
    row("Park run env", gd.park_factor, gd.park_factor, None, False, 1.00, "Total · TT")
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


def _norm(s):
    import re
    t = " ".join(reversed(str(s).lower().split(","))) if "," in str(s) else str(s).lower()
    return " ".join(sorted(re.sub(r"[^a-z ]", "", t).split()))


def _numf(v):
    import pandas as pd
    x = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(x) else float(x)


def _extras(away, home, gd, probs, anchors):
    """Start time, lineup status, SP arsenals, scenario sweep, F5 — from real pipeline data."""
    out = {"start": None, "lineup": "lineups TBD · probables confirmed",
           "arsenal_a": [], "arsenal_h": [], "scenario": [], "f5": None}
    m = BE.load("today_matchups.csv")
    if m is not None and "Away" in m.columns:
        m["Away"] = m["Away"].astype(str).str.upper().str.strip()
        m["Home"] = m["Home"].astype(str).str.upper().str.strip()
        r = m[(m["Away"] == away) & (m["Home"] == home)]
        if not r.empty:
            out["start"] = str(r.iloc[0].get("Time", "") or "")
    ln = BE.load("today_lineups.csv")
    if ln is not None and not ln.empty:
        out["lineup"] = "lineups posted"
    pm = BE.load("pitch_mix_pitcher.csv")

    def arsenal(name):
        if pm is None or "full_name" not in pm.columns:
            return []
        key = _norm(name)
        sub = pm[pm["full_name"].astype(str).map(_norm) == key]
        rows = [{"pitch": str(x.get("pitch_type", "")), "pct": _numf(x.get("pitch_pct")),
                 "whiff": _numf(x.get("whiff_rate"))} for _, x in sub.iterrows()]
        return sorted([z for z in rows if z["pct"]], key=lambda z: -z["pct"])[:6]
    out["arsenal_a"], out["arsenal_h"] = arsenal(gd.away_sp), arsenal(gd.home_sp)
    spp = BE.load("sp_profiles.csv")

    def spid(name):
        if spp is None or "pitcher_name" not in spp.columns or "pitcher_id" not in spp.columns:
            return None
        m = spp[spp["pitcher_name"].astype(str).map(_norm) == _norm(name)]
        if not m.empty:
            v = _numf(m.iloc[0]["pitcher_id"])
            return int(v) if v else None
        return None
    out["a_id"], out["h_id"] = spid(gd.away_sp), spid(gd.home_sp)
    for d in (-1.5, -1, -0.5, 0, 0.5, 1, 1.5):
        line = round((probs.exp_total + d) * 2) / 2
        po = 1 - BE.normal_cdf((line - probs.exp_total) / anchors["total_sd"])
        out["scenario"].append((line, round(po * 100, 1)))
    f5, sdf = probs.exp_total * 0.54, anchors["total_sd"] * 0.74
    line = round(f5 * 2) / 2
    po = BE.clip(1 - BE.normal_cdf((line - f5) / sdf), 0.02, 0.98)
    out["f5"] = {"exp": round(f5, 1), "line": line, "over": round(po * 100, 1), "fair": BE.prob_to_american(po)}
    return out


def build_report(away, home, *, odds_map=None, fetch=True):
    anchors = BE.refresh_anchors()
    gd = BE.load_game(away, home)
    probs = BE.model_probabilities(gd, anchors)
    if odds_map is None:
        odds_map, posted_total = _live_odds(away, home, fetch=fetch)
    else:
        posted_total = None
    tline = posted_total if posted_total is not None else round(probs.exp_total * 2) / 2
    markets = [
        _market_row("ml", gd.home, None, None, gd, probs, anchors, odds_map.get(("ml", gd.home))),
        _market_row("ml", gd.away, None, None, gd, probs, anchors, odds_map.get(("ml", gd.away))),
        _market_row("total", "over", tline, None, gd, probs, anchors, odds_map.get(("total", "over"))),
        _market_row("total", "under", tline, None, gd, probs, anchors, odds_map.get(("total", "under"))),
        _market_row("runline", gd.home if probs.exp_margin > 0 else gd.away, -1.5, None, gd, probs, anchors, None),
    ]
    ex = _extras(away, home, gd, probs, anchors)
    f5 = ex["f5"]
    markets.append({"label": f"F5 Over {f5['line']} (≈)", "model": f5["over"], "fair": f5["fair"],
                    "mkt": None, "impl": None, "edge": None, "ev": None, "max": f5["fair"],
                    "state": "NO-EDGE", "tone": "mut"})
    # line movement (best-effort, open->current for home ML)
    mv = None
    try:
        if MD is not None:
            mv = MD.line_movement(away, home, "ml", gd.home, None)
    except Exception:
        mv = None
    gpk = zlib.crc32(f"{date.today().isoformat()}|{away}|{home}".encode())
    # model confidence: capped (uncalibrated prior) by data completeness + edge size
    have = sum(1 for v in (gd.away_osi, gd.home_osi, gd.away_fip, gd.home_fip) if v is not None)
    conf = "low" if have < 3 else ("high" if (max((abs(m["edge"]) for m in markets if m["edge"] is not None), default=0) >= 4) else "med")
    return {"away": away, "home": home, "gd": gd, "probs": probs, "anchors": anchors,
            "posted_total": posted_total, "extras": ex, "movement": mv, "confidence": conf,
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


def _svg_mktmodel(markets):
    """Model% vs market-implied% per market — the discrepancy at a glance."""
    rows = [m for m in markets if m["impl"] is not None][:4]
    if not rows:
        return '<div class=mut style="font-size:12px">No market prices to compare.</div>'
    out = ""
    for m in rows:
        edge = m["edge"] or 0
        tone = "pos" if edge > 0 else ("neg" if edge < 0 else "mut")
        out += (f'<div class=mm><span class=mml>{html.escape(m["label"])}</span>'
                f'<span class=mmbar><i class=mod style="width:{m["model"]:.0f}%"></i>'
                f'<i class=imp style="left:{m["impl"]:.0f}%"></i></span>'
                f'<span class="mmv {tone}">{edge:+.1f}pt</span></div>')
    return f'<div class=mmwrap>{out}<div class=cap><span class=side>model bar</span><span class=mut>● market</span></div></div>'


def _svg_arsenal(ars, label):
    if not ars:
        return f'<div class=mut style="font-size:11.5px">{label}: no pitch-mix data</div>'
    bars = "".join(
        f'<div class=arl><span class=apt>{html.escape(p["pitch"])}</span>'
        f'<span class=abar><i style="width:{min(100,p["pct"]):.0f}%"></i></span>'
        f'<span class=apv>{p["pct"]:.0f}%</span><span class=aw>whf {(p["whiff"] or 0):.0f}</span></div>'
        for p in ars)
    return f'<div class=arshd>{label}</div><div class=ars>{bars}</div>'


def _svg_scenario(scenario, mkt):
    if not scenario:
        return ""
    lines = [s[0] for s in scenario]
    lo, hi = min(lines), max(lines)
    pts = []
    for ln, ov in scenario:
        x = (ln - lo) / (hi - lo) * 260 + 10 if hi > lo else 135
        pts.append(f"{x:.0f},{70 - ov/100*60:.0f}")
    mk = ""
    if mkt is not None and lo <= mkt <= hi:
        x = (mkt - lo) / (hi - lo) * 260 + 10
        mk = f'<line x1="{x:.0f}" y1="2" x2="{x:.0f}" y2="72" stroke="#E8C24A" stroke-dasharray="3"/><text x="{x:.0f}" y="84" fill="#E8C24A" font-size="9" text-anchor="middle">mkt {mkt}</text>'
    labs = "".join(f'<text x="{(s[0]-lo)/(hi-lo)*260+10 if hi>lo else 135:.0f}" y="84" fill="#707687" font-size="8" text-anchor="middle">{s[0]:g}</text>' for s in scenario)
    return (f'<svg viewBox="0 0 290 90" width="100%" height="92">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="#9A6BFF" stroke-width="2"/>{mk}{labs}</svg>'
            f'<div class=cap><span class=side>fair Over% vs total line</span></div>')


def _svg_movement(mv):
    if not mv or mv.get("snapshots", 0) < 2:
        return '<div class=mut style="font-size:11.5px">Line movement: single snapshot — re-fetch over time to build a timeline.</div>'
    o, c = mv.get("open"), mv.get("current")
    d = mv.get("delta", 0)
    tone = "pos" if d and d > 0 else "neg"
    return (f'<div class=mvrow><span class=mut>open</span><b>{o:+d}</b>'
            f'<span class=mvarrow>→</span><b>{c:+d}</b>'
            f'<span class="{tone}">Δ{d:+d} · {mv["snapshots"]} snaps</span></div>')


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
/* logos + headshots (Chase Analytics blueprint) */
.tlogo{height:26px;width:26px;object-fit:contain;vertical-align:middle;filter:drop-shadow(0 3px 5px rgba(0,0,0,.5))}
.tlogo.lg{height:40px;width:40px}.tlogo.sm{height:18px;width:18px}
.tlf{display:inline-flex;align-items:center;justify-content:center;height:26px;width:26px;border-radius:50%;
background:var(--raised);border:1px solid var(--border-2);color:var(--ink2);font:800 9px/1 var(--display);vertical-align:middle}
.tlf.lg{height:40px;width:40px;font-size:12px}.tlf.sm{height:18px;width:18px;font-size:7px}
.teams{display:flex;align-items:center;gap:11px}
.pitchers{display:flex;align-items:center;gap:14px;margin:11px 0 4px;flex-wrap:wrap}
.pcell{display:flex;align-items:center;gap:9px}
.phead{width:42px;height:42px;border-radius:50%;object-fit:cover;object-position:center top;background:var(--raised);
border:2px solid #454B61;box-shadow:0 5px 14px rgba(0,0,0,.45),0 0 0 2px rgba(154,107,255,.12)}
.phead-na{background:linear-gradient(160deg,var(--raised),var(--card))}.phead-na::after{content:"";display:block}
.pmeta{line-height:1.3}.pmeta b{color:var(--ink);font-size:14px}.pmeta span{display:block;color:var(--muted);font-size:11.5px}
.vsx{color:var(--muted-2);font:700 11px var(--display);text-transform:uppercase}
/* strip chips */
.strip{display:grid;grid-template-columns:repeat(8,1fr);gap:9px}
@media(max-width:880px){.strip{grid-template-columns:repeat(4,1fr)}}
.chipc{background:var(--raised);border:1px solid var(--border);border-radius:11px;padding:9px 10px;text-align:center}
.chipc .k{color:var(--muted);font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.chipc .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:19px;margin-top:3px}
.vbar{display:flex;align-items:center;gap:14px;padding:11px 16px;border-radius:12px;border:1px solid var(--border-2);font-size:13.5px;background:var(--card)}
.vbar b{font-family:var(--display);font-weight:800;font-size:15px;letter-spacing:.03em}.vbar span{color:var(--ink2)}
.vbar.pos{border-color:rgba(60,203,127,.3);background:rgba(60,203,127,.10)}.vbar.pos b{color:#7BDC5A}
.vbar.warnc{border-color:rgba(232,194,74,.3);background:rgba(232,194,74,.10)}.vbar.warnc b{color:var(--gold)}
.vbar.neg{border-color:rgba(242,84,91,.3);background:rgba(242,84,91,.10)}.vbar.neg b{color:#FCA5A5}
.vbar.mut b{color:var(--muted)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start;margin-top:14px}@media(max-width:760px){.cols{grid-template-columns:1fr}}
.note{color:var(--muted);font-size:11.5px;margin-top:8px}
.rti{position:absolute;width:0;height:0;opacity:0}.rtabs{margin-top:20px}
.rtabbar{display:flex;gap:2px;border-bottom:1px solid var(--border);flex-wrap:wrap;margin-bottom:14px}
.rtabbar label{padding:9px 16px;font:700 13.5px var(--sans);color:var(--muted);cursor:pointer;border-bottom:2.5px solid transparent;margin-bottom:-1px}
.rtabbar label:hover{color:var(--ink2)}.pn{display:none}
#rt-markets:checked~.rpanels #pn-markets,#rt-charts:checked~.rpanels #pn-charts,#rt-matchup:checked~.rpanels #pn-matchup,#rt-drivers:checked~.rpanels #pn-drivers,#rt-sharp:checked~.rpanels #pn-sharp{display:block}
#rt-markets:checked~.rtabbar label[for=rt-markets],#rt-charts:checked~.rtabbar label[for=rt-charts],#rt-matchup:checked~.rtabbar label[for=rt-matchup],#rt-drivers:checked~.rtabbar label[for=rt-drivers],#rt-sharp:checked~.rtabbar label[for=rt-sharp]{color:var(--ink);border-bottom-color:var(--accent)}
th[title],td[title]{cursor:help;text-decoration:underline dotted rgba(148,163,184,.4);text-underline-offset:3px}
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
.delta{font-size:11px;font-weight:700}.n{color:var(--muted-2);font-size:10px;font-weight:600}
/* market-vs-model bars */
.mmwrap{display:flex;flex-direction:column;gap:7px}.mm{display:flex;align-items:center;gap:9px}
.mml{flex:0 0 96px;font-size:12px;color:var(--ink2)}.mmbar{position:relative;flex:1;height:12px;background:rgba(255,255,255,.06);border-radius:4px}
.mmbar i.mod{position:absolute;left:0;top:0;height:100%;background:var(--teal);border-radius:4px;opacity:.55}
.mmbar i.imp{position:absolute;top:-2px;width:2px;height:16px;background:#fff}.mmv{flex:0 0 46px;text-align:right;font-weight:700;font-size:12px}
/* arsenal */
.arshd{font-size:11px;color:var(--ink2);font-weight:700;margin:2px 0 6px}.ars{display:flex;flex-direction:column;gap:5px}
.arl{display:flex;align-items:center;gap:8px;font-size:11.5px}.apt{flex:0 0 34px;color:var(--muted);font-weight:700}
.abar{flex:1;height:8px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden}.abar i{display:block;height:100%;background:var(--accent);border-radius:3px}
.apv{flex:0 0 32px;text-align:right;font-weight:700}.aw{flex:0 0 50px;text-align:right;color:var(--muted-2);font-size:10px}
.mvrow{display:flex;align-items:center;gap:9px;font-size:13px}.mvrow b{font-family:var(--display)}.mvarrow{color:var(--muted)}
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


def report_body(r):
    """Inner report content (no <html>/<style> wrapper) so the app shell can embed it."""
    gd, p, e = r["gd"], r["probs"], html.escape
    sd_t = r["anchors"]["team_sd"]
    w = gd.weather or {}
    wx = ("Dome" if w.get("dome")
          else f"{w['temp_f']:.0f}°F · {w.get('wind_mph', 0):.0f}mph" if w.get("temp_f") is not None
          else "weather n/a")

    # projection strip
    best_edge = max((m["edge"] for m in r["markets"] if m["edge"] is not None), default=None)
    strip = [
        ("Win %", f'<span class="pos">{p.p_home_win*100:.0f}</span>/<span class="side">{p.p_away_win*100:.0f}</span>'),
        ("Proj score", f'{e(gd.home)} {p.exp_home_runs:.1f}–{p.exp_away_runs:.1f}'),
        ("Proj total", f'{p.exp_total:.1f}'),
        ("Mkt total", (f'{r["posted_total"]:.1f}' if r.get("posted_total") else '—')),
        ("Fair ML (H)", f'{BE.prob_to_american(p.p_home_win):+d}'),
        ("F5 Over", f'{r["extras"]["f5"]["over"]:.0f}%'),
        ("Best edge", (f'<span class="{"pos" if best_edge and best_edge>0 else "mut"}">{best_edge:+.1f}pt</span>' if best_edge is not None else "—")),
        ("Confidence", f'<span class="{"warnc" if r["confidence"]!="high" else "pos"}">{r["confidence"]}</span>'),
    ]
    strip_html = "".join(f'<div class=chipc><div class=k>{e(k)}</div><div class=v>{v}</div></div>' for k, v in strip)

    # market grid
    def mrow(m):
        mkt = f'{m["mkt"]:+d}' if m["mkt"] is not None else "—"
        impl = f'{m["impl"]}%' if m["impl"] is not None else "—"
        return (f'<tr><td>{e(m["label"])}</td>'
                f'<td>{mkt}</td>'
                f'<td>{m["fair"]:+d}</td>'
                f'<td>{impl}</td>'
                f'<td>{m["model"]}%</td>'
                f'{_td_signed(m["edge"], "pt")}'
                f'{_td_signed(m["ev"], "")}'
                f'<td>{m["max"]:+d}</td>'
                f'<td><span class="pill {m["tone"]}">{m["state"]}</span></td></tr>')
    mrows = "".join(mrow(m) for m in r["markets"])

    # advantage matrix
    def _delta(d, lower_better):
        if d is None:
            return ""
        good = (d < 0) if lower_better else (d > 0)
        tone = "pos" if good else ("neg" if d != 0 else "mut")
        return f' <span class="delta {tone}">{d:+g}</span>'

    def arow(a):
        ac, al = _chip(a["a_pct"])
        hc, hl = _chip(a["h_pct"])
        u, lb = a["unit"], a["lower_better"]
        ar = f' <span class=n>#{a["a_rank"]}</span>' if a.get("a_rank") else ''
        hr = f' <span class=n>#{a["h_rank"]}</span>' if a.get("h_rank") else ''
        # stat-presentation standard: raw + Δ-vs-baseline + percentile chip + rank, per team
        av = f'{_f(a["a_val"])}{u}{_delta(a["a_d"], lb)} <span class="chip {ac}">{al}</span>{ar}'
        hv = f'{_f(a["h_val"])}{u}{_delta(a["h_d"], lb)} <span class="chip {hc}">{hl}</span>{hr}'
        n = f' <span class=n>n={a["n"]}</span>' if a.get("n") else ''
        return (f'<tr><td title="{e(_cat_def(a["cat"]))}">{e(a["cat"])}{n}</td>'
                f'<td class=side>{av}</td><td class=pos>{hv}</td>'
                f'<td class=mut>{_f(a["base"])}{u}</td>'
                f'<td>{e(str(a["edge"]))}</td><td class=mut>{e(str(a["impact"]))}</td></tr>')
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
    def _risk_kind(x):
        xl = x.lower()
        if "hr-prone" in xl or "shaky" in xl or "blown" in xl:
            return ("pen/HR", "neg")
        if "variance" in xl or "babip" in xl or "low-k" in xl:
            return ("variance", "warnc")
        if "wind" in xl or "cold" in xl or "dome" in xl:
            return ("weather", "warnc")
        return ("context", "mut")
    rrows = "".join(f'<tr><td>{e(x)}</td><td><span class="pill {t[1]}">{t[0]}</span></td></tr>'
                    for x in r["risks"] for t in [_risk_kind(x)]) or '<tr><td class=mut colspan=2>None flagged.</td></tr>'

    # top verdict bar — the single most decision-relevant line, above the fold
    op = max((m for m in r["markets"] if m["edge"] is not None), key=lambda m: m["edge"], default=None)
    if op and op["edge"] > 0 and op["state"] in ("BET", "MONITOR"):
        vb = (f'<div class="vbar {op["tone"]}"><b>{op["state"]}</b>'
              f'<span>{e(op["label"])}</span><span>edge {op["edge"]:+.1f}pt</span>'
              f'<span>EV {op["ev"]:+.3f}</span><span>max {op["max"]:+d}</span></div>')
    else:
        vb = '<div class="vbar mut"><b>NO EDGE</b><span>abstain — no market clears the threshold</span></div>'

    # ── Decision layer: the 3 clearest team edges + the 2 biggest risks ──
    adv_edges = [a for a in r["advantage"]
                 if a.get("edge") in (r["away"], r["home"]) and a["a_pct"] is not None and a["h_pct"] is not None]
    adv_edges.sort(key=lambda a: -abs((a["a_pct"] or 0) - (a["h_pct"] or 0)))
    why = "".join(
        f'<tr><td>{e(a["cat"])}</td><td class=side>{e(str(a["edge"]))}</td>'
        f'<td class=mut>{e(str(a["impact"]))}</td></tr>' for a in adv_edges[:3]) \
        or '<tr><td class=mut colspan=3>No decisive edge.</td></tr>'
    rtop = "".join(f'<tr><td>{e(x)}</td></tr>' for x in r["risks"][:2]) or '<tr><td class=mut>None flagged.</td></tr>'
    # incomplete-data flag
    miss = [n for n, v in (("weather", (gd.weather or {}).get("temp_f")),
                           ("lineups", "posted" in r["extras"]["lineup"])) if not v]
    dq = f'<span class="pill warnc" title="default view omits unavailable inputs">incomplete: {", ".join(miss)}</span>' if miss else ''

    return f"""<div class=hd>
   <div style="min-width:0">
     <div class=teams>{_logo(r['away'],'tlogo lg')}<h1>{e(r['away'])} <span class=mut style="font:inherit">@</span> {e(r['home'])}</h1>{_logo(r['home'],'tlogo lg')}</div>
     <div class=pitchers>
       <div class=pcell>{_headshot(r['extras'].get('a_id'))}<div class=pmeta><b>{e(gd.away_sp)}</b><span>{e(gd.away_hand)}HP · FIP {gd.away_fip}</span></div></div>
       <span class=vsx>vs</span>
       <div class=pcell>{_headshot(r['extras'].get('h_id'))}<div class=pmeta><b>{e(gd.home_sp)}</b><span>{e(gd.home_hand)}HP · FIP {gd.home_fip}</span></div></div>
     </div>
     <div class=sp>{e(r['extras']['start'] or 'TBD')} · {e(gd.home)} park {gd.park_factor} · {e(wx)} · {e(r['extras']['lineup'])}</div></div>
   <div class=meta><span class=fresh>● live model</span><br>model {e(r['model_version'])} · metrics {e(r['metric_version'])}<br>{e(r['generated'][:16])}Z · pk {r['game_pk']}</div>
 </div>

 {vb}
 <div class=strip>{strip_html}</div>

 <!-- DECISION LAYER: clearest edges + biggest risks, always visible -->
 <div class=cols>
   <div class=sec><h2>Why {e(r['home'] if p.exp_margin > 0 else r['away'])} <span class=mut>· clearest edges</span></h2><div class=body>
     <table><tr><th>Factor</th><th>Edge</th><th>Affects</th></tr>{why}</table></div></div>
   <div class=sec><h2>Top risks {dq}</h2><div class=body>
     <table><tr><th>Signal</th></tr>{rtop}</table>
     <div class=note>Full evidence in the tabs below; definitions on hover.</div></div></div>
 </div>

 <!-- ANALYSIS LAYER: one tab at a time (not a wall of data) -->
 <div class=rtabs>
   <input class=rti type=radio name=rt id=rt-markets checked>
   <input class=rti type=radio name=rt id=rt-charts>
   <input class=rti type=radio name=rt id=rt-matchup>
   <input class=rti type=radio name=rt id=rt-drivers>
   <input class=rti type=radio name=rt id=rt-sharp>
   <div class=rtabbar>
     <label for=rt-markets>Markets</label><label for=rt-charts>Charts</label>
     <label for=rt-matchup>Matchup</label><label for=rt-drivers>Drivers</label><label for=rt-sharp>Sharp</label>
   </div>
   <div class=rpanels>
     <div id=pn-markets class=pn><div class=sec><div class=body>
       <table><tr><th>Market</th><th title="best available American price">Mkt</th><th title="model fair price">Fair</th><th title="vig-free implied probability">Impl</th><th title="model probability">Model</th><th title="model% minus implied%">Edge</th><th title="expected value per unit, net of vig">EV/u</th><th title="break-even price">Max</th><th>State</th></tr>{mrows}</table>
       <div class=note>Edge = model − implied. Max = worst price still +EV. State: BET / MONITOR / AVOID / NO-EDGE.</div></div></div></div>
     <div id=pn-charts class=pn><div class=charts>
       <div class=sec><h2>Win prob</h2><div class=body>{_svg_winprob(p.p_home_win,p.p_away_win,e(r['home']),e(r['away']))}</div></div>
       <div class=sec><h2>Run distribution</h2><div class=body>{_svg_rundist(p.exp_away_runs,p.exp_home_runs,sd_t,e(r['away']),e(r['home']))}</div></div>
       <div class=sec><h2>Model vs market</h2><div class=body>{_svg_mktmodel(r['markets'])}</div></div>
       <div class=sec><h2>Total sensitivity</h2><div class=body>{_svg_scenario(r['extras']['scenario'], r.get('posted_total'))}</div></div>
       <div class=sec><h2>SP arsenals</h2><div class=body>{_svg_arsenal(r['extras']['arsenal_a'], e(gd.away_sp))}<div style="height:8px"></div>{_svg_arsenal(r['extras']['arsenal_h'], e(gd.home_sp))}</div></div>
       <div class=sec><h2>Line movement</h2><div class=body>{_svg_movement(r['movement'])}</div></div>
     </div></div>
     <div id=pn-matchup class=pn><div class=sec><div class=body>
       <table><tr><th>Category</th><th>{e(r['away'])}</th><th>{e(r['home'])}</th><th title="MLB league average">MLB</th><th>Edge</th><th>Impact</th></tr>{arows}</table>
       <div class=note>raw · Δ vs MLB · percentile chip (elite→poor) · #rank. Hover a category for its definition.</div></div></div></div>
     <div id=pn-drivers class=pn><div class=sec><div class=body>
       <table><tr><th>Factor</th><th title="% change to expected runs">Effect</th><th>Side</th><th>Conf</th><th>Markets</th><th title="already in the market price?">Priced?</th></tr>{drows}</table></div></div></div>
     <div id=pn-sharp class=pn>
       <div class=sec><h2>Sharp money</h2><div class=body>
         <table><tr><th>Market</th><th>Side</th><th title="sharp minus soft de-vig probability">Divergence</th><th>Steam</th></tr>{sharp}</table></div></div>
       <div class=sec><h2>Risks</h2><div class=body>
         <table><tr><th>Signal</th><th>Type</th></tr>{rrows}</table></div></div>
     </div>
   </div>
 </div>

 <div class=sec><details><summary>Methodology &amp; definitions</summary><ul>
   <li><b>Model</b> = expected-runs prior (offense OSI × opposing SP FIP × park × bullpen, regressed to mean); anchors from settled finals. <b>Fair</b> price from that probability; <b>Edge</b> = model − vig-free market; <b>EV</b> net of vig.</li>
   <li><b>OSI</b> offense strength index (50 = avg). <b>FIP</b> fielding-independent ERA. <b>wOBA</b> weighted on-base. <b>OBR</b> baserunning index. Percentiles empirical vs the league.</li>
   <li>Uncalibrated prior — no OOS edge clears the promotion gate; OSI is a team proxy; weather not yet modeled. Observed stats vs model estimates vs market prices are kept distinct.</li></ul></details></div>
"""


def render_html(r):
    """Full standalone document (wraps report_body with the design-system stylesheet)."""
    e = html.escape
    return (f'<!DOCTYPE html><html lang=en><head><meta charset=utf-8>'
            f'<meta name=viewport content="width=device-width,initial-scale=1">'
            f'<title>{e(r["away"])}@{e(r["home"])} — MLB Model</title>'
            f'<style>{_CSS}</style></head><body><div class=wrap>{report_body(r)}</div></body></html>')


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Matchup Intelligence Report (terminal).")
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", default="matchup_report.html")
    ap.add_argument("--no-fetch", action="store_true", help="use cached odds only (0 API credits)")
    args = ap.parse_args()
    away, home = (s.strip().upper() for s in args.game.split("@", 1))
    r = build_report(away, home, fetch=not args.no_fetch)
    open(args.out, "w", encoding="utf-8").write(render_html(r))
    print(f"wrote {args.out}  ({r['away']}@{r['home']})")


if __name__ == "__main__":
    main()
