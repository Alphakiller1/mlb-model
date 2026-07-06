"""Report section HTML builders (Today, Props, Portfolio, Results, Trends, Research)."""
from __future__ import annotations

import html

from mlbmodel.baseball.model import model_probabilities
from mlbmodel.market import prizepicks
from mlbmodel.market.probability import p_over_line_erf
from mlbmodel.leans.calibration import calibration_buckets, summarize_record
from mlbmodel.analytics.edge_intel import (
    clv_from_snapshots,
    market_type_record,
    team_prediction_record,
)
from mlbmodel.report.edge_ui import (
    clv_panel_html,
    market_performance_html,
    team_accuracy_html,
)
from mlbmodel.portfolio.risk import summarize_positions
from mlbmodel.report.decision import MKT_LABEL as _MKT_LABEL
from mlbmodel.report.html_fmt import display as _display, edge_grade as _edge_grade, section_head
from mlbmodel.report.matchup import _headshot, _logo
from mlbmodel.report.props_ui import pitcher_prop_deck

e = html.escape

def slate(repo, pitcher_rows=None):
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
            game_pitchers = [
                row for row in (pitcher_rows or [])
                if row.get("team") in {a, h}
            ]
            gd = repo.load_game(a, h, pitcher_rows=game_pitchers or None)
            repo.enrich_trends(gd, a, h)
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
def today(slate, sd, sharp_by_pk, sync=None, edge_command=""):
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
 <div class=ctx>Model edge vs live lines — where we beat the market, what we&apos;re projecting, and historical CLV.</div>
 {edge_command}
 <div class=cards>
   <div class=card><div class=k>Games</div><div class=v>{n}</div></div>
   <div class=card><div class=k>Slate</div><div class="v v-sm">{e(sd or "—")}</div></div>
   <div class=card><div class=k>With sharp signal</div><div class=v>{nsharp}</div></div>
   <div class=card><div class=k>MLBMA sync</div><div class="v v-sm">{e(sync_label)}</div></div>
 </div>
 <div class=cols>
   <div class=ca-board>{section_head("Slate", icon="slate")}<div class=body>
     <div class=table-scroll><table><tr><th>Game</th><th>Time</th><th>Win%(H)</th><th>Proj tot</th><th>Margin</th><th>Lean</th><th>Sharp</th></tr>{rows or '<tr><td class=mut colspan=7>No slate loaded.</td></tr>'}</table></div></div></div>
   <div class=ca-board>{section_head("Biggest model leans", icon="matchups")}<div class=body>
     <div class=table-scroll><table><tr><th>Lean</th><th>Margin</th><th>Win%</th><th>Tot</th></tr>{lrows or '<tr><td class=mut colspan=4>—</td></tr>'}</table></div>
     <div class=note>Ranked by projected run margin. Open in <b>Matchups</b> for fair vs market edge.</div></div></div>
 </div>"""

def _p_over(line, mean, sd):
    """P(stat > line) via a normal approximation of the simulated distribution."""
    return p_over_line_erf(line, mean, sd or 0)


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
                    else f' <span class="mut odds-variant">{e(str(line.get("odds_type")))}</span>'
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


def props(pitchers, prop_board, pp_board=None, ud_board=None, sl_board=None, top_leans=""):
    pp_board = pp_board or {}
    ud_board = ud_board or {}
    sl_board = sl_board or {}
    pickem_sources = [
        ("PrizePicks", pp_board),
        ("Underdog", ud_board),
        ("Sleeper", sl_board),
    ]

    all_markets = []
    for row in pitchers:
        reports = row.get("market_report") or []
        if row.get("projection_trust") == "trusted":
            all_markets.extend(
                [{"pitcher": row.get("pitcher"), **report} for report in reports]
            )

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
    _, pickem_count = _pickem_rows(pitchers, pickem_sources)
    pitcher_deck = pitcher_prop_deck(pitchers, pickem_sources)
    confirmed = sum(1 for row in pitchers if row.get("lineup_status") == "confirmed")
    return f"""<h2>Pitcher Props</h2>
 <div class=ctx>One card per starter — expand for projections, market lines, pick&apos;em boards, and pitch-mix breakdown.</div>
 {top_leans}
 <div class=cards>
   <div class=card><div class=k>Probable starters</div><div class=v>{len(pitchers)}</div></div>
   <div class=card><div class=k>Confirmed lineups</div><div class=v>{confirmed}/30</div></div>
   <div class=card><div class=k>Priced prop sides</div><div class=v>{len(all_markets)}</div></div>
   <div class=card><div class=k>Pick&apos;em lines</div><div class=v>{pickem_count}</div></div>
 </div>
 <div class=ca-board>{section_head("Prop market report", icon="props")}<div class=body>
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter pitcher or prop…" data-filter-for="props-report-table" aria-label="Filter props report"></div>
   <div class=table-scroll><table id=props-report-table class=sortable><tr><th>Pitcher</th><th>Prop</th><th>Bet</th>
   <th>Best price</th><th>Model</th><th>Market</th><th>Edge</th><th>State</th></tr>
   {report_rows}</table></div>
   <div class=note>Ranked edges across the slate. Open a pitcher card below for full lines and arsenal context.</div></div></div>
 <div class=ca-board>{section_head("Pitcher breakdowns", icon="props")}<div class=body>
   {pitcher_deck}
   <div class=note>Pick&apos;em leans use each book&apos;s scoring formula where applicable. P(over) is a normal approximation of the simulated distribution; leans ≥58% are highlighted. Not betting advice.</div>
 </div></div>"""


def portfolio(reader, gate, slate):
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
 <div class=ca-board>{section_head("Open paper positions", icon="portfolio")}<div class=body>
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter positions…" data-filter-for="portfolio-table" aria-label="Filter portfolio"></div>
   <div class=table-scroll><table id=portfolio-table class=sortable><tr><th>Game</th><th>Market</th><th>Selection</th>
   <th>Entry</th><th>Model</th><th>Market</th><th>Risk</th><th>Entered</th></tr>
   {rows or '<tr><td class=mut colspan=8>No open paper positions.</td></tr>'}</table></div>
   <div class=note>{e(gate_note)} Live-money execution is outside this model.</div>
 </div></div>"""


