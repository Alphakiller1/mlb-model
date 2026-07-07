"""Calibration and results aggregation for model_leans."""
from __future__ import annotations

from collections import defaultdict


def calibration_buckets(rows: list[dict], *, buckets: int = 5) -> list[dict]:
    """Bucket settled leans by model_prob and compare to realized hit-rate."""
    settled = [
        r for r in rows
        if r.get("settled") and r.get("model_prob") is not None and not r.get("push")
    ]
    if not settled:
        return []
    width = 1.0 / buckets
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in settled:
        p = float(row["model_prob"])
        if p > 1:
            p /= 100.0
        idx = min(buckets - 1, int(p / width))
        groups[idx].append(row)
    out = []
    for idx in sorted(groups):
        grp = groups[idx]
        lo = idx * width
        hi = lo + width
        hits = sum(1 for r in grp if r.get("won"))
        out.append({
            "bucket": f"{lo*100:.0f}–{hi*100:.0f}%",
            "n": len(grp),
            "predicted": (lo + hi) / 2 * 100,
            "actual": hits / len(grp) * 100 if grp else 0,
            "gap": (hits / len(grp) - (lo + hi) / 2) * 100 if grp else 0,
        })
    return out


def summarize_record(rows: list[dict]) -> dict:
    settled = [r for r in rows if r.get("settled")]
    wins = sum(1 for r in settled if r.get("won"))
    losses = sum(1 for r in settled if r.get("won") is False and not r.get("push"))
    pushes = sum(1 for r in settled if r.get("push"))
    by_source: dict[str, dict] = defaultdict(lambda: {"w": 0, "l": 0, "p": 0})
    for r in settled:
        src = str(r.get("source") or "unknown")
        if r.get("push"):
            by_source[src]["p"] += 1
        elif r.get("won"):
            by_source[src]["w"] += 1
        else:
            by_source[src]["l"] += 1
    return {
        "total": len(settled),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_rate": wins / (wins + losses) * 100 if (wins + losses) else None,
        "by_source": dict(by_source),
    }
