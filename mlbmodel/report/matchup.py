"""
Matchup Intelligence Report — the canonical, auditable output of the unified MLB Model.

Analytical inheritance (NOT imitation): this is powered by the *actual* validated logic from
Bet Evaluator (`bet_evaluator`) — expected-runs model, fair-price/value layer, risk layer — plus
sharp signals + market prices from the governed warehouse. Every section is traceable to its
source logic + data timestamp + model/metric version. It renders in the Chase Analytics design
contract (governance/DESIGN-CONTRACT.md) as a responsive research workstation with progressive
disclosure. No private chain-of-thought is exposed — only reproducible calculations and evidence.

During the parallel-run phase it imports the legacy `bet_evaluator` (documented migration
dependency in CONSOLIDATION-PLAN); run it with a Python env that has the legacy deps on path:

    cd <bet-evaluator> && PYTHONPATH=<mlb-model> .venv/bin/python -m mlbmodel.report.matchup \
        --game NYY@BOS --out report.html
"""
from __future__ import annotations

import argparse
import html
import zlib
from datetime import date, datetime, timezone

import bet_evaluator as BE  # legacy validated logic (analytical inheritance)
import config


# ── factor decomposition (observation -> feature -> effect -> game state) ─────
def _factors(gd, anchors) -> list[dict]:
    """Each material factor's contribution to expected runs, with full attribution."""
    league = anchors["league_runs"]
    out = []

    def f(name, value, baseline, factor, markets, priced, stability, note, conf="med"):
        eff = (factor - 1.0) * 100.0
        out.append({
            "name": name, "value": value, "baseline": baseline,
            "direction": "↑ runs" if factor > 1.001 else ("↓ runs" if factor < 0.999 else "neutral"),
            "magnitude_pct": round(eff, 1), "markets": markets, "confidence": conf,
            "priced_in": priced, "stability": stability, "note": note,
        })

    f("Away offense (OSI)", gd.away_osi, 50, BE.offense_factor(gd.away_osi),
      "Away TT, Total, ML", "partially (lineup edges often not)", "season-stable",
      "Lineup offensive strength vs opposing hand, regressed to mean.")
    f("Home offense (OSI)", gd.home_osi, 50, BE.offense_factor(gd.home_osi),
      "Home TT, Total, ML", "partially", "season-stable",
      "Lineup offensive strength vs opposing hand, regressed to mean.")
    f("Away SP run-prevention (FIP+pen)", gd.away_fip, config.LEAGUE_FIP,
      BE.pitch_factor(gd.away_fip, gd.away_pen_factor), "Home TT, Total, ML",
      "yes (SP is the headline number)", "noisy early-season",
      f"Away SP FIP {gd.away_fip} blended {config.SP_FIP_WEIGHT:.0%} with bullpen.", conf="high")
    f("Home SP run-prevention (FIP+pen)", gd.home_fip, config.LEAGUE_FIP,
      BE.pitch_factor(gd.home_fip, gd.home_pen_factor), "Away TT, Total, ML",
      "yes", "noisy early-season",
      f"Home SP FIP {gd.home_fip} blended {config.SP_FIP_WEIGHT:.0%} with bullpen.", conf="high")
    f("Park factor", gd.park_factor, 1.00, gd.park_factor, "Total, TT",
      "yes (well known)", "stable", f"{gd.home} park run environment.", conf="high")
    # bullpen + weather as qualitative context rows
    pen = (gd.away_pen_factor + gd.home_pen_factor) / 2
    f("Bullpen run-prevention (avg)", round(pen, 3), 1.00, pen, "Total, late-game ML",
      "partially", "varies w/ usage", "Blended into the SP run-prevention factor (innings SP misses).")
    w = gd.weather or {}
    if w and not w.get("dome"):
        wind = w.get("wind_mph")
        f("Weather (wind/temp)", f"{w.get('temp_f','?')}F / {wind or '?'}mph", "neutral",
          1.0, "Total", "loosely", "temporary",
          "Wind/temperature shift ball flight; directional, not in the runs model yet.", conf="low")
    return out


