"""Edge command center and track-record panels."""
from __future__ import annotations

import html

from mlbmodel.report.html_fmt import edge_grade, section_head

from mlbmodel.report.decision import MKT_LABEL

e = html.escape

_CAT_LABEL = {
    "sharp": "Sharp fusion",
    "game": "Game market",
    "f5": "First 5",
    "prop": "Pitcher prop",
    "pickem": "Pick'em",
}


def _market_label(market: str) -> str:
    key = str(market or "").lower()
    return MKT_LABEL.get(key, key.replace("_", " ").title())


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v <= 1:
        v *= 100
    return f"{v:.0f}%"


def _fmt_line(line) -> str:
    if line is None:
        return "—"
    try:
        return f"{float(line):g}"
    except (TypeError, ValueError):
        return str(line)


def _state_pill(state: str) -> str:
    tone = "pos" if state in {"STRONG", "BET", "MONITOR", "OVER", "UNDER"} else (
        "warnc" if state in {"LEAN", "WATCH", "EDGE"} else "mut"
    )
    return f'<span class="pill {tone}">{e(state)}</span>'


def edge_command_html(
    opportunities: list[dict],
    *,
    clv_summary: dict | None = None,
    limit: int = 12,
) -> str:
    """Hero + ranked edge table for the Today landing."""
    if not opportunities:
        clv_txt = f'{clv_summary["clv_pts"]:+.1f}pt' if clv_summary else "—"
        return (
            '<div class=edge-command><div class=edge-hero>'
            '<div class=edge-hero-stat><span class=k>Actionable edges</span><b>0</b></div>'
            '<div class=edge-hero-stat><span class=k>Historical CLV</span>'
            f'<b>{e(clv_txt)}</b></div>'
            '</div>'
            f'<div class=ca-board>{section_head("Where we have edge today", icon="markets")}<div class=body>'
            '<div class=empty>No priced model edges on this slate yet. '
            'Open <b>Matchups</b> for fair values or check back when lines load.</div></div></div></div>'
        )

    best = opportunities[0]
    best_edge = best.get("edge_pts")
    n_bet = sum(1 for row in opportunities if str(row.get("state")) in {"STRONG", "BET", "MONITOR"})
    n_f5 = sum(1 for row in opportunities if row.get("category") == "f5")
    clv_txt = f'{clv_summary["clv_pts"]:+.1f}pt' if clv_summary else "—"
    clv_n = f'n={clv_summary["n"]}' if clv_summary else "Kalshi history"

    rows = ""
    for row in opportunities[:limit]:
        game = row.get("game") or ""
        game_cell = (
            f'<button class=gamepick onclick="openGame(\'{e(game)}\')">{e(game)}</button>'
            if game and "@" in game
            else f'<span class=mut>{e(str(row.get("context") or "—"))}</span>'
        )
        bet = e(str(row.get("selection") or ""))
        if row.get("line") is not None:
            bet += f' {_fmt_line(row["line"])}'
        edge_pts = row.get("edge_pts")
        edge_cell = (
            f'<b class={edge_grade((edge_pts or 0) / 100)}>{float(edge_pts):+.1f}pt</b>'
            if edge_pts is not None else '<span class=mut>—</span>'
        )
        price = row.get("price") or "—"
        book = f' <span class=mut>{e(str(row["book"]))}</span>' if row.get("book") else ""
        rows += (
            f'<tr><td>{game_cell}</td>'
            f'<td><span class="pill mut">{e(_CAT_LABEL.get(str(row.get("category")), "Edge"))}</span></td>'
            f'<td><b>{e(str(row.get("market_label") or row.get("market") or ""))}</b></td>'
            f'<td>{bet}</td>'
            f'<td class=num>{e(str(price))}{book}</td>'
            f'<td class=num>{_fmt_pct(row.get("model_pct"))}</td>'
            f'<td class=num>{edge_cell}</td>'
            f'<td>{_state_pill(str(row.get("state") or ""))}</td></tr>'
        )

    return f"""<div class=edge-command>
  <div class=edge-hero>
    <div class=edge-hero-stat><span class=k>Best edge</span><b class={edge_grade((best_edge or 0)/100)}>{float(best_edge or 0):+.1f}pt</b>
      <i>{e(str(best.get("market_label") or ""))} · {e(str(best.get("selection") or ""))}</i></div>
    <div class=edge-hero-stat><span class=k>Actionable</span><b>{n_bet}</b><i>BET / MONITOR / STRONG</i></div>
    <div class=edge-hero-stat><span class=k>F5 markets</span><b>{n_f5}</b><i>starter-isolated lines</i></div>
    <div class=edge-hero-stat><span class=k>Historical CLV</span><b>{e(clv_txt)}</b><i>{e(clv_n)} close − entry</i></div>
  </div>
  <div class=ca-board>{section_head("Where we have edge today", icon="markets")}<div class=body>
    <div class=table-scroll><table class=sortable><tr><th>Game</th><th>Type</th><th>Market</th><th>Bet</th>
    <th>Line / price</th><th>Model</th><th>Edge</th><th>State</th></tr>{rows}</table></div>
    <div class=note>Ranked by model edge vs the live or pick&apos;em line. CLV uses settled Kalshi snapshots (close − entry). Open a game for full context.</div>
  </div></div>
</div>"""


