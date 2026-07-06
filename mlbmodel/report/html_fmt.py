"""Shared HTML formatting helpers for report views."""
from __future__ import annotations

import html

e = html.escape

_SECTION_SVGS = {
    "markets": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-6"/></svg>'
    ),
    "slate": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>'
    ),
    "results": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
        '<path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
    ),
    "trends": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>'
        '<polyline points="16 7 22 7 22 13"/></svg>'
    ),
}


def section_head(title: str, *, icon: str | None = None, purpose: str = "") -> str:
    """MLBMA-style section header with optional inline icon badge."""
    icon_html = ""
    if icon and icon in _SECTION_SVGS:
        icon_html = f'<span class="ca-icon">{_SECTION_SVGS[icon]}</span>'
    purpose_html = f'<div class="purpose">{e(purpose)}</div>' if purpose else ""
    return (
        f'<div class="ca-section-head">{icon_html}'
        f'<div class="ca-section-head__body">'
        f'<div class="title">{e(title)}</div>{purpose_html}'
        f"</div></div>"
    )


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
