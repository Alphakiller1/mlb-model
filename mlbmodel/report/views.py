"""Report section HTML builders (Today, Props, Results, Trends, Research)."""
from __future__ import annotations

import html

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
from mlbmodel.report.html_fmt import display as _display, edge_grade as _edge_grade, section_head, lean_dir_html
from mlbmodel.report.html_fmt import (
    pct_chip_html,
)
from mlbmodel.report.matchup import _logo
from mlbmodel.report.shell import slate_view_label
from mlbmodel.report.props_ui import pitcher_prop_deck, prop_channel_counts
from mlbmodel.report.game_keys import assign_slate_keys, parse_game_key
from mlbmodel.report.trends_ui import trends_section_html

e = html.escape


def _projected_score(g):
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


def _today_spotlight(ok):
    return max(ok, key=lambda g: abs(float(g.get("margin") or 0)), default=None)


def _fmt_num(value, digits=1, suffix=""):
    if value is None:
        return "&mdash;"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return e(str(value))


def _fmt_pct(value, digits=0):
    if value is None:
        return "&mdash;"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return e(str(value))
    if abs(v) <= 1:
        v *= 100
    return f"{v:.{digits}f}%"


def _fmt_price(value):
    if isinstance(value, int):
        return f"{value:+d}"
    if value is None:
        return "&mdash;"
    try:
        return f"{int(value):+d}"
    except (TypeError, ValueError):
        return e(str(value))


def _fmt_line(value):
    if value is None:
        return ""
    try:
        return f" {float(value):g}"
    except (TypeError, ValueError):
        return f" {e(str(value))}"


def _pct_width(value):
    if value is None:
        return 0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    if abs(v) <= 1:
        v *= 100
    return max(2, min(100, int(round(v))))


def _state_tone(state):
    key = str(state or "").strip().upper()
    if key in {"STRONG", "BET", "PLAY", "OVER", "UNDER"}:
        return "play"
    if key in {"MONITOR", "WATCH", "LEAN", "EDGE", "REVIEW", "NEEDS PRICE", "MODEL"}:
        return "monitor"
    if key in {"AVOID", "PASS", "CONFLICT", "NO PLAY"}:
        return "avoid"
    return "noedge"


def _state_badge(state):
    label = str(state or "No edge").replace("_", " ").title()
    if label.upper() in {"BET", "OVER", "UNDER"}:
        label = label.upper()
    return f'<span class=command-state data-tone="{_state_tone(state)}">{e(label)}</span>'


def _team_pair_from_game(game):
    if "@" not in str(game or ""):
        return None, None
    away, home = str(game).split("@", 1)
    return away.strip().upper(), home.strip().upper()


def _team_marks(away, home):
    return (
        f'<span class=command-team-mark>{_logo(away, "tlogo sm")}<b>{e(away)}</b></span>'
        f'<span class=command-at>@</span>'
        f'<span class=command-team-mark>{_logo(home, "tlogo sm")}<b>{e(home)}</b></span>'
    )


def _projected_score_parts(g):
    try:
        total = float(g.get("total") or 0)
        margin = float(g.get("margin") or 0)
    except (TypeError, ValueError):
        return None, None
    if total <= 0:
        return None, None
    home_runs = (total + margin) / 2
    away_runs = total - home_runs
    return away_runs, home_runs


def _opportunity_row(op, idx=1, *, compact=False):
    game = str(op.get("game") or "")
    away, home = _team_pair_from_game(game)
    context = str(op.get("context") or "")
    category = str(op.get("category") or "model").replace("_", " ").title()
    market = str(op.get("market_label") or op.get("market") or "Market")
    selection = str(op.get("selection") or "").upper()
    line = _fmt_line(op.get("line"))
    price = _fmt_price(op.get("price"))
    model_pct = op.get("model_pct")
    edge = op.get("edge_pts")
    market_pct = None
    if model_pct is not None and edge is not None:
        try:
            market_pct = float(model_pct) - float(edge)
        except (TypeError, ValueError):
            market_pct = None
    ev = f'{(float(edge or 0) / 100):+.3f}u' if edge is not None else "&mdash;"
    headline = game if game and away and home else (context or str(op.get("label") or "Model signal"))
    sub = (
        f"{category} &middot; {context or 'model vs market'}"
        if game else f"{category} &middot; {str(op.get('book') or 'projection')}"
    )
    marks = _team_marks(away, home) if away and home else (
        f'<span class=command-index>{idx:02d}</span>'
    )
    tag = "button" if away and home else "div"
    action = f' type=button onclick="openGame(\'{e(game)}\')"' if tag == "button" else ""
    density = " command-matrix-row--compact" if compact else ""
    return f"""<{tag} class="command-matrix-row{density}"{action}>
      <span class=command-row-head>
        <span class=command-teamline>{marks}</span>
        <span class=command-row-title><strong>{e(headline)}</strong><span>{sub}</span></span>
      </span>
      <span class=command-pick><span>Line</span><strong>{e(market)} {e(selection)}{line} &middot; {price}</strong></span>
      <span class=command-metric><span>Model fair</span><strong>{_fmt_pct(model_pct)}</strong><i class=command-bar style="--w:{_pct_width(model_pct)}%"><b></b></i></span>
      <span class=command-metric><span>Market fair</span><strong>{_fmt_pct(market_pct)}</strong><i class=command-bar style="--w:{_pct_width(market_pct)}%"><b></b></i></span>
      <span class=command-metric><span>EV/unit</span><strong>{ev}</strong></span>
      {_state_badge(op.get("state"))}
    </{tag}>"""


