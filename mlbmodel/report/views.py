"""Report section HTML builders (Today, Props, Results, Trends, Research)."""
from __future__ import annotations

import html
import json
from pathlib import Path

from mlbmodel.baseball.model import model_probabilities
from mlbmodel.leans.calibration import (
    calibration_buckets,
    clv_summary_from_leans,
    projection_error_summary,
    summarize_record,
    ungraded_reason_counts,
)
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
from mlbmodel.report.html_fmt import display as _display, edge_grade as _edge_grade, section_head, lean_dir_html, desk_pagehead
from mlbmodel.report.html_fmt import pct_chip_html
from mlbmodel.report.board import board_html
from mlbmodel.report.board_mlb import build_board
from mlbmodel.report.props_ui import (
    actionable_counts,
    pitcher_prop_deck,
    prop_channel_counts,
)
from mlbmodel.report.game_keys import assign_slate_keys, parse_game_key
from mlbmodel.report.trends_ui import trends_section_html

e = html.escape

def slate(repo, pitcher_rows=None):
    m = repo.slate()
    if m is None or "Away" not in m.columns:
        return [], None
    sd = str(m.iloc[0].get("Slate_Date", "")) if len(m) else ""
    out = []
    for _, row in m.iterrows():
        a, h = str(row["Away"]).upper().strip(), str(row["Home"]).upper().strip()
        out.append({"away": a, "home": h, "time": str(row.get("Time", "") or "")})
    assign_slate_keys(out)
    anchors = repo.anchors()
    for rec in out:
        a, h = rec["away"], rec["home"]
        _, _, game_number = parse_game_key(rec["key"])
        try:
            game_pitchers = [
                row for row in (pitcher_rows or [])
                if row.get("team") in {a, h}
            ]
            gd = repo.load_game(
                a, h, game_number=game_number, pitcher_rows=game_pitchers or None
            )
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
    return out, sd


# ── sections (each = context -> conclusion -> evidence; honest empty states) ──
def slate_board(slate, sd, sharp_by_pk, sync=None, reports_by_key=None):
    """The slate board — one card per game, each carrying its own priced markets.

    Renders inside the Matchups section, which supplies the page head; this returns the
    board alone so there is exactly one heading over the slate. Card anatomy is the shared
    Board kernel, so MLB, WNBA and NFL read identically.
    """
    board = build_board(slate, sd, reports_by_key or {}, sharp_by_pk, sync)
    return board_html(board)


def props(pitchers, prop_board, pp_board=None, ud_board=None, sl_board=None,
          pickem_snapshots=None, slate_date=None):
    from mlbmodel.market.lines_cache import snapshot_is_fresh, snapshot_label

    pp_board = pp_board or {}
    ud_board = ud_board or {}
    sl_board = sl_board or {}
    pickem_sources = [
        ("PrizePicks", pp_board),
        ("Underdog", ud_board),
        ("Sleeper", sl_board),
    ]

    freshness = ""
    if pickem_snapshots:
        badges = []
        for label, board in pickem_sources:
            if not board:
                continue
            snapshot_at = (pickem_snapshots or {}).get(label.lower())
            fresh = snapshot_is_fresh(snapshot_at, slate_date)
            tone = "pos" if fresh else "warnc"
            state = "" if fresh else " · stale — display only"
            badges.append(
                f'<span class="pill {tone}" style="margin:2px 6px 2px 0;white-space:nowrap">'
                f'{e(label)} · {e(snapshot_label(snapshot_at))}{state}</span>'
            )
        if badges:
            freshness = (
                '<p class=mut style="margin:2px 0 12px;line-height:2">'
                f'Pick\'em line snapshots: {"".join(badges)}</p>'
            )

    book_n, fantasy_n = prop_channel_counts(pitchers, pickem_sources)
    edges_n, clears_n = actionable_counts(pitchers, pickem_sources)
    deck = pitcher_prop_deck(pitchers, pickem_sources)
    return f"""{desk_pagehead(
        "Props",
        sub=(
            "Two channels, two different questions. A priced market can carry an edge "
            "against its de-vigged price; a pick'em leg can only clear its payout's "
            "breakeven. Starters are ranked by what is actionable."
        ),
    )}
 <div class=cards>
   <div class=card><div class=k>Priced edges</div><div class=v>{edges_n}</div>
     <div class="mut mut-sm">model beats the de-vigged price</div></div>
   <div class=card><div class=k>Pick'em clears</div><div class=v>{clears_n}</div>
     <div class="mut mut-sm">above ~57.7% power-play breakeven</div></div>
   <div class=card><div class=k>Starters</div><div class=v>{len(pitchers)}</div></div>
   <div class=card><div class=k>Lines seen</div><div class="v v-sm">{book_n} book / {fantasy_n} pick'em</div></div>
 </div>
 {freshness}
 {deck}"""


