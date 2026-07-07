"""Shared HTML formatting helpers for report views."""

from __future__ import annotations



import html
import math
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


# League-relative metric grading (mirrors dashboard/mlbma_assets.js CONTEXT_DEFAULTS).
_CONTEXT_DEFAULTS: dict[str, dict[str, float | bool]] = {
    "default": {"mean": 50.0, "std": 12.0, "hi": True},
    "osi": {"mean": 50.0, "std": 12.0, "hi": True},
    "abq": {"mean": 50.0, "std": 12.0, "hi": True},
    "rcv": {"mean": 50.0, "std": 12.0, "hi": True},
    "obr": {"mean": 50.0, "std": 12.0, "hi": True},
    "projosi": {"mean": 50.0, "std": 12.0, "hi": True},
    "pals": {"mean": 50.0, "std": 12.0, "hi": True},
    "oor": {"mean": 50.0, "std": 12.0, "hi": True},
    "pitching": {"mean": 50.0, "std": 12.0, "hi": True},
    "rate": {"mean": 50.0, "std": 10.0, "hi": True},
    "woba": {"mean": 0.320, "std": 0.035, "hi": True},
    "ops": {"mean": 0.720, "std": 0.080, "hi": True},
    "game_total": {"mean": 8.80, "std": 1.40, "hi": True},
    "margin": {"mean": 0.0, "std": 1.50, "hi": True},
    "era": {"mean": 4.10, "std": 0.85, "hi": False},
    "fip": {"mean": 4.10, "std": 0.55, "hi": False},
    "xfip": {"mean": 4.05, "std": 0.35, "hi": False},
    "hr9": {"mean": 1.20, "std": 0.28, "hi": False},
    "kpct": {"mean": 22.5, "std": 4.5, "hi": True},
    "bbpct": {"mean": 8.0, "std": 1.8, "hi": False},
    "park": {"mean": 1.00, "std": 0.08, "hi": True},
    "clv": {"mean": 0.0, "std": 2.5, "hi": True},
    "team_runs": {"mean": 4.40, "std": 1.35, "hi": True},
    "prop_k": {"mean": 5.6, "std": 1.8, "hi": True},
    "prop_er": {"mean": 2.8, "std": 1.2, "hi": False},
    "prop_outs": {"mean": 16.5, "std": 2.5, "hi": True},
    "prop_h": {"mean": 5.4, "std": 1.6, "hi": False},
    "fantasy_dk": {"mean": 18.0, "std": 6.0, "hi": True},
    "sample_n": {"mean": 10.0, "std": 4.0, "hi": True},
}


def _context_cfg(context: str) -> dict[str, float | bool]:
    key = str(context or "default").lower()
    if key in _CONTEXT_DEFAULTS:
        return _CONTEXT_DEFAULTS[key]
    stripped = key.replace("_", "")
    for name, cfg in _CONTEXT_DEFAULTS.items():
        if name.replace("_", "") == stripped:
            return cfg
    return _CONTEXT_DEFAULTS["default"]

_SOLID_CHIP_CLASS = {
    "elite": "c-elite",
    "strong": "c-good",
    "aboveAvg": "c-good",
    "average": "c-mid",
    "belowAvg": "c-mid",
    "weak": "c-weak",
    "veryWeak": "c-poor",
}


def _resolve_invert(context: str, invert: bool | None) -> bool:
    if invert is not None:
        return invert
    cfg = _context_cfg(context)
    return not bool(cfg.get("hi", True))


def _z_score(value: float, context: str) -> float:
    cfg = _context_cfg(context)
    std = float(cfg.get("std") or 12.0)
    if std < 1e-6:
        std = 12.0
    return (float(value) - float(cfg.get("mean", 50.0))) / std


def _grade_key_from_z(z: float, invert: bool) -> str:
    if invert:
        z = -z
    if z <= -1.5:
        return "veryWeak"
    if z <= -0.85:
        return "weak"
    if z <= -0.30:
        return "belowAvg"
    if z <= 0.30:
        return "average"
    if z <= 0.85:
        return "aboveAvg"
    if z <= 1.5:
        return "strong"
    return "elite"