def _slate_projection_row(g, idx=1):
    game = g.get("key") or f'{g["away"]}@{g["home"]}'
    margin = g.get("margin")
    total = g.get("total")
    lean = str(g.get("lean") or "Model")
    op = {
        "game": game,
        "category": "projection",
        "context": f'{g.get("asp") or "TBD"} vs {g.get("hsp") or "TBD"}',
        "market_label": "Projected score",
        "selection": lean,
        "line": None,
        "price": None,
        "model_pct": g.get("ph"),
        "edge_pts": abs(float(margin or 0)) if margin is not None else None,
        "state": "Monitor" if total else "No edge",
    }
    return _opportunity_row(op, idx)


def _summary_stat(label, value, note=""):
    note_html = f"<span>{e(note)}</span>" if note else ""
    return f'<div class=command-stat><span>{e(label)}</span><strong>{value}</strong>{note_html}</div>'


def _freshness_rail(sync, sync_label, nsharp, gate):
    verdict = str((gate or {}).get("verdict") or "HOLD")
    reasons = "; ".join((gate or {}).get("reasons") or []) or "promotion gate requires evidence"
    exact = (sync or {}).get("status") == "exact"
    return f"""<div class=command-card>
      <div class=command-section-head><strong>Freshness rail</strong></div>
      <div class=command-rail>
        <div class=command-rail-item data-tone="{'play' if exact else 'monitor'}">
          <span class=command-status-dot></span>
          <div><strong>Slate matched</strong><span>{e(sync_label)} MLBMA schedule state</span></div>
        </div>
        <div class=command-rail-item data-tone="{'play' if nsharp else 'monitor'}">
          <span class=command-status-dot></span>
          <div><strong>Odds intelligence</strong><span>{nsharp} sharp or market-disagreement signals on slate</span></div>
        </div>
        <div class=command-rail-item data-tone="{'play' if verdict == 'PROMOTE' else 'monitor'}">
          <span class=command-status-dot></span>
          <div><strong>Promotion gate</strong><span>{e(verdict)} &middot; {e(reasons)}</span></div>
        </div>
        <div class=command-rail-item data-tone="monitor">
          <span class=command-status-dot></span>
          <div><strong>Projection grading</strong><span>Capture, close, final, and performance sample remain visible</span></div>
        </div>
      </div>
    </div>"""


