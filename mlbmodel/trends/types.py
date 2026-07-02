"""Shared types for the situational-trends module.

A ``Trend`` is one detected, situation-conditioned pattern relevant to an upcoming game.
Every field is populated from real loaded data (or explicitly marked ``data_backed=False``
when a dimension is a structural/derived signal rather than a matched historical record),
so a consumer can always tell signal from fabrication.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# Direction of the run-environment effect a trend implies.
RUN_SUPPRESSION = "run_suppression"   # team is likely to score fewer / be held down
RUN_BOOST = "run_boost"               # team is likely to score more / opponent leaks runs
NEUTRAL = "neutral"


@dataclass
class Trend:
    """One situational trend, structured for both model ingestion and narration."""

    trend_id: str
    team: str
    side: str                      # "away" | "home"
    category: str                  # bullpen_fatigue | form_vs_hand | starter_quality | park ...
    trend_description: str
    situation_key: str             # stable key for caching / dynamic weighting / joins
    direction: str                 # RUN_SUPPRESSION | RUN_BOOST | NEUTRAL

    sample_size: int
    effect_size: float             # standardized magnitude (z-like), signed toward `direction`
    z_score: float                 # raw deviation from baseline in SDs
    significance: str              # strong | moderate | weak | small-sample
    confidence: str                # high | medium | low

    historical_record: str | None = None     # "W-L" in matching games, or None
    avg_runs_scored: float | None = None
    avg_runs_allowed: float | None = None
    key_rate_diffs: dict[str, float] = field(default_factory=dict)   # {"K%": +6.9, ...}

    mechanistic_explanation: str = ""
    betting_implications: list[str] = field(default_factory=list)
    suggested_model_feature: dict[str, float] = field(default_factory=dict)

    data_backed: bool = True       # False => structural/derived signal, no matched game set
    relevance: float = 0.0         # 0..1, how tightly the trend fits today's context
    trend_score: float = 0.0       # 0..1, final rank score (set by the scorer)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SituationalEdge:
    """Per-game roll-up: ranked trends, per-team edge scores, and a flat feature row."""

    game: str
    slate_date: str
    away: str
    home: str
    away_edge_score: float          # 0..100
    home_edge_score: float          # 0..100
    edge_lean: str                  # team abbr the situational picture favors, or "even"
    trends: list[Trend] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)
    narrative: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trends"] = [t.to_dict() if isinstance(t, Trend) else t for t in self.trends]
        return d
