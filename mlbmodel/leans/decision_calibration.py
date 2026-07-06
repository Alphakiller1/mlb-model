"""Calibrate Markets decision thresholds from settled sharp leans."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionThresholds:
    strong_edge: float = 2.0
    strong_div: float = 1.5
    bet_edge: float = 0.01
    sample_n: int = 0
    calibrated: bool = False

    def summary(self) -> str:
        if not self.calibrated:
            return f"default thresholds (n={self.sample_n} settled sharp leans)"
        return (
            f"calibrated from {self.sample_n} sharp leans — "
            f"STRONG ≥{self.strong_edge:.1f}pt edge / ≥{self.strong_div:.1f}pt div, "
            f"BET ≥{self.bet_edge:.1f}pt edge"
        )


DEFAULT_THRESHOLDS = DecisionThresholds()


def _edge_pts(row: dict) -> float | None:
    raw = row.get("edge")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if abs(value) > 1 else value * 100


def thresholds_from_leans(rows: list[dict], *, min_sample: int = 25) -> DecisionThresholds:
    """Derive STRONG/BET edge floors from settled sharp-market leans."""
    settled = [
        row for row in rows
        if row.get("settled")
        and not row.get("push")
        and str(row.get("source") or "").lower() == "sharp"
        and _edge_pts(row) is not None
    ]
    n = len(settled)
    if n < min_sample:
        return DecisionThresholds(sample_n=n, calibrated=False)

    winners = [row for row in settled if row.get("won")]
    if len(winners) < 10:
        return DecisionThresholds(sample_n=n, calibrated=False)

    win_edges = sorted(_edge_pts(row) for row in winners if _edge_pts(row) is not None)
    if not win_edges:
        return DecisionThresholds(sample_n=n, calibrated=False)

    # STRONG: conservative floor — 25th percentile of edges on winning sharp leans.
    p25_idx = max(0, len(win_edges) // 4 - 1)
    strong_edge = max(1.0, min(3.5, win_edges[p25_idx]))

    # BET: lowest 0.5pt edge bucket with hit rate ≥ 52% (min 8 samples).
    bet_edge = 0.5
    for floor in [x * 0.5 for x in range(0, 13)]:
        bucket = [row for row in settled if (_edge_pts(row) or 0) >= floor]
        if len(bucket) < 8:
            continue
        hits = sum(1 for row in bucket if row.get("won"))
        if hits / len(bucket) >= 0.52:
            bet_edge = floor if floor > 0 else 0.01
            break

    return DecisionThresholds(
        strong_edge=round(strong_edge, 2),
        strong_div=1.5,
        bet_edge=round(bet_edge, 2),
        sample_n=n,
        calibrated=True,
    )
