"""Copy vendored static assets alongside generated HTML output."""
from __future__ import annotations

import shutil
from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"


def publish_assets(site_dir: Path) -> int:
    """Mirror ``static/assets/icons`` into ``site_dir/assets/icons``. Returns file count."""
    icons_src = _STATIC / "assets" / "icons"
    if not icons_src.is_dir():
        return 0
    icons_dst = site_dir / "assets" / "icons"
    icons_dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for svg in icons_src.glob("*.svg"):
        shutil.copy2(svg, icons_dst / svg.name)
        count += 1
    return count
