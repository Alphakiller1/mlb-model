"""Orchestration: turn one game into a full situational-trends report.

``build_situational_report`` is the single entry point used by the CLI, the model feature
pipeline, and any UI. It resolves context → runs detectors → ranks/scores → computes per-team
edge scores → engineers model features → writes the narrative, returning one
:class:`SituationalEdge`.
"""

from __future__ import annotations

import logging

from mlbmodel.baseball.repository import DataRepository
from mlbmodel.trends.context import SituationalContext
from mlbmodel.trends.detectors import run_detectors
from mlbmodel.trends.features import trend_features
from mlbmodel.trends.narrative import build_narrative
from mlbmodel.trends.scoring import rank_and_score, team_edge_scores
from mlbmodel.trends.types import SituationalEdge

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


def build_slate_reports(repo: DataRepository, *, top_n: int = 8) -> list[SituationalEdge]:
    """Daily batch: a report for every game on the loaded slate."""
    slate = repo.slate()
    out: list[SituationalEdge] = []
    if slate is None or slate.empty:
        return out
    for _, row in slate.iterrows():
        away = str(row.get("Away") or "").strip()
        home = str(row.get("Home") or "").strip()
        if not away or not home:
            continue
        try:
            out.append(build_situational_report(repo, away, home, top_n=top_n))
        except Exception:
            logger.exception("situational report failed for %s@%s", away, home)
    return out


def trend_features_for_game(repo: DataRepository, away: str, home: str) -> dict[str, float]:
    """Convenience for the main model: just the flat feature row, keyed for one game."""
    return build_situational_report(repo, away, home).features
