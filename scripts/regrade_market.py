"""Reset settled leans for one market so the next grading pass re-settles them.

Written for the `fantasy_score` repair: those rows were graded with the DraftKings pitcher
formula while the projection engine — correctly — used PrizePicks scoring, so every
realised value sits on roughly half the right scale. Resetting them to unsettled lets the
normal grading job in mlbmodel.leans.grade recompute with the fixed formula.

Dry run by default. Nothing is written without --apply.

    python scripts/regrade_market.py --market fantasy_score
    python scripts/regrade_market.py --market fantasy_score --apply
"""
from __future__ import annotations

import argparse
import json
import statistics
import urllib.error
import urllib.request

from mlbmodel import settings


def _request(path: str, *, key: str, method: str = "GET", payload=None, extra_headers=None):
    url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{path}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read().decode()
    return json.loads(body) if body.strip() else []


def fetch_all(path: str, key: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        batch = _request(f"{path}&offset={offset}&limit=1000", key=key)
        rows += batch
        offset += len(batch)
        if len(batch) < 1000:
            break
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True, help="market to reset, e.g. fantasy_score")
    parser.add_argument("--source", default="projection", help="lean source (default: projection)")
    parser.add_argument("--apply", action="store_true", help="perform the write")
    args = parser.parse_args()

    read_key = settings.supabase_read_key()
    if not settings.SUPABASE_URL or not read_key:
        print("SUPABASE_URL / read key not configured")
        return 1

    query = (
        f"model_leans?market=eq.{args.market}&source=eq.{args.source}&settled=eq.true"
        "&select=lean_id,slate_date,pitcher_name,model_value,realized_value"
    )
    rows = fetch_all(query, read_key)
    print(f"settled {args.source}/{args.market} leans: {len(rows)}")
    if not rows:
        return 0

    paired = [
        (float(r["model_value"]), float(r["realized_value"]))
        for r in rows
        if r.get("model_value") is not None and r.get("realized_value") is not None
    ]
    if paired:
        projected = statistics.mean(v for v, _ in paired)
        realised = statistics.mean(v for _, v in paired)
        print(f"  current projected mean {projected:8.2f}")
        print(f"  current realised  mean {realised:8.2f}")
        print(f"  bias                   {projected - realised:+8.2f}  (n={len(paired)})")
    print(f"  slate dates {min(r['slate_date'] for r in rows)} .. {max(r['slate_date'] for r in rows)}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to reset these rows.")
        print("After applying, run the normal settle pass to re-grade them.")
        return 0

    write_key = settings.supabase_write_key()
    if not write_key:
        print("SUPABASE_SECRET_KEY / write key not configured; refusing to write")
        return 1

    payload = {"settled": False, "realized_value": None, "settled_at": None, "won": None}
    updated = 0
    for row in rows:
        try:
            _request(
                f"model_leans?lean_id=eq.{row['lean_id']}",
                key=write_key,
                method="PATCH",
                payload=payload,
                extra_headers={"Prefer": "return=minimal"},
            )
            updated += 1
        except urllib.error.HTTPError as exc:
            print(f"  FAILED {row['lean_id']}: HTTP {exc.code} {exc.read().decode()[:160]}")
            break
    print(f"\nreset {updated} rows to unsettled; run the settle pass to re-grade")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