def _market_row(market, side, line, ou, gd, probs, anchors, odds):
    """Fair prob/price + EV vs an available market price (if any)."""
    p, desc = BE.market_probability(market, side, line, gd, probs, anchors, ou)
    p = BE.clip(p, 0.02, 0.98)
    fair = BE.prob_to_american(p)
    row = {"label": desc, "fair_prob": round(p * 100, 1), "fair_odds": fair,
           "market_odds": None, "vig_free": None, "ev": None, "max_entry": fair, "verdict": "—"}
    if odds is not None:
        v = BE.value_layer(p, odds)
        row.update({"market_odds": odds, "ev": round(v["ev_per_unit"], 3),
                    "vig_free": round(BE.american_to_implied(odds) * 100, 1),
                    "verdict": v["verdict"]})
    return row


def _action(rows, sharp) -> dict:
    """Honest action classification (BET/MONITOR/AVOID/ABSTAIN) — default ABSTAIN."""
    plays = [r for r in rows if r["verdict"] == "PLAY"]
    review = [r for r in rows if r["verdict"] == "REVIEW"]
    if review:
        return {"label": "MONITOR", "tone": "amber",
                "why": "Edge too large to trust at face value — verify inputs/line before acting."}
    if plays and sharp:
        return {"label": "MONITOR", "tone": "amber",
                "why": "Model edge present and sharp signal exists, but no validated OOS edge clears "
                       "the promotion gate yet — track, don't fire."}
    if plays:
        return {"label": "MONITOR", "tone": "amber",
                "why": "Model shows a slim edge; no sharp confirmation. Watch for a better number."}
    return {"label": "ABSTAIN", "tone": "mut",
            "why": "No market clears the value threshold. Honest-empty: no edge, no play."}


