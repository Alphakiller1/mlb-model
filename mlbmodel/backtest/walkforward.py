"""
Point-in-time, out-of-sample backtest harness for market-movement strategies
(Constitution STD-10). Implements the charter's "use past betting data and movement to
inform future decisions" honestly: it splits settled Kalshi closing-line snapshots
*by time*, fits a rule on the PAST, and measures it on the strictly-later FUTURE — never
in-sample. Includes a Kalshi execution-fee model so ROI is net of execution cost, a
non-parametric bootstrap CI, and an ablation interface.

Core functions are pure (operate on row dicts) so they unit-test offline; the loader is a
thin Supabase reader. Each snapshot row needs: snapshot_time, open_prob, delta, won (bool),
implied_probability (close), volume.
"""
from __future__ import annotations

import random
from statistics import NormalDist

_N = NormalDist()


# ── execution cost ───────────────────────────────────────────────────────────
def kalshi_fee(price: float) -> float:
    """Kalshi trading fee ~ 0.07 * P * (1-P) per contract (max near 0.50, ~0 at tails)."""
    return 0.07 * price * (1.0 - price)


def net_roi(open_prob: float, won: bool, *, fee: bool = True) -> float:
    """ROI per dollar staked entering at `open_prob` (a de-vigged probability), net of the
    Kalshi fee when fee=True. Payout is 1 on win; stake is `open_prob`."""
    p = min(max(open_prob, 1e-6), 1 - 1e-6)
    f = kalshi_fee(p) if fee else 0.0
    net = (1.0 - p - f) if won else (-p - f)
    return net / p


# ── evaluation ───────────────────────────────────────────────────────────────
def evaluate(rows: list[dict], *, fee: bool = True) -> dict:
    """ROI/win/CLV for a set of already-selected bets (one row = one entered side)."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    rois = [net_roi(r["open_prob"], r["won"], fee=fee) for r in rows]
    wins = sum(1 for r in rows if r["won"])
    clv = sum((r["implied_probability"] - r["open_prob"]) for r in rows) / n
    mean = sum(rois) / n
    lb, ub = _bootstrap_ci(rois)
    return {"n": n, "win_rate": round(wins / n, 4), "roi": round(mean, 4),
            "roi_lb": round(lb, 4), "roi_ub": round(ub, 4), "clv": round(clv, 4)}


def _bootstrap_ci(xs: list[float], iters: int = 2000, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(xs)
    if n == 0:
        return (0.0, 0.0)
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[min(iters - 1, int(0.975 * iters))]


# ── strategy + point-in-time split ───────────────────────────────────────────
def steam_rule(threshold: float):
    """Bet the side the market moved TOWARD (delta >= threshold)."""
    return lambda r: (r.get("delta") or 0.0) >= threshold


def time_ordered_split(rows: list[dict], train_frac: float = 0.7,
                       time_key: str = "snapshot_time") -> tuple[list[dict], list[dict]]:
    """Sort by time; earliest `train_frac` = train, the strictly-later remainder = test.
    No shuffling — this is the point-in-time guarantee (no future leakage)."""
    ordered = sorted(rows, key=lambda r: r.get(time_key) or "")
    cut = int(len(ordered) * train_frac)
    return ordered[:cut], ordered[cut:]


def fit_best_threshold(train: list[dict], grid=(0.02, 0.03, 0.04, 0.05, 0.06),
                       min_n: int = 20) -> float | None:
    """'Fit' = choose the steam threshold with the best net ROI on TRAIN only."""
    best, best_roi = None, -1e9
    for t in grid:
        sel = [r for r in train if steam_rule(t)(r)]
        if len(sel) < min_n:
            continue
        roi = sum(net_roi(r["open_prob"], r["won"]) for r in sel) / len(sel)
        if roi > best_roi:
            best, best_roi = t, roi
    return best


def walk_forward(rows: list[dict], train_frac: float = 0.7) -> dict:
    """Fit the steam threshold on the past, evaluate on the strictly-later future.
    Returns IS (train) and OOS (test) performance side by side — the honest comparison."""
    train, test = time_ordered_split(rows, train_frac)
    thr = fit_best_threshold(train)
    if thr is None:
        return {"error": "insufficient train sample to fit a threshold"}
    is_sel = [r for r in train if steam_rule(thr)(r)]
    oos_sel = [r for r in test if steam_rule(thr)(r)]
    return {"fitted_threshold": thr,
            "in_sample": evaluate(is_sel), "out_of_sample": evaluate(oos_sel),
            "in_sample_nofee": evaluate(is_sel, fee=False),
            "out_of_sample_nofee": evaluate(oos_sel, fee=False)}


# ── ablation interface ───────────────────────────────────────────────────────
def ablation(rows: list[dict], train_frac: float = 0.7) -> list[dict]:
    """Incremental value of each filter layered onto the steam signal, evaluated OOS.
    (Within-strategy ablation; true source-system ablation needs a unified prediction
    that fuses Betting-Brain / MLBMA / Sharp features — see VERIFICATION-AUDIT.)"""
    _, test = time_ordered_split(rows, train_frac)
    configs = {
        "all_games (no signal)": lambda r: True,
        "steam>=0.04": steam_rule(0.04),
        "steam>=0.04 + liquid>=120k": lambda r: steam_rule(0.04)(r) and (r.get("volume") or 0) >= 120000,
        "steam>=0.04 + dog(open<0.45)": lambda r: steam_rule(0.04)(r) and (r.get("open_prob") or 1) < 0.45,
    }
    out = []
    for name, pred in configs.items():
        ev = evaluate([r for r in test if pred(r)])
        out.append({"config": name, **ev})
    return out


# ── thin Supabase loader ─────────────────────────────────────────────────────
def load_settled_ml_from_env(env_path: str) -> list[dict]:  # pragma: no cover (network)
    import json
    import urllib.request
    env = {}
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    url, key = env["SUPABASE_URL"], env["SUPABASE_KEY"]
    q = ("prediction_market_snapshots?market_type=eq.ml&settled=eq.true&won=not.is.null"
         "&open_prob=not.is.null&select=snapshot_time,open_prob,delta,won,implied_probability,volume")
    req = urllib.request.Request(url.rstrip("/") + "/rest/v1/" + q,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


def main():  # pragma: no cover
    import argparse
    import json
    p = argparse.ArgumentParser(description="Point-in-time OOS backtest of the steam strategy.")
    p.add_argument("--env", required=True)
    p.add_argument("--train-frac", type=float, default=0.7)
    args = p.parse_args()
    rows = load_settled_ml_from_env(args.env)
    print(f"loaded {len(rows)} settled ML snapshots")
    print("WALK-FORWARD:", json.dumps(walk_forward(rows, args.train_frac), indent=2))
    print("ABLATION (OOS):")
    for r in ablation(rows, args.train_frac):
        print("  ", r)


if __name__ == "__main__":
    main()
