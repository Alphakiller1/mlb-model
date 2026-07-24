"""Evolved logic matrix — MLBMA pipeline metrics → model run factors.

This module does **not** redefine ABQ/RCV/OBR/OSI/Pitching Score. Those formulas live in
``mlbma-pipeline/core/config.py`` and ``core/compute.py``. Genesis mirrors their validated
weights and derives the betting-model conversion layer (sensitivities, blends, signal gates).

Betting Brain rules that are not in the Obsidian vault remain encoded only where the unified
model already implements them (expected-runs engine, signal edge, confidence tiers). Convergence
scoring is consumed directly from the pipeline's ``Signals_Convergence`` tab.
"""
from __future__ import annotations

# Keep in sync with mlbma-pipeline/core/config.py (2026-06 rebalanced sweep).
LINEAGE_VERSION = "2026.07"
PIPELINE_CONFIG_REF = "mlbma-pipeline/core/config.py"

OSI_WEIGHTS = {
    "rcv": 0.35,
    "abq": 0.25,
    "obr": 0.40,
}

PITCHING_WEIGHTS = {
    "k_pct": 0.30,
    "inv_bb_pct": 0.20,
    "inv_hr9": 0.20,
    "inv_whip": 0.30,
}

OOR_WEIGHTS = {
    "hvr": 0.55,
    "hvl": 0.45,
}

COMBINED_PITCHING_WEIGHTS = {
    "sp": 0.70,
    "bullpen": 0.30,
}

# Pitcher allowed tiers — OSI lineage with composite allowed index retained.
ALLOWED_METRIC_WEIGHTS = {
    "OSI_allowed": 0.35,
    "ABQ_allowed": OSI_WEIGHTS["abq"],
    "RCV_allowed": 0.25,
    "OBR_allowed": 0.15,
}

# Pipeline signal engine (core/compute_signals.py).
CONVERGENCE_THRESHOLD = 4
CONVERGENCE_PP_GAP_WEIGHT = 2
CONVERGENCE_DEFAULT_WEIGHT = 1

# Depth layer: season OSI anchor + fractional OSI components (not a second OSI formula).
COMPOSITE_BASE_WEIGHT = 0.55
COMPOSITE_METRIC_BLEND = 0.45

# Evolved model sensitivities — tuned from pipeline calibration notes, regressed in-model.
MODEL_SENSITIVITIES = {
    # Primary OSI step (~0.9 validated in osi_reweight_sweep / decision calibration).
    "osi_run": 0.90,
    "regression_to_mean": 0.25,
    # Incremental depth layer beyond slate OSI.
    "metric_run": 0.004,
    "pals_blend": 0.08,
    "proj_osi_blend": 0.12,
    "oor_blend": 0.06,
    "off_depth_clip": (0.97, 1.03),
    # Pitching staff — mirror COMBINED_PITCHING_WEIGHTS starter share anchor.
    "sp_fip_weight": COMBINED_PITCHING_WEIGHTS["sp"],
    "pitching_score_run": 0.002,
    "allowed_metric": 0.0018,
    # Platoon / recent form — OBR-heavy offense gets slightly stronger split read.
    "platoon_metric": 0.0025,
    "platoon_delta": 0.003,
    "recent_osi": 0.12,
    "recent_abq": 0.06,
    "recent_rcv": 0.06,
    # Situational trend features (pipeline trend report).
    "trend_run": 0.008,
    "trend_pen": 0.006,
    "trend_interaction": 0.004,
    "trend_park": 0.003,
    "trend_clip": (0.97, 1.03),
    # Defense / bullpen IR.
    "defense": 0.003,
    "bullpen_ir": 0.004,
    # Signal + convergence gates (pipeline Signals_Today / Signals_Convergence).
    "signal_edge_scale": 0.0015,
    "signal_edge_cap": 0.025,
    "convergence_edge_scale": 0.003,
    "convergence_edge_cap": 0.012,
}


def composite_metric_weight(metric: str) -> float:
    """Weight for ABQ/RCV/OBR in the offense depth composite."""
    return OSI_WEIGHTS[metric] * COMPOSITE_METRIC_BLEND


def convergence_for_game(
    rows: list[dict],
    away: str,
    home: str,
) -> list[dict]:
    away_key = away.strip().upper()
    home_key = home.strip().upper()
    return [
        row
        for row in rows
        if str(row.get("away") or "").upper() == away_key
        and str(row.get("home") or "").upper() == home_key
    ]


def convergence_side_row(
    rows: list[dict],
    *,
    away: str,
    home: str,
    side: str,
) -> dict | None:
    side_key = side.strip().lower()
    for row in convergence_for_game(rows, away, home):
        if str(row.get("side") or "").lower() == side_key:
            return row
    return None