def _prediction_status(row: dict) -> tuple[str, str]:
    if row.get("void"):
        return "VOID", str(row.get("ungraded_reason") or "ungradeable")
    if row.get("push"):
        return "PUSH", ""
    if row.get("settled") and row.get("won") is True:
        return "W", ""
    if row.get("settled") and row.get("won") is False:
        return "L", ""
    if row.get("settled"):
        return "GRADED", "realized value recorded"
    return "PENDING", str(row.get("ungraded_reason") or "awaiting final")


def _audit_asset_rows(rows: list[dict]) -> list[dict]:
    """Compact public audit schema used by the lazy, paginated Results tables."""
    game_sources = {"matchup", "f5", "sharp"}
    payload = []
    for row in rows:
        status, detail = _prediction_status(row)
        source = str(row.get("source") or "").lower()
        payload.append({
            "k": "game" if source in game_sources else "prop",
            "d": str(row.get("slate_date") or ""),
            "t": str(row.get("recorded_at") or ""),
            "g": str(row.get("game_pk") or ""),
            "p": str(row.get("pitcher_name") or ""),
            "s": source,
            "m": str(row.get("market") or ""),
            "x": str(row.get("selection") or ""),
            "l": row.get("line"),
            "q": row.get("model_prob"),
            "v": row.get("model_value"),
            "o": row.get("entry_odds"),
            "a": row.get("realized_value"),
            "z": status,
            "n": detail,
            "r": str(row.get("run_id") or ""),
        })
    return payload


