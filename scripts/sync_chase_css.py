#!/usr/bin/env python3
"""Sync vendored Chase Analytics CSS from mlbma-pipeline into MLB Model static assets.

Copies dashboard/*.css that chase_theme.theme_css() loads from the pipeline repo.
``mlbma_backgrounds.css`` is intentionally excluded — MLB Model uses a gradient-only fork.

Usage:
    python scripts/sync_chase_css.py --source ../mlbma-pipeline --write
    python scripts/sync_chase_css.py --source ../mlbma-pipeline --check

Environment:
    MLBMA_PIPELINE_ROOT — default for --source when omitted
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "mlbmodel" / "report" / "static"

# dashboard filename → static filename (1:1 for synced files)
SYNC_FILES = (
    "mlbma_design_system.css",
    "theme.css",
    "chase_nav.css",
)

# Never overwrite — documented fork in chase_theme.py
EXCLUDE = frozenset({"mlbma_backgrounds.css"})


def _resolve_source(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    env = __import__("os").environ.get("MLBMA_PIPELINE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (REPO_ROOT.parent / "mlbma-pipeline").resolve()


def _dashboard_dir(source: Path) -> Path:
    dash = source / "dashboard"
    if not dash.is_dir():
        raise SystemExit(f"dashboard/ not found under {source}")
    return dash


def sync(source: Path, *, write: bool) -> int:
    dashboard = _dashboard_dir(source)
    drift: list[str] = []

    for name in SYNC_FILES:
        if name in EXCLUDE:
            continue
        src = dashboard / name
        dst = STATIC / name
        if not src.is_file():
            raise SystemExit(f"missing source file: {src}")
        if write:
            STATIC.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"copied {src.name}")
            continue
        if not dst.is_file():
            drift.append(f"missing vendored copy: {dst.relative_to(REPO_ROOT)}")
            continue
        if src.read_bytes() != dst.read_bytes():
            drift.append(f"drift: {name}")

    if write:
        print(f"synced {len(SYNC_FILES)} files → {STATIC.relative_to(REPO_ROOT)}")
        return 0

    if drift:
        print("Chase CSS drift detected (run with --write after review):", file=sys.stderr)
        for line in drift:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"OK — {len(SYNC_FILES)} vendored CSS files match {dashboard}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        help="Path to mlbma-pipeline repo (default: MLBMA_PIPELINE_ROOT or ../mlbma-pipeline)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Exit 1 if vendored CSS differs")
    mode.add_argument("--write", action="store_true", help="Copy dashboard CSS into static/")
    args = parser.parse_args(argv)
    return sync(_resolve_source(args.source), write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