def results(reader):
    result = reader.get(
        "model_leans?select=lean_id,slate_date,game_pk,source,market,selection,line,"
        "model_prob,model_value,edge,lean,won,push,settled,entry_odds,recorded_at"
        "&order=recorded_at.desc&limit=2000"
    )
    if result.error:
        return f"""<h2>Results</h2><div class=ctx>Track record, CLV, calibration, and where the model finds value.</div>
 <div class=empty>Lean warehouse unavailable: {e(result.error)}. Apply migration
 <code>0003_model_leans.sql</code> and configure <code>SUPABASE_URL</code> +
 <code>SUPABASE_KEY</code> in GitHub Actions secrets.</div>"""

    rows = result.rows
    clv_result = reader.get(
        "prediction_market_snapshots?settled=eq.true&won=not.is.null"
        "&entry_prob=not.is.null&implied_probability=not.is.null"
        "&select=market_type,entry_prob,implied_probability,won&limit=5000"
    )
    clv_summary = clv_from_snapshots(clv_result.rows if not clv_result.error else [])
    teams = team_prediction_record(rows)
    market_perf = market_type_record(rows)
    summary = summarize_record(rows)
    cal = calibration_buckets(rows)
    hit = summary.get("hit_rate")
    hit_txt = f"{hit:.1f}%" if hit is not None else "—"

    cal_rows = "".join(
        f'<tr><td>{e(c["bucket"])}</td><td>{c["n"]}</td><td>{c["predicted"]:.1f}%</td>'
        f'<td>{c["actual"]:.1f}%</td><td>{c["gap"]:+.1f}pt</td></tr>'
        for c in cal
    ) or '<tr><td class=mut colspan=5>No settled leans for calibration yet.</td></tr>'

    src_rows = "".join(
        f'<tr><td>{e(src)}</td><td>{v["w"]}</td><td>{v["l"]}</td><td>{v["p"]}</td>'
        f'<td>{(v["w"]/(v["w"]+v["l"])*100 if v["w"]+v["l"] else 0):.1f}%</td></tr>'
        for src, v in sorted((summary.get("by_source") or {}).items())
    ) or '<tr><td class=mut colspan=5>—</td></tr>'

    rows_html = []
    for r in rows[:40]:
        edge_cell = f'{float(r["edge"]):+.1f}pt' if r.get("edge") is not None else "—"
        entry_cell = str(int(r["entry_odds"])) if r.get("entry_odds") is not None else "—"
        line_suffix = f' {_display(r.get("line"), digits=1)}' if r.get("line") is not None else ""
        result_cell = "W" if r.get("won") else ("P" if r.get("push") else ("L" if r.get("settled") else "—"))
        rows_html.append(
            f'<tr><td>{e(str(r.get("slate_date") or ""))}</td>'
            f'<td>{e(str(r.get("source") or ""))}</td>'
            f'<td>{e(str(r.get("market") or ""))} {e(str(r.get("selection") or ""))}{line_suffix}</td>'
            f'<td class=num>{entry_cell}</td>'
            f'<td>{e(str(r.get("lean") or ""))}</td>'
            f'<td class=num>{edge_cell}</td>'
            f'<td>{result_cell}</td></tr>'
        )
    recent = "".join(rows_html) or '<tr><td class=mut colspan=7>No leans recorded yet.</td></tr>'

    clv_panel = clv_panel_html(clv_summary)
    team_panel = team_accuracy_html(teams)
    market_panel = market_performance_html(market_perf)

    return f"""<h2>Results</h2>
 <div class=ctx>Honest track record: CLV vs closing lines, calibration, team accuracy, and market-level edge.</div>
 <div class=cards>
   <div class=card><div class=k>Record</div><div class=v>{summary["wins"]}-{summary["losses"]}-{summary["pushes"]}</div></div>
   <div class=card><div class=k>Hit rate</div><div class=v>{hit_txt}</div></div>
   <div class=card><div class=k>Historical CLV</div><div class=v>{(f'{clv_summary["clv_pts"]:+.1f}pt' if clv_summary else "—")}</div></div>
   <div class=card><div class=k>Leans logged</div><div class=v>{len(rows)}</div></div>
 </div>
 {clv_panel}
 <div class=cols>
   {team_panel}
   {market_panel}
 </div>
 <div class=ca-board>{section_head("Calibration", icon="results")}<div class=body>
   <div class=table-scroll><table class=sortable><tr><th>Bucket</th><th>n</th><th>Predicted</th><th>Actual</th><th>Gap</th></tr>{cal_rows}</table></div>
   <div class=note>Bucketed by model probability vs realized hit-rate once games finalize.</div>
 </div></div>
 <div class=ca-board>{section_head("By source", icon="results")}<div class=body>
   <div class=table-scroll><table><tr><th>Source</th><th>W</th><th>L</th><th>P</th><th>Hit%</th></tr>{src_rows}</table></div>
 </div></div>
 <div class=ca-board>{section_head("Recent leans", icon="results")}<div class=body>
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter leans…" data-filter-for="results-recent-table" aria-label="Filter results"></div>
   <div class=table-scroll><table id=results-recent-table class=sortable><tr><th>Date</th><th>Source</th><th>Market</th><th>Entry</th><th>Lean</th><th>Edge</th><th>Result</th></tr>{recent}</table></div>
 </div></div>"""


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