def prediction_audit_html(
    rows: list[dict], *, external_asset_url: str | None = None
) -> str:
    """Complete game/F5 and player-prop audit ledgers—never a recent-only sample."""
    game_sources = {"matchup", "f5", "sharp"}
    games = [row for row in rows if str(row.get("source") or "").lower() in game_sources]
    props = [row for row in rows if str(row.get("source") or "").lower() not in game_sources]

    def result_cell(row: dict) -> str:
        status, detail = _prediction_status(row)
        cls = "pos" if status == "W" else "neg" if status == "L" else "mut"
        note = f'<span class="mut mut-sm">{e(detail)}</span>' if detail else ""
        return f'<b class="{cls}">{status}</b>{note}'

    def number(value, digits=1) -> str:
        return _display(value, digits=digits) if value is not None else "—"

    preview_games = games[:100] if external_asset_url else games
    preview_props = props[:100] if external_asset_url else props
    game_rows = "".join(
        f'<tr><td>{e(str(row.get("slate_date") or ""))}'
        f'<span class="mut mut-sm">{e(str(row.get("recorded_at") or ""))}</span></td>'
        f'<td>{e(str(row.get("game_pk") or "—"))}</td>'
        f'<td>{e(str(row.get("source") or ""))}</td>'
        f'<td>{e(str(row.get("market") or ""))} {e(str(row.get("selection") or ""))}'
        f'{(" " + number(row.get("line"))) if row.get("line") is not None else ""}</td>'
        f'<td class=num>{number(row.get("model_prob"), 3)}</td>'
        f'<td class=num>{number(row.get("entry_odds"), 0)}</td>'
        f'<td class=num>{number(row.get("realized_value"))}</td>'
        f'<td>{result_cell(row)}</td><td class=mut>{e(str(row.get("run_id") or "—"))}</td></tr>'
        for row in preview_games
    ) or '<tr><td class=mut colspan=9>No game projections logged.</td></tr>'

    prop_rows = "".join(
        f'<tr><td>{e(str(row.get("slate_date") or ""))}'
        f'<span class="mut mut-sm">{e(str(row.get("recorded_at") or ""))}</span></td>'
        f'<td>{e(str(row.get("pitcher_name") or "—"))}</td>'
        f'<td>{e(str(row.get("source") or ""))}</td>'
        f'<td>{e(str(row.get("market") or ""))}</td>'
        f'<td>{e(str(row.get("selection") or ""))}'
        f'{(" " + number(row.get("line"))) if row.get("line") is not None else ""}</td>'
        f'<td class=num>{number(row.get("model_value"))}</td>'
        f'<td class=num>{number(row.get("realized_value"))}</td>'
        f'<td>{result_cell(row)}</td><td class=mut>{e(str(row.get("run_id") or "—"))}</td></tr>'
        for row in preview_props
    ) or '<tr><td class=mut colspan=9>No player-prop projections logged.</td></tr>'

    load_controls = ""
    audit_script = ""
    game_filter_attr = 'data-filter-for="results-game-audit"'
    prop_filter_attr = 'data-filter-for="results-prop-audit"'
    game_pager = ""
    prop_pager = ""
    if external_asset_url:
        asset_url = json.dumps(external_asset_url)
        load_controls = f"""
   <div class=audit-load><button type=button class=btn onclick=loadPredictionAudit(this)>Load complete history</button>
     <span class=mut>Newest 100 shown initially · <a href={e(external_asset_url)} download>download full audit JSON</a></span></div>"""
        game_filter_attr = 'oninput="auditSearch(\'game\',this.value)"'
        prop_filter_attr = 'oninput="auditSearch(\'prop\',this.value)"'
        game_pager = (
            f'<div class=table-toolbar><button type=button onclick="auditPage(\'game\',-1)">Previous</button>'
            f'<span id=results-game-audit-page class=mut>Newest {len(preview_games)} of {len(games)}</span>'
            '<button type=button onclick="auditPage(\'game\',1)">Next</button></div>'
        )
        prop_pager = (
            f'<div class=table-toolbar><button type=button onclick="auditPage(\'prop\',-1)">Previous</button>'
            f'<span id=results-prop-audit-page class=mut>Newest {len(preview_props)} of {len(props)}</span>'
            '<button type=button onclick="auditPage(\'prop\',1)">Next</button></div>'
        )
        audit_script = f"""<script>
const AUDIT_URL={asset_url}, audit={{rows:[], game:{{page:0,q:''}}, prop:{{page:0,q:''}}}}, AUDIT_PAGE=100;
function auditText(v){{return v===null||v===undefined||v===''?'—':String(v)}}
function auditNum(v,d=1){{const n=Number(v);return Number.isFinite(n)?n.toFixed(d):'—'}}
function auditGrade(r){{const box=document.createElement('span');box.textContent=r.z+(r.n?' · '+r.n:'');box.className=r.z==='W'?'pos':r.z==='L'?'neg':'mut';return box}}
function auditCell(tr,value,cls){{const td=document.createElement('td');if(value instanceof Node)td.append(value);else td.textContent=auditText(value);if(cls)td.className=cls;tr.append(td)}}
function renderPredictionAudit(kind){{
  const state=audit[kind], q=state.q.toLowerCase();
  const rows=audit.rows.filter(r=>r.k===kind&&(!q||Object.values(r).join(' ').toLowerCase().includes(q)));
  const pages=Math.max(1,Math.ceil(rows.length/AUDIT_PAGE));state.page=Math.min(state.page,pages-1);
  const body=document.getElementById('results-'+kind+'-audit-body');body.replaceChildren();
  rows.slice(state.page*AUDIT_PAGE,(state.page+1)*AUDIT_PAGE).forEach(r=>{{const tr=document.createElement('tr');
    auditCell(tr,r.d+' '+r.t);if(kind==='game'){{auditCell(tr,r.g);auditCell(tr,r.s);auditCell(tr,r.m+' '+r.x+(r.l===null?'':' '+auditText(r.l)));auditCell(tr,auditNum(r.q,3),'num');auditCell(tr,auditNum(r.o,0),'num');}}
    else{{auditCell(tr,r.p);auditCell(tr,r.s);auditCell(tr,r.m);auditCell(tr,r.x+(r.l===null?'':' '+auditText(r.l)));auditCell(tr,auditNum(r.v,1),'num');}}
    auditCell(tr,auditNum(r.a,1),'num');auditCell(tr,auditGrade(r));auditCell(tr,r.r,'mut');body.append(tr)}});
  document.getElementById('results-'+kind+'-audit-page').textContent=`${{rows.length.toLocaleString()}} records · page ${{state.page+1}}/${{pages}}`;
}}
function auditSearch(kind,value){{audit[kind].q=value;audit[kind].page=0;renderPredictionAudit(kind)}}
function auditPage(kind,delta){{audit[kind].page=Math.max(0,audit[kind].page+delta);renderPredictionAudit(kind)}}
async function loadPredictionAudit(button){{
  document.querySelectorAll('.audit-load button').forEach(b=>{{b.disabled=true;b.textContent='Loading complete history…'}});
  try{{const data=await fetch(AUDIT_URL).then(r=>{{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}});audit.rows=data.rows||[];renderPredictionAudit('game');renderPredictionAudit('prop');document.querySelectorAll('.audit-load button').forEach(b=>b.textContent='Complete history loaded')}}
  catch(err){{button.disabled=false;button.textContent='Retry complete history';alert('Could not load prediction history: '+err.message)}}
}}
</script>"""

    return f"""
 <div class=ca-board>{section_head(f"All game and F5 prediction runs ({len(games)})", icon="results")}<div class=body>
   <p class=mut>Every recorded model run is retained below, including both market sides and repeated pregame refreshes.</p>
   {load_controls}
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter game audit…" aria-label="Filter game prediction audit" {game_filter_attr}></div>
   <div class=table-scroll><table id=results-game-audit class=sortable><thead><tr><th>Date / logged</th><th>Game PK</th><th>Source</th><th>Projection</th><th>Model p</th><th>Entry</th><th>Actual</th><th>Grade</th><th>Run</th></tr></thead><tbody id=results-game-audit-body>{game_rows}</tbody></table></div>
   {game_pager}
 </div></div>
 <div class=ca-board>{section_head(f"All player-prop prediction runs ({len(props)})", icon="results")}<div class=body>
   <p class=mut>Priced props, pick'em calls, and unpriced model projections share one auditable outcome ledger.</p>
   {load_controls}
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter prop audit…" aria-label="Filter player prop prediction audit" {prop_filter_attr}></div>
   <div class=table-scroll><table id=results-prop-audit class=sortable><thead><tr><th>Date / logged</th><th>Pitcher</th><th>Source</th><th>Market</th><th>Pick / line</th><th>Projection</th><th>Actual</th><th>Grade</th><th>Run</th></tr></thead><tbody id=results-prop-audit-body>{prop_rows}</tbody></table></div>
   {prop_pager}
 </div></div>{audit_script}"""


