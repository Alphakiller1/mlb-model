"""Chase Analytics shared visual layer — vendored design system, self-contained output.

Copies production Chase Analytics dashboard styles from mlbma-pipeline/dashboard/
(mlbma_design_system.css, theme.css, chase_nav.css, chase_tokens, chase_components).
The model report uses the same header, wordmark, tokens, and typography as chase-analytics.com.

**Backgrounds:** ``mlbma_backgrounds.css`` in this tree is an MLB-Model-only fork — gradient
broadcast scrim only, no stadium photo layers (smaller self-contained HTML). Do **not** overwrite
it from mlbma-pipeline/dashboard/; chase-analytics.com keeps the full stadium photo treatment.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"

# The production font import, extended with Oswald (the italic wordmark face used by
# .chase-wordmark in chase_nav.css) which the dashboard loads globally elsewhere.
_SRC_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=DM+Sans:wght@400;500;600;700;800&"
    "family=Roboto+Condensed:wght@400;500;600;700&display=swap');"
)
_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=DM+Sans:wght@400;500;600;700;800&"
    "family=Oswald:ital,wght@0,600;0,700;0,900;1,600;1,700;1,900&"
    "family=Roboto+Condensed:wght@400;500;600;700&display=swap');"
)


@lru_cache(maxsize=1)
def theme_css() -> str:
    """The full production Chase Analytics stylesheet, inlined and self-contained.

    Load order mirrors the site: design-system tokens/components → theme extensions →
    header/nav → broadcast gradient backgrounds (MLB Model fork; no stadium photos).
    """
    design = (_STATIC / "mlbma_design_system.css").read_text(encoding="utf-8")
    # The vendored copy is standalone: drop the responsive.css @import (not vendored) and add
    # Oswald to the font import so the wordmark renders in its real face.
    design = design.replace("@import url('responsive.css?v=20260630a');", "")
    design = design.replace(_SRC_FONT_IMPORT, _FONT_IMPORT)

    theme = (_STATIC / "theme.css").read_text(encoding="utf-8")
    nav = (_STATIC / "chase_nav.css").read_text(encoding="utf-8")

    backgrounds = (_STATIC / "mlbma_backgrounds.css").read_text(encoding="utf-8")

    tokens = (_STATIC / "chase_tokens.css").read_text(encoding="utf-8")
    components = (_STATIC / "chase_components.css").read_text(encoding="utf-8")

    return "\n".join([design, theme, nav, backgrounds, tokens, components])


@lru_cache(maxsize=1)
def _icon_data_uri() -> str:
    import base64

    data = (_STATIC / "assets" / "chase-icon-filled.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def nav_html(
    nav_items: list[tuple[str, str, str]],
    active: str,
    product_tag: str,
    status: str = "Live",
) -> str:
    """Build the real Chase Analytics header/nav bar (matches dashboard/chase_nav.html).

    ``nav_items`` is a list of (key, label, onclick-js) tuples rendered as in-page view
    switches; ``active`` is the current view key. ``product_tag`` labels the product next to the
    wordmark; ``status`` is the pipeline/freshness text shown at right.
    """
    links = "".join(
        f'<button type="button" class="chase-nav-link{" active" if key == active else ""}" '
        f'data-v="{key}" onclick="{onclick}">{label}</button>'
        for key, label, onclick in nav_items
    )
    icon = _icon_data_uri()
    return f"""<header class="chase-header" id="chaseHeader">
  <nav class="chase-nav">
    <a href="https://chase-analytics.com" class="chase-logo" title="Chase Analytics">
      <img class="chase-nav-logo--icon" src="{icon}" alt="" width="36" height="36">
      <span class="chase-wordmark"><span>Chase</span><span class="chase-wordmark__accent">Analytics</span></span>
    </a>
    <div class="chase-nav-links">{links}</div>
    <div class="chase-status">
      <span class="chase-product-tag">{product_tag}</span>
      <div class="chase-timestamp">
        <span class="chase-pipeline-dot" title="Pipeline: Fresh"></span>
        <span>{status}</span>
      </div>
    </div>
  </nav>
</header>"""
