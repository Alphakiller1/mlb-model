"""Aggregate top leans for the summary strip."""
from __future__ import annotations

import html

e = html.escape


def top_leans_html(
    *,
    market_plays: list[dict],
    pickem_rows: list[dict],
    prop_reports: list[dict],
    limit: int = 6,
) -> str:
    items: list[tuple[float, str, str, str]] = []

    for play in market_plays:
        verdict = str(play.get("verdict") or "")
        if verdict not in {"STRONG", "BET", "LEAN"}:
            continue
        score = float(play.get("score") or 0)
        game = str(play.get("game") or "")
        label = f'{verdict} · {play.get("mkt_type", "")} {play.get("sel", "")}'
        items.append((score, label, game, "markets"))

    for row in pickem_rows:
        p = row.get("p_over")
        if p is None:
            continue
        dist = abs(float(p) - 0.5)
        label = f'{row.get("lean", "")} {row.get("prop", "")} {row.get("line", "")}'
        pitcher = str(row.get("pitcher") or "")
        items.append((dist * 100, label, pitcher, "props"))

    for rep in prop_reports:
        edge = rep.get("edge")
        if edge is None:
            continue
        edge_f = float(edge)
        if edge_f <= 0:
            continue
        pts = edge_f * 100 if abs(edge_f) <= 1 else edge_f
        label = f'{rep.get("side", "")} {rep.get("prop", "")} {rep.get("line", "")}'
        pitcher = str(rep.get("pitcher") or "")
        items.append((pts, label, pitcher, "props"))

    items.sort(key=lambda x: -x[0])
    if not items:
        return '<div class=top-leans><div class=mut>No graded leans on this slate yet.</div></div>'

    cards = []
    for score, label, ctx, view in items[:limit]:
        onclick = f"show('{view}')"
        if view == "matchups" and "@" in ctx:
            onclick = f"openGame('{e(ctx)}')"
        cards.append(
            f'<div class=top-lean><div class=k>{e(view.title())}</div>'
            f'<button type=button onclick="{onclick}"><span class=v>{e(label)}</span></button>'
            f'<div class=mut>{e(ctx)} · {score:.1f}</div></div>'
        )
    return '<div class=top-leans aria-label="Top model leans">' + "".join(cards) + "</div>"