def results(reader, *, audit_asset_dir: str | Path | None = None):
    query = (
        "model_leans?select=lean_id,slate_date,game_pk,source,market,selection,line,"
        "model_prob,model_value,edge,lean,won,push,settled,entry_odds,recorded_at,"
        "void,ungraded_reason,closing_odds,clv_pts,realized_value,run_id,pitcher_name,model_version"
        "&order=recorded_at.desc"
    )
    result = (
        reader.get_all(query, max_rows=100000)
        if hasattr(type(reader), "get_all")
        else reader.get(query)
    )
    if result.error:
        return f"""{desk_pagehead("Results", sub="Paper track record · CLV · calibration")}
 <div class=empty>Lean warehouse unavailable: {e(result.error)}</div>"""

    rows = result.rows
    clv_result = reader.get(
        "prediction_market_snapshots?settled=eq.true&won=not.is.null"
        "&entry_prob=not.is.null&implied_probability=not.is.null"
        "&select=market_type,entry_prob,implied_probability,won&limit=5000"
    )
    clv_summary = clv_from_snapshots(clv_result.rows if not clv_result.error else [])
    lean_clv = clv_summary_from_leans(rows)
    proj_errors = projection_error_summary(rows)
    reasons = ungraded_reason_counts(rows)
    pending_n = sum(1 for r in rows if not r.get("settled"))
    void_n = sum(1 for r in rows if r.get("void"))
    teams = team_prediction_record(rows)
    market_perf = market_type_record(rows)
    summary = summarize_record(rows)
    cal = calibration_buckets(rows)
    hit = summary.get("hit_rate")
    hit_txt = f"{hit:.1f}%" if hit is not None else "—"
    brier = summary.get("brier")
    brier_txt = f"{brier:.3f}" if brier is not None else "—"

    cal_rows = "".join(
        f'<tr><td>{e(c["bucket"])}</td><td>{c["n"]}</td><td>{c["predicted"]:.1f}%</td>'
        f'<td>{c["actual"]:.1f}% <span class=mut>({c["actual_lo"]:.0f}–{c["actual_hi"]:.0f})</span></td>'
        f'<td>{c["gap"]:+.1f}pt</td>'
        f'<td>{"—" if not c["reliable"] else ("✓" if c["within_ci"] else "✗")}</td></tr>'
        for c in cal
    ) or '<tr><td class=mut colspan=6>No settled leans for calibration yet.</td></tr>'

    src_rows = "".join(
        f'<tr><td>{e(src)}</td><td>{v["w"]}</td><td>{v["l"]}</td><td>{v["p"]}</td>'
        f'<td>{(v["w"]/(v["w"]+v["l"])*100 if v["w"]+v["l"] else 0):.1f}%</td></tr>'
        for src, v in sorted((summary.get("by_source") or {}).items())
    ) or '<tr><td class=mut colspan=5>—</td></tr>'

    rows_html = []
    for r in rows[:40]:
        edge_cell = f'{float(r["edge"]):+.1f}pt' if r.get("edge") is not None else "—"
        entry_cell = str(int(r["entry_odds"])) if r.get("entry_odds") is not None else "—"
        clv_cell = f'{float(r["clv_pts"]):+.1f}' if r.get("clv_pts") is not None else "—"
        line_suffix = f' {_display(r.get("line"), digits=1)}' if r.get("line") is not None else ""
        if r.get("void"):
            result_cell = f'<span class=mut title="{e(str(r.get("ungraded_reason") or "void"))}">VOID</span>'
        elif r.get("won"):
            result_cell = "W"
        elif r.get("push"):
            result_cell = "P"
        elif r.get("settled") and r.get("won") is False:
            result_cell = "L"
        elif r.get("settled"):
            result_cell = '<span class=mut>graded</span>'
        else:
            result_cell = "—"
        rows_html.append(
            f'<tr><td>{e(str(r.get("slate_date") or ""))}</td>'
            f'<td>{e(str(r.get("source") or ""))}</td>'
            f'<td>{e(str(r.get("market") or ""))} {e(str(r.get("selection") or ""))}{line_suffix}</td>'
            f'<td class=num>{entry_cell}</td>'
            f'<td>{lean_dir_html(r.get("lean"))}</td>'
            f'<td class=num>{edge_cell}</td>'
            f'<td class=num>{clv_cell}</td>'
            f'<td>{result_cell}</td></tr>'
        )
    recent = "".join(rows_html) or '<tr><td class=mut colspan=8>No leans recorded yet.</td></tr>'

    reason_rows = "".join(
        f'<tr><td>{e(reason)}</td><td class=num>{count}</td></tr>'
        for reason, count in reasons.items()
    ) or '<tr><td class=mut colspan=2>No ungradeable leans.</td></tr>'

    proj_rows = "".join(
        f'<tr><td>{e(p["market"])}</td><td class=num>{p["n"]}</td>'
        f'<td class=num>{p["mean_error"]:+.2f}</td><td class=num>{p["mae"]:.2f}</td>'
        f'<td class=num>{p["std"]:.2f}</td></tr>'
        for p in proj_errors
    ) or '<tr><td class=mut colspan=5>No settled projections yet.</td></tr>'

    lean_clv_cards = ""
    if lean_clv:
        by_src = ", ".join(
            f'{e(src)} {v["clv_pts"]:+.1f}pt (n={v["n"]})'
            for src, v in lean_clv["by_source"].items()
        )
        lean_clv_cards = f"""
 <div class=ca-board>{section_head("Model-lean CLV", icon="results")}<div class=body>
   <p class=mut>Closing minus entry implied probability on this model's own recorded leans
   (positive = beat the close). Mean {lean_clv["clv_pts"]:+.2f}pt over {lean_clv["n"]} leans;
   beat the close {lean_clv["beat_close_rate"]}% of the time. {by_src}</p>
 </div></div>"""

    clv_panel = clv_panel_html(clv_summary)
    team_panel = team_accuracy_html(teams)
    market_panel = market_performance_html(market_perf)
    audit_asset_url = None
    if audit_asset_dir is not None:
        asset_dir = Path(audit_asset_dir)
        asset_dir.mkdir(parents=True, exist_ok=True)
        (asset_dir / "prediction-audit.json").write_text(
            json.dumps({"rows": _audit_asset_rows(rows)}, separators=(",", ":"), default=str),
            encoding="utf-8",
        )
        audit_asset_url = "assets/prediction-audit.json"
    audit = prediction_audit_html(rows, external_asset_url=audit_asset_url)

    return f"""{desk_pagehead("Results", sub="Paper track record · CLV · calibration · no fake ROI")}
 <div class=cards>
   <div class=card><div class=k>Record</div><div class=v>{summary["wins"]}-{summary["losses"]}-{summary["pushes"]}</div></div>
   <div class=card><div class=k>Hit rate</div><div class=v>{hit_txt}</div></div>
   <div class=card><div class=k>Brier</div><div class=v>{brier_txt}</div></div>
   <div class=card><div class=k>Lean CLV</div><div class=v>{(f'{lean_clv["clv_pts"]:+.1f}pt' if lean_clv else "—")}</div></div>
   <div class=card><div class=k>Snapshot CLV</div><div class=v>{(f'{clv_summary["clv_pts"]:+.1f}pt' if clv_summary else "—")}</div></div>
   <div class=card><div class=k>Graded / pending / void</div><div class="v v-sm">{summary["total"]} / {pending_n} / {void_n}</div></div>
 </div>
 {lean_clv_cards}
 {clv_panel}
 <div class=cols>
   {team_panel}
   {market_panel}
 </div>
 <div class=cols>
 <div class=ca-board>{section_head("Calibration", icon="results")}<div class=body>
   <p class=mut>Predicted = mean model probability in bucket; Actual carries a Wilson 95% interval.
   ✓ = calibrated within CI, — = under-sampled.</p>
   <div class=table-scroll><table class=sortable><tr><th>Bucket</th><th>n</th><th>Predicted</th><th>Actual (95% CI)</th><th>Gap</th><th>OK</th></tr>{cal_rows}</table></div>
 </div></div>
 <div class=ca-board>{section_head("By source", icon="results")}<div class=body>
   <div class=table-scroll><table><tr><th>Source</th><th>W</th><th>L</th><th>P</th><th>Hit%</th></tr>{src_rows}</table></div>
 </div></div>
 </div>
 <div class=cols>
 <div class=ca-board>{section_head("Projection error", icon="results")}<div class=body>
   <p class=mut>Settled projection leans: model mean vs realized stat (error = projected − actual).
   These distributions calibrate the prop model's sigmas.</p>
   <div class=table-scroll><table><tr><th>Market</th><th>n</th><th>Mean err</th><th>MAE</th><th>Std</th></tr>{proj_rows}</table></div>
 </div></div>
 <div class=ca-board>{section_head("Grading health", icon="results")}<div class=body>
   <p class=mut>Every ungradeable lean carries a reason code; postponed or unresolvable leans void
   after 4 days instead of pending forever.</p>
   <div class=table-scroll><table><tr><th>Ungraded reason</th><th>n</th></tr>{reason_rows}</table></div>
 </div></div>
 </div>
 <div class=ca-board>{section_head("Recent leans", icon="results")}<div class=body>
   <div class=table-toolbar><input class=table-filter type=search placeholder="Filter leans…" data-filter-for="results-recent-table" aria-label="Filter results"></div>
   <div class=table-scroll><table id=results-recent-table class=sortable><tr><th>Date</th><th>Source</th><th>Market</th><th>Entry</th><th>Lean</th><th>Edge</th><th>CLV</th><th>Result</th></tr>{recent}</table></div>
 </div></div>
 {audit}"""


def trends(reports, *, slate=None):
    return trends_section_html(reports, slate=slate)


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

    return f"""{desk_pagehead("Research", sub="Promotion gate · F5 board · Kalshi calibration")}
 <div class=ca-board>{section_head("Promotion gate", icon="research")}<div class=body>
   <div class="vbar {tone}"><b>{pv['verdict']}</b><span>{e('; '.join(pv.get('reasons', [])))}</span></div></div></div>
 {f5_panel}
 <div class=ca-board>{section_head("Kalshi price calibration", icon="research")}<div class=body>
   <div class=table-scroll><table class=sortable><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div></div></div>"""
