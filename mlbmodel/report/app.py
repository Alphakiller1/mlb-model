"""
mlbmodel.report.app — the unified MLB Model product shell.

ONE coherent application (not separate dashboards) with a 7-section information architecture:
Today · Matchups · Markets · Props · Results · Research. Workflow:
discover -> inspect -> evaluate -> compare -> decide -> track -> review. Each section follows the
page hierarchy: context -> conclusion -> price/opportunity -> evidence -> risks -> action ->
methodology. The user never sees which repo a number came from — it reads as one platform.

    python -m mlbmodel.report.app --game NYY@BOS --out app.html [--no-fetch]
"""
from __future__ import annotations

import argparse
import html
import logging
import os
from pathlib import Path

from mlbmodel.baseball.repository import DataRepository
from mlbmodel.market.props import load_prop_board, market_report
from mlbmodel.market.quotes import load_board
from mlbmodel.market import prizepicks, underdog, sleeper
from mlbmodel import settings
from mlbmodel.props.model import build_pitcher_board
from mlbmodel.report import chase_theme
from mlbmodel.trends import build_slate_reports
from mlbmodel.report.matchup import (
    _CSS,
    _promotion,
    build_report,
    matchup_summary_html,
    report_body,
)
from mlbmodel.report.decision import collect_market_plays as _collect_market_plays, markets_html as _markets
from mlbmodel.analytics.edge_intel import clv_from_snapshots, collect_slate_opportunities
from mlbmodel.report.edge_ui import edge_command_html
from mlbmodel.leans.decision_calibration import thresholds_from_leans
from mlbmodel.leans.record import collect_leans, record_leans
from mlbmodel.market.pickem import (
    build_pickem_rows,
    build_pickem_rows_from_boards,
    load_pickem_lines,
    pickem_market_reports,
)
from mlbmodel.report.shell import NAV as _NAV, shell_css, shell_js, slate_view_label
from mlbmodel.report.views import (
    props as _props,
    research as _research,
    results as _results,
    slate as _slate,
    today as _today,
    trends as _trends,
)
from mlbmodel.storage.supabase import SupabaseReader

from mlbmodel.report.static_assets import publish_assets

e = html.escape
log = logging.getLogger(__name__)

# Re-exported for tests and downstream imports.
__all__ = ["_NAV", "_props", "build_app", "main"]


