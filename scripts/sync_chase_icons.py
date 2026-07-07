#!/usr/bin/env python3
"""Sync MLBMA icon assets from mlbma-pipeline into the model static tree."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "mlbmodel" / "report" / "static"
ICON_NAMES = (
    "neon-baseball.svg",
    "neon-bat.svg",
    "neon-diamond-field.svg",
    "neon-stadium.svg",
    "neon-trend-down.svg",
    "neon-trend-up.svg",
    "neon-vs.svg",
    "neon-weather-field.svg",
)


def _resolve_source(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    env = __import__("os").environ.get("MLBMA_PIPELINE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (REPO_ROOT.parent / "mlbma-pipeline").resolve()


def sync(source: Path, *, write: bool) -> int:
    dash = source / "dashboard"
    icons_src = dash / "assets" / "icons"
    js_src = dash / "mlbma_icons.js"
    icons_dst = STATIC / "assets" / "icons"
    js_dst = STATIC / "mlbma_icons.js"
    drift: list[str] = []

    for name in ICON_NAMES:
        src = icons_src / name
        dst = icons_dst / name
        if not src.is_file():
            raise SystemExit(f"missing icon: {src}")
        if write:
            icons_dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            continue
        if not dst.is_file() or src.read_bytes() != dst.read_bytes():
            drift.append(name)

    if not js_src.is_file():
        raise SystemExit(f"missing {js_src}")
    if write:
        STATIC.mkdir(parents=True, exist_ok=True)
        shutil.copy2(js_src, js_dst)
        print(f"synced {len(ICON_NAMES)} SVGs + mlbma_icons.js")
        return 0

    if not js_dst.is_file() or js_src.read_bytes() != js_dst.read_bytes():
        drift.append("mlbma_icons.js")

    if drift:
        print("Icon drift detected (run with --write):", file=sys.stderr)
        for line in drift:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"OK — icons match {icons_src}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    return sync(_resolve_source(args.source), write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
