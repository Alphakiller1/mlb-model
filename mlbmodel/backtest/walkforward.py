"""Executable, grouped walk-forward validation for market-movement strategies.

A movement signal is tradable only when the historical row contains the time the signal
was observable and the price available after that signal. Open-to-close movement cannot
be used to select a bet at the opening price.
"""
from __future__ import annotations

import json
import random
import urllib.request


def kalshi_fee(price: float) -> float:
    return 0.07 * price * (1.0 - price)


def net_roi(entry_prob: float, won: bool, *, fee: bool = True) -> float:
    """ROI per dollar staked at the executable contract entry price."""
    price = min(max(entry_prob, 1e-6), 1 - 1e-6)
    execution_fee = kalshi_fee(price) if fee else 0.0
    net = (1.0 - price - execution_fee) if won else (-price - execution_fee)
    return net / price


def evaluate(rows: list[dict], *, fee: bool = True) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    returns = [net_roi(row["entry_prob"], row["won"], fee=fee) for row in rows]
    wins = sum(1 for row in rows if row["won"])
    clv = sum(
        row["implied_probability"] - row["entry_prob"] for row in rows
    ) / n
    lower, upper = _bootstrap_ci(returns)
    return {
        "n": n,
        "win_rate": round(wins / n, 4),
        "roi": round(sum(returns) / n, 4),
        "roi_lb": round(lower, 4),
        "roi_ub": round(upper, 4),
        "clv": round(clv, 4),
    }


def _bootstrap_ci(
    values: list[float],
    iters: int = 2000,
    seed: int = 7,
) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(iters)
    )
    return means[int(0.025 * iters)], means[min(iters - 1, int(0.975 * iters))]


def steam_rule(threshold: float):
    """Enter after the observed point-in-time movement crosses a threshold."""
    return lambda row: (row.get("signal_delta") or 0.0) >= threshold


def executable_rows(rows: list[dict]) -> list[dict]:
    required = (
        "game_pk",
        "signal_time",
        "entry_prob",
        "signal_delta",
        "won",
        "implied_probability",
    )
    return [
        row for row in rows
        if all(row.get(key) is not None and row.get(key) != "" for key in required)
    ]


def time_ordered_split(
    rows: list[dict],
    train_frac: float = 0.7,
    time_key: str = "signal_time",
) -> tuple[list[dict], list[dict]]:
    """Split whole games by time so correlated contracts stay in one partition."""
    grouped: dict[object, list[dict]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(row.get("game_pk", f"missing-{index}"), []).append(row)
    games = sorted(
        grouped.values(),
        key=lambda group: min(str(row.get(time_key) or "") for row in group),
    )
    cut = int(len(games) * train_frac)
    return (
        [row for game in games[:cut] for row in game],
        [row for game in games[cut:] for row in game],
    )


def fit_best_threshold(
    train: list[dict],
    grid=(0.02, 0.03, 0.04, 0.05, 0.06),
    min_n: int = 20,
) -> float | None:
    best, best_roi = None, -1e9
    for threshold in grid:
        selected = [row for row in train if steam_rule(threshold)(row)]
        if len(selected) < min_n:
            continue
        roi = sum(
            net_roi(row["entry_prob"], row["won"]) for row in selected
        ) / len(selected)
        if roi > best_roi:
            best, best_roi = threshold, roi
    return best


def walk_forward(rows: list[dict], train_frac: float = 0.7) -> dict:
    tradable = executable_rows(rows)
    if not tradable:
        return {
            "error": (
                "no executable observations: require game_pk, signal_time, "
                "signal_delta, and entry_prob"
            )
        }
    train, test = time_ordered_split(tradable, train_frac)
    threshold = fit_best_threshold(train)
    if threshold is None:
        return {"error": "insufficient training sample to fit an executable threshold"}
    in_sample = [row for row in train if steam_rule(threshold)(row)]
    out_of_sample = [row for row in test if steam_rule(threshold)(row)]
    return {
        "fitted_threshold": threshold,
        "in_sample": evaluate(in_sample),
        "out_of_sample": evaluate(out_of_sample),
        "in_sample_nofee": evaluate(in_sample, fee=False),
        "out_of_sample_nofee": evaluate(out_of_sample, fee=False),
    }


def ablation(rows: list[dict], train_frac: float = 0.7) -> list[dict]:
    _, test = time_ordered_split(executable_rows(rows), train_frac)
    configs = {
        "all executable entries": lambda row: True,
        "steam>=0.04": steam_rule(0.04),
        "steam>=0.04 + liquid>=120k": (
            lambda row: steam_rule(0.04)(row)
            and (row.get("volume") or 0) >= 120000
        ),
        "steam>=0.04 + dog(entry<0.45)": (
            lambda row: steam_rule(0.04)(row)
            and (row.get("entry_prob") or 1) < 0.45
        ),
    }
    return [
        {"config": name, **evaluate([row for row in test if predicate(row)])}
        for name, predicate in configs.items()
    ]


def load_settled_ml_from_env(env_path: str) -> list[dict]:  # pragma: no cover
    env = {}
    for raw in open(env_path, encoding="utf-8"):
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    url, key = env["SUPABASE_URL"], env["SUPABASE_KEY"]
    query = (
        "prediction_market_snapshots?market_type=eq.ml&settled=eq.true"
        "&won=not.is.null&entry_prob=not.is.null"
        "&select=game_pk,signal_time,entry_prob,signal_delta,won,"
        "implied_probability,volume"
    )
    request = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/{query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode())


def main():  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(
        description="Executable point-in-time OOS test of a steam strategy."
    )
    parser.add_argument("--env", required=True)
    parser.add_argument("--train-frac", type=float, default=0.7)
    args = parser.parse_args()
    rows = load_settled_ml_from_env(args.env)
    print(f"loaded {len(rows)} executable settled ML observations")
    print(json.dumps(walk_forward(rows, args.train_frac), indent=2))


if __name__ == "__main__":
    main()