def _proof_drawer(ok, sd, sync_label, sharp_by_pk):
    top = _today_spotlight(ok)
    if not top:
        return """<section class="command-screen command-proof">
      <div class=command-empty>No matchup proof drawer until slate inputs load.</div>
    </section>"""
    game = top.get("key") or f'{top["away"]}@{top["home"]}'
    away_runs, home_runs = _projected_score_parts(top)
    score = (
        f'{e(top["away"])} {_fmt_num(away_runs)} &middot; {e(top["home"])} {_fmt_num(home_runs)}'
        if away_runs is not None and home_runs is not None else "Projected score pending"
    )
    sharp_count = len(sharp_by_pk.get(top.get("pk"), [])) if top.get("pk") is not None else 0
    home_prob = _fmt_pct(top.get("ph"))
    away_prob = _fmt_pct((1 - float(top.get("ph"))) if top.get("ph") is not None else None)
    return f"""<section class="command-screen command-proof">
      <div class=command-proof-card>
        <div class=command-proof-head>
          <div class=command-proof-title>
            <span class=command-teamline>{_team_marks(top["away"], top["home"])}</span>
            <div><strong>{e(game)}</strong><span>{e(str(top.get("asp") or "TBD"))} vs {e(str(top.get("hsp") or "TBD"))} &middot; {e(str(top.get("time") or "TBD"))}</span></div>
          </div>
          <span class=command-state data-tone=monitor>Projected &middot; ungraded</span>
        </div>
        <div class=command-split-grid>
          <div class=command-scoreline><span>Projected score</span><strong>{score}</strong><span>Run gap {_fmt_num(top.get("margin"), 1, " R")} &middot; total {_fmt_num(top.get("total"), 1)}</span></div>
          <div class=command-ticket-strip>
            <div class=command-inline-set><span class=command-micro>Locked inputs</span><span class=command-badge>slate {e(sd or "pending")}</span><span class=command-badge>{e(sync_label)}</span></div>
            <span>Receipt-style state for every generated projection: capture, close, final, graded.</span>
          </div>
        </div>
      </div>
      <div class=command-proof-grid>
        <div class=command-card>
          <div class=command-section-head><strong>Factor stack</strong><span>Run deltas from model-facing inputs</span></div>
          <div class=command-factor-list>
            <div class=command-factor-row><div><strong>Win model split</strong><span>{e(top["away"])} {away_prob} vs {e(top["home"])} {home_prob}</span></div><strong>{e(str(top.get("lean") or "Lean"))}</strong></div>
            <div class=command-factor-row><div><strong>Starter contact profile</strong><span>{e(str(top.get("asp") or "TBD"))} vs {e(str(top.get("hsp") or "TBD"))}</span></div><strong>{_fmt_num(top.get("afip"))}/{_fmt_num(top.get("hfip"))}</strong></div>
            <div class=command-factor-row><div><strong>Run environment</strong><span>Total projection and run gap stay separated</span></div><strong>{_fmt_num(top.get("total"), 1)}</strong></div>
            <div class=command-factor-row><div><strong>Market pressure</strong><span>Sharp or disagreement signals attached to game</span></div><strong>{sharp_count}</strong></div>
          </div>
        </div>
        <div class=command-card>
          <div class=command-section-head><strong>Projection grading</strong></div>
          <div class=command-timeline>
            <div><span class=command-status-dot></span><p><strong>Prediction logged</strong><span>Projection, market price, and source versions captured</span></p></div>
            <div><span class=command-status-dot></span><p><strong>Closing line pending</strong><span>CLV waits for a closing snapshot</span></p></div>
            <div><span class=command-status-dot></span><p><strong>Final outcome pending</strong><span>Auto grade runs after MLB final is present</span></p></div>
            <div><span class=command-status-dot></span><p><strong>Performance sample</strong><span>Brier, ROI, calibration, and abstain accuracy</span></p></div>
          </div>
        </div>
      </div>
    </section>"""


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
def today(
    slate,
    sd,
    sharp_by_pk,
    sync=None,
    edge_command="",
    *,
    opportunities=None,
    clv_summary=None,
    gate=None,
):
    ok = [g for g in slate if not g.get("err")]
    n = len(ok)
    nsharp = sum(len(v) for v in sharp_by_pk.values())
    sync = sync or {}
    sync_label = "Exact" if sync.get("status") == "exact" else (
        "Live fallback" if sync.get("status") == "fallback" else "Untracked"
    )
    opportunities = opportunities or []
    priced_markets = sum(1 for op in opportunities if op.get("price") not in {None, ""})
    conflicts = sum(1 for op in opportunities if _state_tone(op.get("state")) == "avoid")
    clv_cell = (
        f'{float(clv_summary["clv_pts"]):+.1f}pt'
        if clv_summary and clv_summary.get("clv_pts") is not None else "pending"
    )
    if opportunities:
        queue_rows = "".join(
            _opportunity_row(op, idx) for idx, op in enumerate(opportunities[:3], start=1)
        )
        matrix_rows = "".join(
            _opportunity_row(op, idx, compact=True)
            for idx, op in enumerate(opportunities[:3], start=1)
        )
    else:
        queue_rows = "".join(
            _slate_projection_row(g, idx) for idx, g in enumerate(ok[:3], start=1)
        ) or '<div class=command-empty>No slate loaded.</div>'
        matrix_rows = "".join(
            _slate_projection_row(g, idx) for idx, g in enumerate(ok[:3], start=1)
        ) or '<div class=command-empty>No prediction rows available.</div>'
    summary = "".join([
        _summary_stat("Games loaded", n, f"slate {sd or 'pending'}"),
        _summary_stat("Priced markets", priced_markets, "live or cached books"),
        _summary_stat("Model conflicts", conflicts, "pass/avoid states"),
        _summary_stat("Projection grades due", len(opportunities), f"CLV {clv_cell}"),
    ])
    command_rail = _freshness_rail(sync, sync_label, nsharp, gate)
    proof = _proof_drawer(ok, sd, sync_label, sharp_by_pk)
    return f"""<div class=model-command>
  <section class=command-screen aria-label="Slate command center">
    <div class=command-topbar>
      <div class=command-brand-lockup>
        <span class=command-brand-mark aria-hidden=true><svg viewBox="0 0 36 36"><path d="M18 5 C21 13 24 20 33 31 L3 31 C12 20 15 13 18 5 Z"></path></svg></span>
        <div class=command-brand-copy><strong>MLB Model</strong><span>Slate command center</span></div>
      </div>
      <div class=command-inline-set>
        <span class=command-badge>MLBMA {e(sync_label)}</span>
        <span class=command-badge>{nsharp} sharp signals</span>
        <span class=command-badge>Gate {e(str((gate or {}).get("verdict") or "HOLD"))}</span>
      </div>
    </div>
    <div class=command-title-block>
      <span class=command-kicker>{e(slate_view_label(sd))}</span>
      <h2>Actionable slate, not just a game list</h2>
    </div>
    <div class=command-summary-grid>{summary}</div>
    <div class=command-content-grid>
      <div class=command-card>
        <div class=command-section-head>
          <strong>Decision queue</strong>
          <span>Ranked by model edge, price quality, and data trust</span>
        </div>
        <div class=command-queue>{queue_rows}</div>
      </div>
      {command_rail}
    </div>
  </section>
  <section class="command-screen edge-command" aria-label="Prediction matrix">
    <div class=command-section-head>
      <div><span class=command-kicker>Prediction matrix</span>
      <h2>Every row separates projection, market, edge, and state</h2></div>
      <div class=command-inline-set><span class=command-badge>Model v1 expected-runs</span><span class=command-badge>Where we have edge today</span></div>
    </div>
    <div class=command-matrix-labels><span>Game</span><span>Line</span><span>Model fair</span><span>Market fair</span><span>EV/unit</span><span>State</span></div>
    <div class=command-queue>{matrix_rows}</div>
  </section>
  {proof}
</div>
<div class=command-source-html hidden>{edge_command}</div>"""
    """
 {hero}
 <p class=viewhero-sub><b>{n}</b> games<span class=vh-dot></span>slate <b>{e(sd or "—")}</b><span class=vh-dot></span><b>{nsharp}</b> sharp signals<span class=vh-dot></span>MLBMA sync <b>{e(sync_label)}</b></p>
 {edge_command}
 <div class=ca-board>{section_head("Slate", icon="slate")}<div class=body>
   <div class=slate-card-grid>{rows or '<div class=empty>No slate loaded.</div>'}</div>
 </div></div>
    """


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
    deck = pitcher_prop_deck(pitchers, pickem_sources)
    return f"""<h2>Pitcher Props</h2>
 <div class=cards>
   <div class=card><div class=k>Starters</div><div class=v>{len(pitchers)}</div></div>
   <div class=card><div class=k>Book lines</div><div class=v>{book_n}</div></div>
   <div class=card><div class=k>Fantasy lines</div><div class=v>{fantasy_n}</div></div>
 </div>
 {freshness}
 {deck}"""


def results(reader):
    result = reader.get(
        "model_leans?select=lean_id,slate_date,game_pk,source,market,selection,line,"
        "model_prob,model_value,edge,lean,won,push,settled,entry_odds,recorded_at,"
        "void,ungraded_reason,closing_odds,clv_pts,realized_value"
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

    return f"""<h2>Results</h2>
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
 </div></div>"""


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

    return f"""<h2>Research</h2>
 <div class=ca-board>{section_head("Promotion gate", icon="research")}<div class=body>
   <div class="vbar {tone}"><b>{pv['verdict']}</b><span>{e('; '.join(pv.get('reasons', [])))}</span></div></div></div>
 {f5_panel}
 <div class=ca-board>{section_head("Kalshi price calibration", icon="research")}<div class=body>
   <div class=table-scroll><table class=sortable><tr><th>Bucket</th><th>n</th><th>Avg price</th><th>Actual win%</th><th>Gap</th></tr>{crows}</table></div></div></div>"""
