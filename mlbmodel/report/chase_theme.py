"""Chase Analytics shared visual layer — the REAL vendored design system, self-contained output.

These are byte-for-byte copies of the production Chase Analytics dashboard styles from
mlbma-pipeline/dashboard/ (mlbma_design_system.css, theme.css, chase_nav.css,
mlbma_backgrounds.css + the stadium-outfield background photo and brand icon). The model report
renders with the *same* header, wordmark, tokens, typography, and stadium background as
chase-analytics.com — not an approximation. Everything is inlined so each generated HTML page
stays fully self-contained (no external CSS/asset fetches), while remaining a faithful port of
the source. Resync by re-copying the four CSS files + the background asset if the source changes.
"""
from __future__ import annotations

import base64
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
def _bg_photo_data_uri() -> str:
    data = (_STATIC / "assets" / "backgrounds" / "stadium-outfield-night.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


@lru_cache(maxsize=1)
def theme_css() -> str:
    """The full production Chase Analytics stylesheet, inlined and self-contained.

    Load order mirrors the site: design-system tokens/components → theme extensions →
    header/nav → stadium backgrounds. The model's small vendored token/grade-chip files are
    appended last so shell-specific tokens (glass panels, grade chips) resolve; duplicates share
    the source values so the cascade is unchanged.
    """
    design = (_STATIC / "mlbma_design_system.css").read_text(encoding="utf-8")
    # The vendored copy is standalone: drop the responsive.css @import (not vendored) and add
    # Oswald to the font import so the wordmark renders in its real face.
    design = design.replace("@import url('responsive.css?v=20260630a');", "")
    design = design.replace(_SRC_FONT_IMPORT, _FONT_IMPORT)

    theme = (_STATIC / "theme.css").read_text(encoding="utf-8")
    nav = (_STATIC / "chase_nav.css").read_text(encoding="utf-8")

    backgrounds = (_STATIC / "mlbma_backgrounds.css").read_text(encoding="utf-8")
    # Inline the stadium photo so the page needs no external asset fetch on GitHub Pages.
    backgrounds = backgrounds.replace(
        "url('assets/backgrounds/stadium-outfield-night.png')",
        f"url('{_bg_photo_data_uri()}')",
    )

    tokens = (_STATIC / "chase_tokens.css").read_text(encoding="utf-8")
    components = (_STATIC / "chase_components.css").read_text(encoding="utf-8")

    return "\n".join([design, theme, nav, backgrounds, tokens, components])


@lru_cache(maxsize=1)
def _icon_data_uri() -> str:
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