def clv_panel_html(clv_summary: dict | None) -> str:
    if not clv_summary:
        return (
            f'<div class=ca-board>{section_head("Closing line value (CLV)", icon="results")}<div class=body>'
            '<div class=empty>No executable snapshot history with entry + close prices yet.</div></div></div>'
        )
    market_rows = "".join(
        f'<tr><td>{e(_market_label(mkt))}</td><td class=num>{pts:+.1f}pt</td></tr>'
        for mkt, pts in sorted((clv_summary.get("by_market") or {}).items(), key=lambda x: -x[1])
    ) or '<tr><td class=mut colspan=2>—</td></tr>'
    wr = clv_summary.get("win_rate")
    wr_txt = f'{wr:.1f}%' if wr is not None else "—"
    return f"""<div class=ca-board>{section_head("Closing line value (CLV)", icon="results")}<div class=body>
  <div class="cards cards--tight">
    <div class=card><div class=k>Mean CLV</div><div class=v>{clv_summary["clv_pts"]:+.1f}pt</div></div>
    <div class=card><div class=k>Sample</div><div class=v>{clv_summary["n"]}</div></div>
    <div class=card><div class=k>Win rate</div><div class=v>{wr_txt}</div></div>
    <div class=card><div class=k>Markets w/ CLV</div><div class=v>{len(clv_summary.get("by_market") or {})}</div></div>
  </div>
  <div class=table-scroll><table><tr><th>Market</th><th>Mean CLV</th></tr>{market_rows}</table></div>
  <div class=note>CLV = close implied probability minus entry probability on point-in-time Kalshi snapshots. Positive CLV means we beat the closing line.</div>
</div></div>"""


def team_accuracy_html(teams: list[dict], *, title: str = "Teams we predict best") -> str:
    if not teams:
        return (
            f'<div class=ca-board>{section_head(title, icon="results")}<div class=body>'
            '<div class=empty>Need at least 3 settled moneyline leans per team.</div></div></div>'
        )
    rows = "".join(
        f'<tr><td><b>{e(t["team"])}</b></td><td>{t["w"]}-{t["l"]}-{t["p"]}</td>'
        f'<td class=num>{t["hit_rate"]:.1f}%</td><td class=mut>{t["n"]} leans</td></tr>'
        for t in teams[:15]
    )
    return f"""<div class=ca-board>{section_head(title, icon="results")}<div class=body>
  <div class=table-scroll><table class=sortable><tr><th>Team</th><th>Record</th><th>Hit%</th><th>Sample</th></tr>{rows}</table></div>
  <div class=note>ML and F5 moneyline leans only — where the model took a side on a team to win.</div>
</div></div>"""


def market_performance_html(markets: list[dict]) -> str:
    if not markets:
        return (
            f'<div class=ca-board>{section_head("Edge by market", icon="markets")}<div class=body>'
            '<div class=empty>Not enough settled leans per market type yet.</div></div></div>'
        )
    rows_out = []
    for m in markets:
        avg_edge = f'{m["avg_edge_pts"]:.1f}pt' if m.get("avg_edge_pts") is not None else "—"
        rows_out.append(
            f'<tr><td>{e(m["source"])}</td><td>{e(m["market_label"])}</td>'
            f'<td>{m["w"]}-{m["l"]}-{m["p"]}</td>'
            f'<td class=num>{m["hit_rate"]:.1f}%</td>'
            f'<td class=num>{avg_edge}</td>'
            f'<td class=mut>{m["n"]}</td></tr>'
        )
    rows = "".join(rows_out)
    return f"""<div class=ca-board>{section_head("Edge by market", icon="markets")}<div class=body>
  <div class=table-scroll><table class=sortable><tr><th>Source</th><th>Market</th><th>Record</th>
  <th>Hit%</th><th>Avg edge</th><th>n</th></tr>{rows}</table></div>
  <div class=note>Where the model has historically found value — props, F5, game markets, and pick&apos;em.</div>
</div></div>"""