def build_app(featured_game, *, fetch=True, data_dir=None):
    repo = DataRepository(data_dir)
    reader = SupabaseReader()
    cache_dir = Path(data_dir) if data_dir else settings.CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    slate_frame = repo.slate()
    slate_date = (
        str(slate_frame.iloc[0].get("Slate_Date", ""))[:10]
        if slate_frame is not None and len(slate_frame)
        else str((repo.sync_manifest() or {}).get("slate_date") or "")[:10]
    )
    board = load_board(
        fetch=fetch,
        cache_path=cache_dir / "odds_latest.json",
        slate_date=slate_date or None,
    )
    prop_prices = load_prop_board(
        fetch=fetch, cache_path=cache_dir / "prop_odds_latest.json"
    )
    pp_board = prizepicks.board_by_player(
        load_pickem_lines(
            prizepicks, cache_dir / "prizepicks_lines.json", fetch=fetch
        )
    )
    ud_board = prizepicks.board_by_player(
        load_pickem_lines(
            underdog, cache_dir / "underdog_lines.json", fetch=fetch
        )
    )
    sl_board = prizepicks.board_by_player(
        load_pickem_lines(
            sleeper, cache_dir / "sleeper_lines.json", fetch=fetch
        )
    )
    gate = _promotion(reader)
    pitchers = build_pitcher_board(repo)
    promotion_status = (
        "PROMOTE" if gate.get("verdict") == "PROMOTE" else "HOLD/ABSTAIN"
    )
    pickem_sources = [
        ("PrizePicks", pp_board),
        ("Underdog", ud_board),
        ("Sleeper", sl_board),
    ]
    for pitcher in pitchers:
        reports = market_report(
            pitcher,
            prop_prices,
            promotion_status=promotion_status,
        )
        if not reports:
            reports = pickem_market_reports(pitcher, pickem_sources)
        pitcher["market_report"] = reports
        if reports:
            pitcher["market_state"] = str(reports[0].get("state") or "NO MARKET")
    slate, sd = _slate(repo, pitchers)
    sync = repo.sync_manifest()
    games = [f'{g["away"]}@{g["home"]}' for g in slate if not g.get("err")]
    if games and featured_game.upper() not in games:
        featured_game = games[0]
    pks = {g["pk"] for g in slate if "pk" in g}
    sharp_by_pk = {}
    for game in slate:
        if game.get("err") or "pk" not in game:
            continue
        try:
            quotes = board.game_quotes(game["away"], game["home"])
        except Exception:
            quotes = []
        candidates = [
            q for q in quotes
            if q.sharp_divergence is not None and q.sharp_divergence >= 0.006
            and q.sharp_book_count >= 1 and q.soft_book_count >= 1
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda q: q.sharp_divergence)
        sharp_by_pk[game["pk"]] = [{
            "market_type": best.market,
            "selection": best.selection,
            "divergence": round(best.sharp_divergence, 4),
            "sharp_novig_prob": best.sharp_probability,
            "soft_novig_prob": best.soft_probability,
            "n_sharp_books": best.sharp_book_count,
            "n_soft_books": best.soft_book_count,
            "line_current": best.best_odds,
            "steam_flag": best.sharp_divergence >= 0.05,
        }]
    if not sharp_by_pk:
        for s in reader.get(
            "sharp_signals?select=game_pk,market_type,selection,divergence,steam_flag,"
            "sharp_novig_prob,soft_novig_prob,n_sharp_books,n_soft_books,line_current&limit=200"
        ).rows:
            if s.get("game_pk") in pks:
                sharp_by_pk.setdefault(s["game_pk"], []).append(s)

    matchup_reports = []
    model_by_pk = {}
    for game in slate:
        game_name = f'{game["away"]}@{game["home"]}'
        try:
            r = build_report(
                game["away"], game["home"], fetch=False, data_dir=data_dir,
                board=board, reader=reader, gate=gate,
                pitcher_rows=[
                    pitcher for pitcher in pitchers
                    if pitcher.get("team") in {game["away"], game["home"]}
                ],
            )
            if "pk" in game:
                model_by_pk[game["pk"]] = r.get("markets", [])
            full_terminal = report_body(r)
            if game_name == featured_game.upper():
                report = f'<div class=matchup-body>{full_terminal}</div>'
            else:
                report = (
                    f'<div class=matchup-body>{matchup_summary_html(r)}</div>'
                    f'<template class=matchup-full-src>{full_terminal}</template>'
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
        f'<p class=pagehead-sub>{e(sd or "Slate pending")}</p></div>'
        f'<select id=gameSelect aria-label="Matchup" onchange="switchGame(this.value)">{options}</select></div>'
        f'{"".join(matchup_reports)}'
    )

    pkmap = {g["pk"]: f'{g["away"]}@{g["home"]}' for g in slate if "pk" in g}
    try:
        slate_reports = build_slate_reports(
            repo,
            pitchers=pitchers,
            model_by_pk=model_by_pk,
            pkmap=pkmap,
            top_n=10,
        )
    except Exception:
        slate_reports = []
    f5_board = [
        (pkmap.get(pk, str(pk)), m)
        for pk, rows in model_by_pk.items()
        for m in rows
        if str(m.get("market") or "").startswith("f5_")
    ]
    matchup_markets_by_pk = dict(model_by_pk)
    cal_result = reader.get(
        "model_leans?settled=eq.true&select=edge,won,push,source,settled&limit=2000"
    )
    decision_thresholds = thresholds_from_leans(
        cal_result.rows if not cal_result.error else []
    )
    market_plays = _collect_market_plays(
        slate, sharp_by_pk, model_by_pk, decision_thresholds
    )
    pickem_rows = build_pickem_rows_from_boards(pitchers, pickem_sources)
    if not pickem_rows:
        pickem_rows = build_pickem_rows(pitchers)
    flat_props = []
    for pitcher in pitchers:
        for report in pitcher.get("market_report") or []:
            flat_props.append({
                "pitcher": pitcher.get("pitcher"),
                "game_pk": pitcher.get("game_pk"),
                **report,
                "model_mean": (pitcher.get("projections") or {}).get(report.get("prop"), {}).get("mean"),
            })

    clv_result = reader.get(
        "prediction_market_snapshots?settled=eq.true&won=not.is.null"
        "&entry_prob=not.is.null&implied_probability=not.is.null"
        "&select=market_type,entry_prob,implied_probability,won&limit=5000"
    )
    clv_summary = clv_from_snapshots(clv_result.rows if not clv_result.error else [])

    opportunities = collect_slate_opportunities(
        pkmap=pkmap,
        market_plays=market_plays,
        model_by_pk=model_by_pk,
        prop_reports=flat_props,
        pickem_rows=pickem_rows,
    )
    edge_command = edge_command_html(opportunities, clv_summary=clv_summary)

    if sd:
        try:
            lean_rows = collect_leans(
                slate_date=str(sd)[:10],
                market_plays=market_plays,
                pickem_rows=pickem_rows,
                prop_reports=flat_props,
                matchup_markets_by_pk=matchup_markets_by_pk,
                pitchers=pitchers,
                pkmap=pkmap,
            )
            written = record_leans(lean_rows)
            if written:
                sources = {}
                for row in lean_rows:
                    sources[row["source"]] = sources.get(row["source"], 0) + 1
                log.info(
                    "recorded %s model leans for %s (%s)",
                    written,
                    sd,
                    ", ".join(f"{k}={v}" for k, v in sorted(sources.items())),
                )
            elif lean_rows and os.getenv("SUPABASE_URL"):
                log.error(
                    "model lean record wrote 0 rows (%s candidates); check SUPABASE_KEY and migrations",
                    len(lean_rows),
                )
        except Exception as exc:
            log.error("model lean record failed: %s", exc)

    views = {
        "today": _today(slate, sd, sharp_by_pk, sync, edge_command),
        "matchups": matchups,
        "trends": _trends(slate_reports),
        "markets": _markets(slate, sharp_by_pk, model_by_pk, decision_thresholds),
        "props": _props(pitchers, prop_prices, pp_board, ud_board, sl_board),
        "results": _results(reader),
        "research": _research(reader, gate, f5_board, clv_summary),
    }
    nav_items = [
        (k, slate_view_label(sd) if k == "today" else lbl, f"show('{k}')")
        for k, lbl in _NAV
    ]
    sections = "".join(
        f'<section class="view{" on" if k == "today" else ""}" id="v-{k}">{html_}</section>'
        for k, html_ in views.items()
    )
    deployment_notice = os.getenv("MLB_MODEL_DEPLOYMENT_NOTICE", "").strip()
    sync_notice = str(sync.get("message") or "").strip()
    notice_text = " ".join(part for part in (deployment_notice, sync_notice) if part)
    notice = (
        f'<div class=deployment-notice>{e(notice_text)}</div>'
        if notice_text else ""
    )
    chase_nav = chase_theme.nav_html(nav_items, "today", "MLB Model", status=(sd or "Live"))
    return (
        f'<!DOCTYPE html><html lang=en class=view-opening><head><meta charset=utf-8>'
        f'<meta name=viewport content="width=device-width,initial-scale=1">'
        f'<title>MLB Model — Chase Analytics</title>'
        f'<style>{chase_theme.theme_css()}{_CSS}{shell_css()}</style></head>'
        f'<body class="platform-dashboard opening-dashboard">'
        f'{chase_nav}'
        f'<main id=main class=ca-page-shell>{notice}{sections}</main>'
        f'<script>{shell_js()}</script></body></html>'
    )


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Unified MLB Model product shell.")
    ap.add_argument("--game", default="NYY@BOS", help="featured matchup")
    ap.add_argument("--out", default="mlb_model_app.html")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--data-dir")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build_app(args.game, fetch=not args.no_fetch, data_dir=args.data_dir),
        encoding="utf-8",
    )
    published = publish_assets(out.parent)
    print(f"wrote {out}" + (f" (+{published} icons)" if published else ""))


if __name__ == "__main__":
    main()
