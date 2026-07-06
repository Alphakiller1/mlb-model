#!/usr/bin/env python3
"""Copy mlbma_icons.js from mlbma-pipeline (optional; PNG assets not vendored)."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "mlbmodel" / "report" / "static"


def sync(source: Path, *, write: bool) -> int:
    src = source / "dashboard" / "mlbma_icons.js"
    dst = STATIC / "mlbma_icons.js"
    if not src.is_file():
        raise SystemExit(f"missing {src}")
    if write:
        STATIC.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied {dst.relative_to(REPO_ROOT)}")
        return 0
    if not dst.is_file() or src.read_bytes() != dst.read_bytes():
        print("mlbma_icons.js drift detected (run with --write)", file=sys.stderr)
        return 1
    print("OK — mlbma_icons.js matches pipeline")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(args.source).resolve() if args.source else (REPO_ROOT.parent / "mlbma-pipeline").resolve()
    return sync(root, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
