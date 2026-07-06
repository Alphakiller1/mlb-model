"""Shared HTML formatting helpers for report views."""
from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

e = html.escape

_STATIC = Path(__file__).resolve().parent / "static"
_ICON_DIR = _STATIC / "assets" / "icons"

_ICON_FILES = {
    "markets": "neon-trend-up.svg",
    "slate": "neon-diamond-field.svg",
    "results": "neon-stadium.svg",
    "trends": "neon-trend-up.svg",
    "research": "neon-stadium.svg",
    "portfolio": "neon-baseball.svg",
    "props": "neon-bat.svg",
    "matchups": "neon-vs.svg",
}

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
}


@lru_cache(maxsize=16)
def _unique_svg(file_name: str) -> str:
    path = _ICON_DIR / file_name
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    uid = re.sub(r"[^a-z0-9]+", "-", file_name.lower()).strip("-")
    for token in ("neon", "glow"):
        text = text.replace(f'id="{token}"', f'id="{token}-{uid}"')
        text = text.replace(f"url(#{token})", f"url(#{token}-{uid})")
    return text


def section_icon_html(key: str, *, small: bool = True) -> str:
    """MLBMA neon icon badge — inlined SVG when vendored, thin fallback otherwise."""
    file_name = _ICON_FILES.get(key)
    if file_name:
        svg = _unique_svg(file_name)
        if svg:
            cls = "ca-neon-icon ca-neon-icon--sm" if small else "ca-neon-icon"
            return f'<span class="{cls}" aria-hidden="true">{svg}</span>'
    fallback = _SECTION_SVGS.get(key)
    if fallback:
        return f'<span class="ca-icon" aria-hidden="true">{fallback}</span>'
    return ""


def section_head(title: str, *, icon: str | None = None, purpose: str = "") -> str:
    """MLBMA-style section header with optional neon icon badge."""
    icon_html = section_icon_html(icon) if icon else ""
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
