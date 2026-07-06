"""Shared HTML formatting helpers for report views."""
from __future__ import annotations


def display(value, suffix="", digits=1) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def edge_grade(edge_fraction) -> str:
    """chase-style 5-tier color for a prop value edge (stored as a fraction; *100 = pts)."""
    if edge_fraction is None:
        return "c-na"
    pts = edge_fraction * 100
    if pts >= 6:
        return "c-elite"
    if pts >= 3:
        return "c-good"
    if pts >= 1:
        return "c-mid"
    if pts >= 0:
        return "c-weak"
    return "c-poor"
