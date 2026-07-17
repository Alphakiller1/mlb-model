"""Post a run report to the Chase Analytics Discord via webhook.

Usage: python scripts/notify_discord.py --title "settle run" --status success --body "..."
No-op (exit 0) when DISCORD_WEBHOOK_URL is not configured, so workflows can call
it unconditionally.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def post(webhook: str, title: str, status: str, body: str) -> None:
    color = {"success": 0x4CC38A, "failure": 0xE5645F}.get(status.lower(), 0xE8B45A)
    payload = {
        "embeds": [
            {
                "title": f"mlb-model · {title}",
                "description": body[:3900] or "(no details)",
                "color": color,
            }
        ]
    }
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "mlb-model-notify/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--status", default="info", choices=["success", "failure", "info"])
    parser.add_argument("--body", default="")
    parser.add_argument("--body-stdin", action="store_true", help="Read body from stdin.")
    args = parser.parse_args()

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        print("notify: DISCORD_WEBHOOK_URL not set; skipping")
        return 0
    body = sys.stdin.read() if args.body_stdin else args.body
    try:
        post(webhook, args.title, args.status, body)
        print("notify: posted to Discord")
    except Exception as exc:  # Never fail the pipeline because a notification failed.
        print(f"notify: failed ({exc}); continuing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
