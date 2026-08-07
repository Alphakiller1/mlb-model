"""Exit 0 when a pick'em line cache actually holds lines, else 1.

The deploy workflow uses this to decide whether a live fetch returned real data
before it overwrites the committed snapshot. It must understand the wrapped
cache format written by ``lines_cache.write_lines_cache``:

    {"snapshot_at": "<UTC ISO>", "lines": [...]}

A bare ``len(json.load(fh))`` on that payload counts the WRAPPER'S KEYS (2), so
it is truthy even when ``lines`` is empty. That made every blocked fetch look
successful and clobber a good committed snapshot with zero lines — the failure
mode that emptied the PrizePicks board while the build logged "live fetch OK".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def line_count(path: str | Path) -> int:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if isinstance(data, list):  # legacy bare-list snapshot
        return len(data)
    if isinstance(data, dict):
        lines = data.get("lines")
        return len(lines) if isinstance(lines, list) else 0
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: lines_nonempty.py <cache.json>", file=sys.stderr)
        return 2
    count = line_count(sys.argv[1])
    print(f"lines={count}")
    return 0 if count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
