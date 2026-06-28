"""Daily batch CLI for the situational-trends module.

    python -m mlbmodel.trends.cli --data-dir DATA [--game NYY@BOS] [--out trends.json] [--narrative]

Writes the structured JSON (model-consumable) and optionally prints the human-readable
narrative for each game. Designed to run once per slate after the MLBMA sync.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from mlbmodel.baseball.repository import DataRepository
from mlbmodel.trends.report import build_situational_report, build_slate_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dominant Situational Trends report")
    parser.add_argument("--data-dir", default=None, help="MLBMA data dir (default: settings.DATA_DIR)")
    parser.add_argument("--game", default=None, help="single game AWAY@HOME (default: full slate)")
    parser.add_argument("--out", default=None, help="write structured JSON here")
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--narrative", action="store_true", help="print human-readable bullets")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    repo = DataRepository(args.data_dir)

    if args.game:
        away, home = args.game.replace(" ", "").split("@")
        reports = [build_situational_report(repo, away, home, top_n=args.top_n)]
    else:
        reports = build_slate_reports(repo, top_n=args.top_n)

    payload = {"games": [r.to_dict() for r in reports]}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"wrote {args.out} ({len(reports)} games)")
    else:
        print(json.dumps(payload, indent=2))

    if args.narrative:
        for r in reports:
            print(f"\n=== {r.game}  ({r.slate_date}) ===")
            for line in r.narrative:
                print(f"  • {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
