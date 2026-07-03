"""Chase Analytics shared visual layer — vendored tokens/components/logo, self-contained output.

Extracted from mlbma-pipeline's design system (dashboard/mlbma_design_system.css,
dashboard/chase_nav.css, dashboard/assets/) rather than invented. See
mlbmodel/report/static/chase_tokens.css and chase_components.css for the canonical values;
resync those by hand if the MLBMA source changes. This module has no runtime dependency on
the mlbma-pipeline repo -- the CSS and logo asset are vendored copies so this product stays
independently deployable and every generated HTML page stays self-contained.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"


@lru_cache(maxsize=1)
def theme_css() -> str:
    tokens = (_STATIC / "chase_tokens.css").read_text(encoding="utf-8")
    components = (_STATIC / "chase_components.css").read_text(encoding="utf-8")
    return tokens + "\n" + components


@lru_cache(maxsize=1)
def _icon_data_uri() -> str:
    data = (_STATIC / "assets" / "chase-icon-filled.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def nav_html(nav_items: list[tuple[str, str, str]], active: str, product_tag: str) -> str:
    """Build the shared Chase header/nav bar.

    ``nav_items`` is a list of (key, label, onclick-js) tuples; ``active`` is the key of the
    current view. ``product_tag`` names the product (e.g. "MLB Model") next to the wordmark,
    matching the shared header construction without claiming to be a different repo's page.
    """
    links = "".join(
        f'<button type="button" class="chase-nav-link{" active" if key == active else ""}" '
        f'onclick="{onclick}">{label}</button>'
        for key, label, onclick in nav_items
    )
    icon = _icon_data_uri()
    return f"""<header class="chase-header">
  <nav class="chase-nav">
    <a href="https://chase-analytics.com" class="chase-logo" title="Chase Analytics">
      <img class="chase-nav-logo--icon" src="{icon}" alt="" width="36" height="36">
      <span class="chase-wordmark"><span>Chase</span><span class="chase-wordmark__accent">Analytics</span></span>
    </a>
    <div class="chase-nav-links">{links}</div>
    <span class="chase-product-tag">{product_tag}</span>
  </nav>
</header>"""
