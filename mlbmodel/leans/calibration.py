"""Calibration and results aggregation for model_leans."""
from __future__ import annotations

import math
from collections import defaultdict


def _prob(row: dict) -> float:
    p = float(row["model_prob"])
    return p / 100.0 if p > 1 else p


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (as fractions)."""
    if n == 0:
        return 0.0, 1.0
    phat = hits / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return max(0.0, center - margin), min(1.0, center + margin)


def _graded(rows: list[dict]) -> list[dict]:
    """Settled rows with a real W/L outcome and a model probability."""
    return [
        r for r in rows
        if r.get("settled")
        and not r.get("push")
        and not r.get("void")
        and r.get("won") is not None
        and r.get("model_prob") is not None
    ]


def brier_score(rows: list[dict]) -> float | None:
    graded = _graded(rows)
    if not graded:
        return None
    total = sum((_prob(r) - (1.0 if r.get("won") else 0.0)) ** 2 for r in graded)
    return round(total / len(graded), 4)


def calibration_buckets(rows: list[dict], *, buckets: int = 5, min_n: int = 5) -> list[dict]:
    """Bucket graded leans by model_prob and compare to the realized hit-rate.

    ``predicted`` is the mean model probability of the rows in the bucket (not
    the bucket midpoint), and ``actual`` carries a Wilson 95% interval so a
    2-sample bucket cannot masquerade as evidence of miscalibration.
    """
    graded = _graded(rows)
    if not graded:
        return []
    width = 1.0 / buckets
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in graded:
        idx = min(buckets - 1, int(_prob(row) / width))
        groups[idx].append(row)
    out = []
    for idx in sorted(groups):
        grp = groups[idx]
        lo = idx * width
        hi = lo + width
        n = len(grp)
        hits = sum(1 for r in grp if r.get("won"))
        predicted = sum(_prob(r) for r in grp) / n * 100
        actual = hits / n * 100
        ci_lo, ci_hi = wilson_interval(hits, n)
        out.append({
            "bucket": f"{lo*100:.0f}–{hi*100:.0f}%",
            "n": n,
            "predicted": predicted,
            "actual": actual,
            "actual_lo": ci_lo * 100,
            "actual_hi": ci_hi * 100,
            "gap": actual - predicted,
            # Calibrated iff the mean prediction falls inside the actual CI —
            # and only claimable at all with a minimum sample.
            "reliable": n >= min_n,
            "within_ci": ci_lo * 100 <= predicted <= ci_hi * 100,
        })
    return out


def summarize_record(rows: list[dict]) -> dict:
    scored = [
        r for r in rows
        if r.get("settled") and not r.get("void")
        and str(r.get("source") or "") != "projection"
    ]
    wins = sum(1 for r in scored if r.get("won"))
    losses = sum(1 for r in scored if r.get("won") is False and not r.get("push"))
    pushes = sum(1 for r in scored if r.get("push"))
    voids = sum(1 for r in rows if r.get("void"))
    by_source: dict[str, dict] = defaultdict(lambda: {"w": 0, "l": 0, "p": 0})
    for r in scored:
        src = str(r.get("source") or "unknown")
        if r.get("push"):
            by_source[src]["p"] += 1
        elif r.get("won"):
            by_source[src]["w"] += 1
        elif r.get("won") is False:
            by_source[src]["l"] += 1
    return {
        "total": len(scored),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "voids": voids,
        "hit_rate": wins / (wins + losses) * 100 if (wins + losses) else None,
        "brier": brier_score(rows),
        "by_source": dict(by_source),
    }


def clv_summary_from_leans(rows: list[dict]) -> dict | None:
    """Mean closing-line value (pts) across leans carrying entry + clv data."""
    vals = [float(r["clv_pts"]) for r in rows if r.get("clv_pts") is not None]
    if not vals:
        return None
    by_source: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("clv_pts") is not None:
            by_source[str(r.get("source") or "unknown")].append(float(r["clv_pts"]))
    return {
        "n": len(vals),
        "clv_pts": round(sum(vals) / len(vals), 2),
        "beat_close_rate": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        "by_source": {
            src: {"n": len(v), "clv_pts": round(sum(v) / len(v), 2)}
            for src, v in sorted(by_source.items())
        },
    }


def projection_error_summary(rows: list[dict]) -> list[dict]:
    """Per-market error distribution of settled projection leans."""
    by_market: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        if (
            str(r.get("source") or "") == "projection"
            and r.get("settled")
            and not r.get("void")
            and r.get("model_value") is not None
            and r.get("realized_value") is not None
        ):
            by_market[str(r.get("market") or "?")].append(
                (float(r["model_value"]), float(r["realized_value"]))
            )
    out = []
    for market, pairs in sorted(by_market.items()):
        errors = [proj - actual for proj, actual in pairs]
        n = len(errors)
        mean_err = sum(errors) / n
        mae = sum(abs(e) for e in errors) / n
        var = sum((e - mean_err) ** 2 for e in errors) / (n - 1) if n > 1 else 0.0
        out.append({
            "market": market,
            "n": n,
            "mean_error": round(mean_err, 2),
            "mae": round(mae, 2),
            "std": round(math.sqrt(var), 2),
        })
    return out


def ungraded_reason_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        reason = r.get("ungraded_reason")
        if reason:
            counts[str(reason)] += 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