def trends(reports):
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
        cards += f"""<div class=ca-board><h2>{e(r.game)} · {lean_txt}</h2><div class=body>
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
 <div class=ca-board>{section_head("Dominant trend board", icon="trends")}<div class=body>
   <div class=table-scroll><table><tr><th>Game</th><th>Team</th><th>Type</th><th>Signal</th>
   <th>Mag</th><th>n</th><th>Lean / bet</th></tr>{board}</table></div>
   <div class=note>Ranked by blended score (magnitude × sample × relevance). σ = SDs from the league baseline.</div></div></div>
 {cards}"""


def research(reader, pv, f5_board=None, clv_summary=None):
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
    f5_panel = (f'<div class=ca-board>{section_head("First 5 (F5) edges", icon="markets")}<div class=body>'
                f'<div class=table-scroll><table><tr><th>Game</th><th>Market</th><th>Side</th>'
                f'<th>Model%</th><th>Price</th><th>Edge</th><th>State</th></tr>{f5rows}</table></div>'
                f'<div class=note>{f5_note}</div></div></div>')
    clv_panel = clv_panel_html(clv_summary)

    return f"""<h2>Research</h2>
 <div class=ctx>Model health, CLV backbone, and promotion gate — evidence before sizing.</div>
 {clv_panel}
 <div class=ca-board>{section_head("Promotion gate", icon="research")}<div class=body>
   <div class="vbar {tone}"><b>{pv['verdict']}</b><span>{e('; '.join(pv.get('reasons', [])))}</span></div>
	   <div class=note>Promotion also requires an executable signal timestamp and entry price. Open-to-close hindsight cannot qualify.</div></div></div>
 {f5_panel}
 <div class=ca-board>{section_head("Kalshi price calibration", icon="research")}<div class=body>
   <div class=table-scroll><table><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div></div></div>"""