def build_report(away: str, home: str, *, odds_map: dict | None = None) -> dict:
    """Assemble the full structured report from real model logic. odds_map: {(market,side):odds}."""
    anchors = BE.refresh_anchors()
    gd = BE.load_game(away, home)
    probs = BE.model_probabilities(gd, anchors)
    odds_map = odds_map or {}

    markets = [
        _market_row("ml", gd.home, None, None, gd, probs, anchors, odds_map.get(("ml", gd.home))),
        _market_row("ml", gd.away, None, None, gd, probs, anchors, odds_map.get(("ml", gd.away))),
        _market_row("total", "over", round(probs.exp_total * 2) / 2, None, gd, probs, anchors,
                    odds_map.get(("total", "over"))),
        _market_row("runline", gd.home if probs.exp_margin > 0 else gd.away,
                    -1.5, None, gd, probs, anchors, None),
    ]
    risks = BE.risk_layer(gd, "ml", anchors)
    gpk = zlib.crc32(f"{date.today().isoformat()}|{away}|{home}".encode())
    sharp = _sharp_for(gpk)
    action = _action(markets, sharp)
    return {
        "away": away, "home": home, "gd": gd, "probs": probs, "anchors": anchors,
        "markets": markets, "factors": _factors(gd, anchors), "risks": risks,
        "sharp": sharp, "action": action, "game_pk": gpk,
        "model_version": config.MODEL_VERSION, "metric_version": config.METRIC_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _sharp_for(gpk: int) -> list[dict]:
    """Live sharp signals for this game from the governed warehouse (read-only)."""
    try:
        import json
        import urllib.request
        if not config.SUPABASE_URL or not config.SUPABASE_KEY:
            return []
        url = (config.SUPABASE_URL.rstrip("/") + "/rest/v1/sharp_signals"
               f"?game_pk=eq.{gpk}&select=market_type,selection,divergence,steam_flag,snapshot_time")
        req = urllib.request.Request(url, headers={"apikey": config.SUPABASE_KEY,
                                                   "Authorization": f"Bearer {config.SUPABASE_KEY}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []


# ── rendering (Chase Analytics design contract) ──────────────────────────────
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap');
:root{--bg:#070b12;--panel:#111827;--line:rgba(148,163,184,.18);--line-strong:rgba(196,181,253,.34);
--ink:#f3f6fb;--soft:#cbd5e1;--mut:#94a3b8;--teal:#2dd4bf;--violet:#8b5cf6;--violet-2:#c4b5fd;
--blue:#60a5fa;--green:#22c55e;--amber:#f59e0b;--red:#fb7185;--shadow:0 18px 60px rgba(0,0,0,.34)}
*{box-sizing:border-box}body{margin:0;color:var(--ink);font-family:Inter,system-ui,sans-serif;
background:linear-gradient(rgba(148,163,184,.04) 1px,transparent 1px) 0 0/26px 26px,
linear-gradient(90deg,rgba(148,163,184,.04) 1px,transparent 1px) 0 0/26px 26px,
linear-gradient(180deg,#080c14,#05070c);min-height:100vh;padding:24px}
.wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:16px}
.hd{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px}
.hd h1{margin:0;font-size:26px;font-weight:700;background:linear-gradient(90deg,var(--teal),var(--violet-2));
-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hd .meta{color:var(--mut);font-size:12px;text-align:right}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media(max-width:760px){.cards{grid-template-columns:repeat(2,1fr)}}
.card,.panel{background:linear-gradient(160deg,rgba(17,24,39,.72),rgba(8,13,22,.82));
border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}
.card .k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.4px}
.card .v{font-size:24px;font-weight:700;margin-top:4px}
.act{font-size:22px;font-weight:700}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600}
.teal{color:var(--teal)}.amber{color:var(--amber)}.red{color:var(--red)}.mut{color:var(--mut)}.blue{color:var(--blue)}.violet{color:var(--violet-2)}
.panel h2{margin:0 0 12px;font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--violet-2)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--mut);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.3px;padding:6px 10px;border-bottom:1px solid var(--line)}
td{padding:7px 10px;border-bottom:1px solid rgba(148,163,184,.08)}
td.mono,th.mono{font-family:"JetBrains Mono",monospace}
.pos{color:var(--green)}.neg{color:var(--red)}
details{border-top:1px solid var(--line);padding-top:10px;margin-top:8px}
summary{cursor:pointer;color:var(--soft);font-weight:600;font-size:13px}
.trace{color:var(--mut);font-size:11px;margin-top:6px;font-style:italic}
ul{margin:6px 0;padding-left:18px}li{margin:4px 0;font-size:13px;color:var(--soft)}
"""


def _td_ev(ev):
    if ev is None:
        return '<td class="mono mut">—</td>'
    cls = "pos" if ev > 0 else "neg"
    return f'<td class="mono {cls}">{ev:+.3f}</td>'


def render_html(r: dict) -> str:
    gd, probs, e = r["gd"], r["probs"], html.escape
    rows = "".join(
        f"<tr><td>{e(m['label'])}</td><td class=mono>{m['fair_prob']}%</td>"
        f"<td class=mono>{m['fair_odds']:+d}</td>"
        f"<td class=mono>{(str(m['market_odds'])+'') if m['market_odds'] is not None else '—'}</td>"
        f"<td class=mono>{(str(m['vig_free'])+'%') if m['vig_free'] is not None else '—'}</td>"
        f"{_td_ev(m['ev'])}"
        f"<td class=mono>{m['max_entry']:+d}</td>"
        f"<td>{e(m['verdict'])}</td></tr>"
        for m in r["markets"])
    frows = "".join(
        f"<tr><td>{e(f['name'])}</td><td class=mono>{e(str(f['value']))}</td>"
        f"<td class=mono>{e(str(f['baseline']))}</td><td>{f['direction']}</td>"
        f"<td class=mono>{f['magnitude_pct']:+.1f}%</td><td>{e(f['markets'])}</td>"
        f"<td>{f['confidence']}</td><td>{e(f['priced_in'])}</td><td>{e(f['stability'])}</td></tr>"
        for f in r["factors"])
    sharp = (r["sharp"] and "".join(
        f"<li>{e(s['market_type'])} <b>{e(str(s['selection']))}</b> — divergence "
        f"{float(s.get('divergence') or 0)*100:+.1f}pts{' · STEAM' if s.get('steam_flag') else ''}</li>"
        for s in r["sharp"])) or "<li class=mut>No sharp signal recorded for this game.</li>"
    risks = "".join(f"<li>{e(x)}</li>" for x in r["risks"]) or "<li>None flagged.</li>"
    w = gd.weather or {}
    wx = "Dome" if w.get("dome") else f"{w.get('temp_f','?')}F, wind {w.get('wind_mph','?')}mph"
    act = r["action"]
    return f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{e(r['away'])}@{e(r['home'])} — Matchup Intelligence</title><style>{_CSS}</style></head>
<body><div class=wrap>
  <div class=hd>
    <div><h1>{e(r['away'])} @ {e(r['home'])}</h1>
      <div class=mut style="font-size:13px;margin-top:4px">
        {e(gd.away_sp)} ({e(gd.away_hand)}HP, FIP {gd.away_fip}) vs
        {e(gd.home_sp)} ({e(gd.home_hand)}HP, FIP {gd.home_fip}) · {e(gd.home)} park {gd.park_factor} · {e(wx)}</div></div>
    <div class=meta>model {e(r['model_version'])} · metrics {e(r['metric_version'])}<br>
      generated {e(r['generated'])} · game_pk {r['game_pk']}</div>
  </div>

  <div class=cards>
    <div class=card><div class=k>Win probability</div><div class=v><span class=teal>{probs.p_home_win*100:.0f}%</span> {e(r['home'])}</div>
      <div class=mut style="font-size:12px">{probs.p_away_win*100:.0f}% {e(r['away'])}</div></div>
    <div class=card><div class=k>Expected total</div><div class=v>{probs.exp_total}</div>
      <div class=mut style="font-size:12px">margin {probs.exp_margin:+.2f}</div></div>
    <div class=card><div class=k>Best fair edge</div><div class=v class=blue>{max((m['fair_prob'] for m in r['markets']),default=0):.0f}%</div>
      <div class=mut style="font-size:12px">model fair prob</div></div>
    <div class=card><div class=k>Action</div><div class="act {act['tone']}">{act['label']}</div>
      <div class=mut style="font-size:11.5px">{e(act['why'])}</div></div>
  </div>

  <div class=panel><h2>Markets — fair vs available (net of vig), max entry = break-even</h2>
    <table><tr><th>Market</th><th class=mono>Fair %</th><th class=mono>Fair</th><th class=mono>Mkt</th>
      <th class=mono>Vig-free</th><th class=mono>EV/u</th><th class=mono>Max entry</th><th>Verdict</th></tr>
      {rows}</table>
    <div class=trace>Source: bet_evaluator.market_probability + value_layer · expected-runs model
      (OSI·FIP·park·bullpen, regressed) · anchors refreshed from settled finals.</div></div>

  <div class=panel><h2>Factor contribution — observation → effect → market</h2>
    <table><tr><th>Factor</th><th class=mono>Value</th><th class=mono>Base</th><th>Dir</th>
      <th class=mono>Effect</th><th>Markets</th><th>Conf</th><th>Priced in?</th><th>Stability</th></tr>
      {frows}</table>
    <div class=trace>Effect = factor's multiplicative deviation from league baseline in the expected-runs
      model. Correlated inputs (SP+bullpen) are blended once to avoid double-counting.</div></div>

  <div class=panel><h2>Sharp money &amp; line movement</h2><ul>{sharp}</ul>
    <div class=trace>Source: warehouse sharp_signals (de-vig sharp-vs-soft + steam), point-in-time.</div></div>

  <details class=panel><summary>Risks, counterarguments &amp; invalidation conditions</summary>
    <ul>{risks}</ul>
    <div class=trace>Source: bet_evaluator.risk_layer + single-game MLB variance (margin SD
      ~{r['anchors']['margin_sd']:.1f} runs). The model is a transparent prior, not a calibrated edge.</div></details>

  <details class=panel><summary>Model &amp; data audit</summary>
    <ul><li>Model {e(r['model_version'])}, metrics {e(r['metric_version'])} · league runs {r['anchors']['league_runs']},
      home win% {r['anchors']['home_winp']}, margin SD {r['anchors']['margin_sd']} (from settled finals).</li>
    <li>Features from the MLBMA pipeline export (hub_dataset); slate from MLB Stats API.</li>
    <li><b>Honest limits:</b> uncalibrated prior; no validated OOS edge clears the promotion gate;
      OSI is a team-level proxy; weather not yet in the runs model.</li></ul></details>
</div></body></html>"""


def main():  # pragma: no cover
    p = argparse.ArgumentParser(description="Generate a Matchup Intelligence Report.")
    p.add_argument("--game", required=True, help='AWAY@HOME, e.g. NYY@BOS')
    p.add_argument("--out", default="matchup_report.html")
    args = p.parse_args()
    away, home = (s.strip().upper() for s in args.game.split("@", 1))
    r = build_report(away, home)
    open(args.out, "w", encoding="utf-8").write(render_html(r))
    print(f"wrote {args.out}  ({r['away']}@{r['home']} · action {r['action']['label']})")


if __name__ == "__main__":
    main()