def metric_grade(value, context: str = "osi", *, invert: bool | None = None) -> str:
    """Map a raw metric to c-elite … c-poor (league-relative)."""
    if value is None:
        return "c-na"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "c-na"
    if not math.isfinite(number):
        return "c-na"
    key = context.lower()
    if key in {"oor"}:
        if number >= 55:
            return "c-good"
        if number <= 45:
            return "c-mid"
        return "c-mid"
    z = _z_score(number, key)
    grade = _grade_key_from_z(z, _resolve_invert(key, invert))
    return _SOLID_CHIP_CLASS.get(grade, "c-mid")


def run_impact_grade(runs: float) -> str:
    """Signed run-delta coloring — green adds runs, red/orange suppresses."""
    if not math.isfinite(runs):
        return "c-na"
    if abs(runs) < 0.05:
        return "c-mid"
    if runs > 0:
        if runs >= 1.0:
            return "c-elite"
        if runs >= 0.35:
            return "c-good"
        return "c-good"
    mag = abs(runs)
    if mag >= 1.0:
        return "c-poor"
    if mag >= 0.35:
        return "c-weak"
    return "c-weak"


def val_chip_html(
    value,
    context: str = "osi",
    *,
    invert: bool | None = None,
    digits: int = 1,
    suffix: str = "",
    display_text: str | None = None,
) -> str:
    """Solid graded chip — same contract as MLBMA valChipHtml."""
    if value is None:
        return '<span class="chip c-na">—</span>'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return '<span class="chip c-na">—</span>'
    if not math.isfinite(number):
        return '<span class="chip c-na">—</span>'
    text = display_text if display_text is not None else f"{number:.{digits}f}{suffix}"
    cls = metric_grade(number, context, invert=invert)
    return f'<span class="chip {cls}">{e(text)}</span>'


def val_grade_html(
    value,
    context: str = "osi",
    *,
    invert: bool | None = None,
    digits: int = 1,
    suffix: str = "",
    bold: bool = True,
) -> str:
    """Graded numeric text without chip wrapper (tables)."""
    if value is None:
        return '<span class="c-na">—</span>'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return '<span class="c-na">—</span>'
    if not math.isfinite(number):
        return '<span class="c-na">—</span>'
    cls = metric_grade(number, context, invert=invert)
    text = f"{number:.{digits}f}{suffix}"
    tag = "b" if bold else "span"
    return f"<{tag} class=\"{cls}\">{e(text)}</{tag}>"


def prob_chip_html(probability, *, digits: int = 0) -> str:
    """Grade a 0–1 probability on the 50=neutral scale."""
    if probability is None:
        return '<span class="chip c-na">—</span>'
    return val_chip_html(float(probability) * 100.0, "osi", digits=digits, suffix="%")


def pct_chip_html(percent_value, context: str = "osi", *, digits: int = 0) -> str:
    """Grade a 0–100 percentage display."""
    if percent_value is None:
        return '<span class="chip c-na">—</span>'
    return val_chip_html(float(percent_value), context, digits=digits, suffix="%")


def lean_dir_html(lean, *, as_pill: bool = True) -> str:
    """OVER = green ▲, UNDER = red ▼."""
    key = str(lean or "").strip().upper()
    if key == "OVER":
        cls = "lean-dir lean-dir--over"
        inner = '<span class="lean-arrow" aria-hidden="true">▲</span> OVER'
    elif key == "UNDER":
        cls = "lean-dir lean-dir--under"
        inner = '<span class="lean-arrow" aria-hidden="true">▼</span> UNDER'
    else:
        if not str(lean or "").strip():
            return '<span class="c-na">—</span>'
        if as_pill:
            return f'<span class="pill mut">{e(str(lean))}</span>'
        return e(str(lean))
    if as_pill:
        return f'<span class="pill {cls}">{inner}</span>'
    return f'<span class="{cls}">{inner}</span>'


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


