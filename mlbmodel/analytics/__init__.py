"""Post-model analytics: edge ranking, CLV, team accuracy."""

from mlbmodel.analytics.edge_intel import (
    clv_from_snapshots,
    collect_slate_opportunities,
    market_type_record,
    team_prediction_record,
)

__all__ = [
    "clv_from_snapshots",
    "collect_slate_opportunities",
    "market_type_record",
    "team_prediction_record",
]
