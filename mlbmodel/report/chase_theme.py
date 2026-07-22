"""Chase Analytics shared visual layer — vendored design system, self-contained output.

Copies production Chase Analytics dashboard styles from mlbma-pipeline/dashboard/
(mlbma_design_system.css, theme.css, chase_nav.css, chase_tokens, chase_components).
The model report uses the same header, wordmark, tokens, and typography as chase-analytics.com.

**Backgrounds:** ``mlbma_backgrounds.css`` in this tree is an MLB-Model-only fork — gradient
broadcast scrim only, no stadium photo layers (smaller self-contained HTML). Do **not** overwrite
it from mlbma-pipeline/dashboard/; chase-analytics.com keeps the full stadium photo treatment.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"

# Single font load for the whole bundle — Oswald is wordmark-only; DM Sans = UI/body;
# Roboto Condensed = display headings and graded stat chips.
_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;0,9..40,800&"
    "family=Oswald:ital,wght@0,600;0,700;0,900;1,600;1,700;1,900&"
    "family=Roboto+Condensed:wght@400;500;600;700;800&display=swap');"
)
_FONT_IMPORT_RE = re.compile(
    r"@import\s+url\([^)]*fonts\.googleapis\.com[^)]*\)\s*;",
    re.IGNORECASE,
)


def _strip_font_imports(css: str) -> str:
  """Remove duplicate Google Font @imports from vendored sheets."""
  return _FONT_IMPORT_RE.sub("", css)


@lru_cache(maxsize=1)
def theme_css() -> str:
    """The full production Chase Analytics stylesheet, inlined and self-contained.

    Load order: design-system → theme → backgrounds → tokens → components (nav included).
    Fonts are imported once at the top; vendored @imports are stripped to avoid double-loads.
    """
    design = _strip_font_imports(
        (_STATIC / "mlbma_design_system.css")
        .read_text(encoding="utf-8")
        .replace("@import url('responsive.css?v=20260630a');", "")
    )

    theme = _strip_font_imports((_STATIC / "theme.css").read_text(encoding="utf-8"))
    backgrounds = (_STATIC / "mlbma_backgrounds.css").read_text(encoding="utf-8")
    tokens = _strip_font_imports((_STATIC / "chase_tokens.css").read_text(encoding="utf-8"))
    components = _strip_font_imports(
        (_STATIC / "chase_components.css").read_text(encoding="utf-8")
    )

    return "\n".join([_FONT_IMPORT, design, theme, backgrounds, tokens, components])


@lru_cache(maxsize=1)
def _icon_data_uri() -> str:
    import base64

    data = (_STATIC / "assets" / "chase-icon-filled.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


@lru_cache(maxsize=1)
def _wordmark_data_uri() -> str:
    import base64

    data = (_STATIC / "assets" / "chase-wordmark.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def nav_html(
    nav_items: list[tuple[str, str, str]],
    active: str,
    product_tag: str,
    status: str = "Live",
) -> str:
    """Build the Chase Analytics research-terminal rail.

    ``nav_items`` is a list of (key, label, onclick-js) tuples rendered as in-page view
    switches; ``active`` is the current view key. ``product_tag`` labels the product next to the
    wordmark; ``status`` is the pipeline/freshness text shown at right.
    """
    icons = {
        "today": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 9h18M8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01"/></svg>',
        "matchups": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2v20M2 12h20"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/></svg>',
        "trends": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3v18h18M7 16l4-5 4 3 5-7"/></svg>',
        "markets": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/></svg>',
        "props": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8"/></svg>',
        "results": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
        "research": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4M11 8v6M8 11h6"/></svg>',
    }
    links = "".join(
        f'<button type="button" class="chase-nav-link{" active" if key == active else ""}" '
        f'data-v="{key}" onclick="{onclick}">{icons.get(key, "")}<span>{label}</span></button>'
        for key, label, onclick in nav_items
    )
    icon = _icon_data_uri()
    wordmark = _wordmark_data_uri()
    return f"""<aside class="chase-header chase-rail" id="chaseHeader">
  <a href="https://chase-analytics.com" class="chase-logo chase-rail__brand" title="Chase Analytics">
    <img class="chase-nav-logo--icon" src="{icon}" alt="" width="30" height="30">
    <span class="chase-wordmark"><span>Chase</span><span class="chase-wordmark__accent">Analytics</span></span>
    <img class="chase-wordmark-image" src="{wordmark}" alt="Chase Analytics" width="94" height="16">
  </a>
  <div class="chase-rail__product">
    <span>{product_tag}</span>
    <i><span class="chase-pipeline-dot" title="Pipeline: Fresh"></span>{status}</i>
  </div>
  <nav class="chase-nav" aria-label="MLB model navigation">
    <div class="chase-nav-links">{links}</div>
  </nav>
  <button type="button" class="chase-rail__settings" title="Settings">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.6v-.09A1.7 1.7 0 0 0 8.5 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3V9.6h.09A1.7 1.7 0 0 0 4.6 8.5a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.5 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.18.36.49.7.9.92.35.2.73.31 1.11.32H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z"/></svg>
    <span>Settings</span>
  </button>
</aside>"""
