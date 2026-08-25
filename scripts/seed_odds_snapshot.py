"""Promote the freshest valid committed odds snapshots into a deploy data directory."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _snapshot_time(path: Path) -> datetime | None:
    if not path.exists() or not path.stat().st_size:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not payload.get("events"):
            return None
        raw = str(payload.get("fetched_at") or "").strip()
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def freshest_snapshot(paths: list[Path]) -> Path | None:
    valid = [(timestamp, path) for path in paths if (timestamp := _snapshot_time(path))]
    return max(valid, default=(None, None), key=lambda item: item[0])[1]


def promote_snapshot(destination: Path, candidates: list[Path]) -> Path | None:
    chosen = freshest_snapshot([destination, *candidates])
    if chosen is None:
        return None
    if chosen.resolve() != destination.resolve():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chosen, destination)
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, action="append", default=[])
    parser.add_argument(
        "--snapshot",
        action="append",
        default=["odds_latest.json", "prop_odds_latest.json"],
    )
    args = parser.parse_args()

    for name in dict.fromkeys(args.snapshot):
        destination = args.deploy_dir / name
        candidates = [directory / name for directory in args.candidate_dir]
        chosen = promote_snapshot(destination, candidates)
        label = str(chosen) if chosen else "none"
        print(f"{name}: deploy seed {label}")


if __name__ == "__main__":
    main()
