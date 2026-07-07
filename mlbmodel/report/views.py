"""Report section HTML builders (Today, Props, Results, Trends, Research)."""
from __future__ import annotations

import html

from mlbmodel.baseball.model import model_probabilities
from mlbmodel.leans.calibration import calibration_buckets, summarize_record
from mlbmodel.analytics.edge_intel import (
    clv_from_snapshots,
    market_type_record,
    team_prediction_record,
)
from mlbmodel.report.decision import MKT_LABEL as _MKT_LABEL
from mlbmodel.report.edge_ui import (
    clv_panel_html,
    market_performance_html,
    team_accuracy_html,
)
from mlbmodel.report.html_fmt import display as _display, edge_grade as _edge_grade, section_head, lean_dir_html
from mlbmodel.report.html_fmt import (
    prob_chip_html,
    pct_chip_html,
    val_chip_html,
    val_grade_html,
)
from mlbmodel.report.matchup import _logo
from mlbmodel.report.shell import slate_view_label
from mlbmodel.report.props_ui import pitcher_prop_deck, prop_channel_counts
from mlbmodel.report.trends_ui import trends_section_html

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
                 f'<td>{prob_chip_html(g["ph"])}</td>'
                 f'<td>{val_chip_html(g["total"], "game_total", digits=1)}</td>'
                 f'<td>{val_grade_html(g["margin"], "margin", digits=1, suffix="")}</td>'
                 f'<td class=side>{e(g["lean"])}</td>'
                 f'<td class=mut>{e(str(g.get("asp") or "—"))} / {e(str(g.get("hsp") or "—"))}</td>'
                 f'<td class=mut>{_display(g.get("ak"), digits=0)} / {_display(g.get("hk"), digits=0)}</td>'
                 f'<td>{("<span class=pill warnc>"+str(sc)+"</span>") if sc else "<span class=mut>—</span>"}</td></tr>')
    ok = [g for g in slate if not g.get("err")]
    n = len(ok)
    nsharp = sum(len(v) for v in sharp_by_pk.values())
    sync = sync or {}
    sync_label = "Exact" if sync.get("status") == "exact" else (
        "Live fallback" if sync.get("status") == "fallback" else "Untracked"
    )
    return f"""<h2>{e(slate_view_label(sd))}</h2>
 {edge_command}
 <div class=cards>
   <div class=card><div class=k>Games</div><div class=v>{n}</div></div>
   <div class=card><div class=k>Slate</div><div class="v v-sm">{e(sd or "—")}</div></div>
   <div class=card><div class=k>Sharp signals</div><div class=v>{nsharp}</div></div>
   <div class=card><div class=k>MLBMA sync</div><div class="v v-sm">{e(sync_label)}</div></div>
 </div>
 <div class=ca-board>{section_head("Slate", icon="slate")}<div class=body>
   <div class=table-scroll><table class=sortable><tr><th>Game</th><th>Time</th><th>Win%(H)</th><th>Tot</th><th>Margin</th><th>Lean</th><th>SPs</th><th>K%</th><th>Sharp</th></tr>{rows or '<tr><td class=mut colspan=9>No slate loaded.</td></tr>'}</table></div></div></div>"""


def props(pitchers, prop_board, pp_board=None, ud_board=None, sl_board=None):
    pp_board = pp_board or {}
    ud_board = ud_board or {}
    sl_board = sl_board or {}
    pickem_sources = [
        ("PrizePicks", pp_board),
        ("Underdog", ud_board),
        ("Sleeper", sl_board),
    ]

    book_n, fantasy_n = prop_channel_counts(pitchers, pickem_sources)
    deck = pitcher_prop_deck(pitchers, pickem_sources)
    return f"""<h2>Pitcher Props</h2>
 <div class=cards>
   <div class=card><div class=k>Starters</div><div class=v>{len(pitchers)}</div></div>
   <div class=card><div class=k>Book lines</div><div class=v>{book_n}</div></div>
   <div class=card><div class=k>Fantasy lines</div><div class=v>{fantasy_n}</div></div>
 </div>
 {deck}"""


def results(reader):
    result = reader.get(
        "model_leans?select=lean_id,slate_date,game_pk,source,market,selection,line,"
        "model_prob,model_value,edge,lean,won,push,settled,entry_odds,recorded_at"
        "&order=recorded_at.desc&limit=2000"
    )
    if result.error:
        return f"""<h2>Results</h2>
 <div class=empty>Lean warehouse unavailable: {e(result.error)}</div>"""

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
            f'<td>{lean_dir_html(r.get("lean"))}</td>'
            f'<td class=num>{edge_cell}</td>'
            f'<td>{result_cell}</td></tr>'
        )
    recent = "".join(rows_html) or '<tr><td class=mut colspan=7>No leans recorded yet.</td></tr>'

    clv_panel = clv_panel_html(clv_summary)
    team_panel = team_accuracy_html(teams)
    market_panel = market_performance_html(market_perf)

    return f"""<h2>Results</h2>
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
 <div class=cols>
 <div class=ca-board>{section_head("Calibration", icon="results")}<div class=body>
   <div class=table-scroll><table class=sortable><tr><th>Bucket</th><th>n</th><th>Predicted</th><th>Actual</th><th>Gap</th></tr>{cal_rows}</table></div>
 </div></div>
 <div class=ca-board>{section_head("By source", icon="results")}<div class=body>
   <div class=table-scroll><table><tr><th>Source</th><th>W</th><th>L</th><th>P</th><th>Hit%</th></tr>{src_rows}</table></div>
 </div></div>
 </div>
 <div class=ca-board>{section_head("Recent leans", icon="results")}<div class=body>
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter leans…" data-filter-for="results-recent-table" aria-label="Filter results"></div>
   <div class=table-scroll><table id=results-recent-table class=sortable><tr><th>Date</th><th>Source</th><th>Market</th><th>Entry</th><th>Lean</th><th>Edge</th><th>Result</th></tr>{recent}</table></div>
 </div></div>"""


def trends(reports):
    return trends_section_html(reports)


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
            f'<td><b>{e(str(m.get("side")))}</b></td><td class=num>{pct_chip_html(m.get("model"))}</td>'
            f'<td class=num>{(str(m["mkt"]) if isinstance(m.get("mkt"), int) and m["mkt"]>=0 else str(m.get("mkt"))) if m.get("mkt") is not None else "—"}</td>'
            f'<td><b class={_edge_grade((m.get("edge") or 0)/100)}>{m["edge"]:+.1f}pt</b></td>'
            f'<td><span class="pill {m.get("tone","mut")}">{e(str(m.get("state")))}</span></td></tr>'
            for g, m in f5)
    else:
        f5rows = '<tr><td class=mut colspan=7>No F5 prices on slate.</td></tr>'
    f5_panel = (f'<div class=ca-board>{section_head("First 5 (F5) edges", icon="markets")}<div class=body>'
                f'<div class=table-scroll><table class=sortable><tr><th>Game</th><th>Market</th><th>Side</th>'
                f'<th>Model%</th><th>Price</th><th>Edge</th><th>State</th></tr>{f5rows}</table></div></div></div>')

    return f"""<h2>Research</h2>
 <div class=ca-board>{section_head("Promotion gate", icon="research")}<div class=body>
   <div class="vbar {tone}"><b>{pv['verdict']}</b><span>{e('; '.join(pv.get('reasons', [])))}</span></div></div></div>
 {f5_panel}
 <div class=ca-board>{section_head("Kalshi price calibration", icon="research")}<div class=body>
   <div class=table-scroll><table class=sortable><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div></div></div>"""
