"""Orchestration: turn one game into a full situational-trends report.

``build_situational_report`` is the single entry point used by the CLI, the model feature
pipeline, and any UI. It resolves context → runs detectors → ranks/scores → computes per-team
edge scores → engineers model features → writes the narrative, returning one
:class:`SituationalEdge`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mlbmodel.sources.sync_mlbma import matchup_keys
from mlbmodel.trends.context import SituationalContext
from mlbmodel.trends.detectors import run_detectors
from mlbmodel.trends.features import trend_features
from mlbmodel.trends.narrative import build_narrative
from mlbmodel.trends.scoring import rank_and_score, team_edge_scores
from mlbmodel.trends.prop_detectors import trends_for_game
from mlbmodel.trends.types import SituationalEdge

if TYPE_CHECKING:  # annotation-only; avoids a runtime import cycle with baseball.repository
    from mlbmodel.baseball.repository import DataRepository

logger = logging.getLogger("mlbmodel.trends")


def build_situational_report(
    repo: DataRepository, away: str, home: str, *, top_n: int = 8
) -> SituationalEdge:
    ctx = SituationalContext.resolve(repo, away, home)
    trends = rank_and_score(run_detectors(ctx))[:top_n]
    away_edge, home_edge, lean = team_edge_scores(away, home, trends)

    notes: list[str] = []
    if not ctx.slate_date:
        notes.append("Game not found on the loaded slate; context may be incomplete.")
    if ctx.reliever_log.empty:
        notes.append("Reliever log unavailable — bullpen-fatigue trends disabled.")

    edge = SituationalEdge(
        game=f"{away}@{home}",
        slate_date=ctx.slate_date,
        away=away,
        home=home,
        away_edge_score=away_edge,
        home_edge_score=home_edge,
        edge_lean=lean,
        trends=trends,
        features=trend_features(away, home, trends, away_edge, home_edge),
        notes=notes,
    )
    edge.narrative = build_narrative(edge, top_n=top_n)
    logger.info(
        "trends %s: %d trends, edge %s (%.0f/%.0f)",
        edge.game, len(trends), lean, away_edge, home_edge,
    )
    return edge


def _enrich_with_prop_and_market_trends(
    edge: SituationalEdge,
    repo: DataRepository,
    away: str,
    home: str,
    *,
    pitchers: list[dict] | None,
    model_rows: list[dict] | None,
    top_n: int,
) -> SituationalEdge:
    """Merge situational, prop/fantasy, and market trends; re-score edge."""
    ctx = SituationalContext.resolve(repo, away, home)
    situational = run_detectors(ctx)
    game_pitchers = [
        p for p in (pitchers or []) if str(p.get("team") or "") in {away, home}
    ]
    merged = trends_for_game(
        situational=situational,
        pitchers=game_pitchers,
        model_rows=model_rows or [],
        game=edge.game,
        away=away,
        home=home,
    )
    cap = top_n + 6 if (pitchers or model_rows) else top_n
    trends = rank_and_score(merged)[:cap]
    away_edge, home_edge, lean = team_edge_scores(away, home, trends)
    edge.trends = trends
    edge.away_edge_score = away_edge
    edge.home_edge_score = home_edge
    edge.edge_lean = lean
    edge.features = trend_features(away, home, trends, away_edge, home_edge)
    edge.narrative = build_narrative(edge, top_n=top_n)
    return edge


def build_slate_reports(
    repo: DataRepository,
    *,
    top_n: int = 8,
    pitchers: list[dict] | None = None,
    model_by_pk: dict | None = None,
    pkmap: dict | None = None,
) -> list[SituationalEdge]:
    """Daily batch: a report for every game on the loaded slate."""
    slate = repo.slate()
    out: list[SituationalEdge] = []
    if slate is None or slate.empty:
        return out
    slate_rows = [row.to_dict() for _, row in slate.iterrows()]
    keys = matchup_keys(slate_rows)
    for index, row in enumerate(slate_rows):
        away = str(row.get("Away") or "").strip()
        home = str(row.get("Home") or "").strip()
        if not away or not home:
            continue
        game_key = keys[index]
        try:
            edge = build_situational_report(repo, away, home, top_n=top_n)
            edge.game = game_key
            if pitchers is not None or model_by_pk is not None:
                model_rows: list[dict] = []
                if model_by_pk and pkmap:
                    for pk, mapped_key in pkmap.items():
                        if mapped_key == game_key:
                            model_rows = list(model_by_pk.get(pk) or [])
                            break
                edge = _enrich_with_prop_and_market_trends(
                    edge,
                    repo,
                    away,
                    home,
                    pitchers=pitchers,
                    model_rows=model_rows,
                    top_n=top_n,
                )
            out.append(edge)
        except Exception:
            logger.exception("situational report failed for %s", game_key)
    return out


def trend_features_for_game(repo: DataRepository, away: str, home: str) -> dict[str, float]:
    """Convenience for the main model: just the flat feature row, keyed for one game."""
    return build_situational_report(repo, away, home).features
