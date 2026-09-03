"""Optimise the two markets still left on defaults: earned runs, and the Outs luck term.

Earned runs got no matchup term (measured: none exists) but its *baseline* was never tested.
The engine builds it from `blended_era/9 * IP`, where `blended_era = 0.70*skill_era +
0.30*ERA` and `skill_era` is a FIP/xFIP blend shrunk by `starts/(starts+6)`. Every one of
those choices is a default nobody scored. This tries the alternatives.

Outs currently carries a BABIP-regression term. The factor study also showed the ERA-vs-skill
gap worth +0.29% alone, which was never shipped because the four-factor stack overfitted.
Tested here on its own, and jointly.

Run:  PYTHONPATH=. python scripts/fit_er_and_outs.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mlbmodel.props import matrix as mx
from scripts.factor_study import TRAIN_FRAC, add_features, load_starts


def score(projected, actual) -> tuple[float, float, float]:
    projected = np.asarray(projected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    keep = np.isfinite(projected) & np.isfinite(actual)
    projected, actual = projected[keep], actual[keep]
    sse = float(np.sum((projected - actual) ** 2))
    sst = float(np.sum((actual - actual.mean()) ** 2))
    slope = float(np.polyfit(projected, actual, 1)[0]) if projected.std() > 1e-9 else np.nan
    return 1 - sse / sst, slope, float(np.sqrt(sse / len(actual)))


def build() -> pd.DataFrame:
    frame, _ = add_features(load_starts())
    frame = frame[frame["p_starts"] >= 2].copy()
    grouped = frame.groupby("pitcher_id", sort=False)
    # Point-in-time season ERA and a FIP-shaped skill estimate, both from prior starts only.
    er = grouped["ER"].transform(lambda s: s.shift(1).expanding().sum())
    outs = grouped["outs"].transform(lambda s: s.shift(1).expanding().sum())
    frame["prior_er"] = er
    frame["prior_outs"] = outs
    frame["prior_starts"] = grouped.cumcount()
    frame["era_raw"] = np.where(outs > 0, er / (outs / 3), np.nan)
    return frame.dropna(subset=["p_outs_mean", "era_raw", "p_fip"])


def er_variants(train: pd.DataFrame, test: pd.DataFrame) -> None:
    league_er_out = float(train["ER"].sum() / train["outs"].sum())
    actual = test["ER"].to_numpy(dtype=float)
    projected_outs = test["p_outs_mean"].to_numpy(dtype=float)
    innings = projected_outs / 3.0
    results = []

    # 1. what ships: ERA-shaped, shrunk by starts/(starts+6) toward 4.20, blended 70/30
    starts = test["prior_starts"].to_numpy(dtype=float)
    shrink = starts / (starts + 6)
    skill = 4.20 + (test["p_fip"].to_numpy() - 4.20) * shrink
    blended = skill * 0.70 + test["era_raw"].to_numpy() * 0.30
    results.append(("shipped: 0.70*shrunk FIP + 0.30*ERA", blended / 9 * innings))

    # 2. per-out rate shrunk like the other markets, at a swept strength
    for strength in (0, 120, 248, 400, 700, 1200):
        rate = (
            (test["prior_er"].to_numpy() + strength * league_er_out)
            / (test["prior_outs"].to_numpy() + strength)
        )
        results.append((f"ER/out shrunk at {strength:4d} outs", rate * projected_outs))

    # 3. pure FIP-shaped skill, no ERA component
    results.append(("shrunk FIP only, no ERA", skill / 9 * innings))
    # 4. league constant
    results.append(("league mean (the bar)", np.full(len(test), league_er_out) * projected_outs))

    print(f"{'earned-run construction':38s} {'R2':>9s} {'slope':>8s} {'RMSE':>8s}")
    print("-" * 66)
    best = (None, -9e9)
    for label, projection in results:
        r2, slope, rmse = score(projection, actual)
        if r2 > best[1]:
            best = (label, r2)
        print(f"{label:38s} {r2:+9.4f} {slope:8.3f} {rmse:8.4f}")
    print(f"  best: {best[0]}")


def outs_variants(train: pd.DataFrame, test: pd.DataFrame) -> None:
    actual = test["outs"].to_numpy(dtype=float)
    base = test["p_outs_mean"].to_numpy(dtype=float)

    def fit_weight(feature: str, clip: tuple[float, float]) -> float:
        x = np.clip(train[feature].to_numpy(dtype=float), *clip)
        y = train["outs"].to_numpy(dtype=float) - train["p_outs_mean"].to_numpy(dtype=float)
        keep = np.isfinite(x) & np.isfinite(y)
        return float(np.polyfit(x[keep], y[keep], 1)[0])

    babip = np.clip(test["luck_babip"].to_numpy(dtype=float), -0.06, 0.06)
    rest = np.clip(test["rest_days"].to_numpy(dtype=float), 3, 10) - 5.0
    era_gap = np.clip(test["luck_era"].to_numpy(dtype=float), -2.5, 2.5)
    w_era = fit_weight("luck_era", (-2.5, 2.5))

    shipped = base + mx.BABIP_OUTS_WEIGHT * babip + mx.REST_OUTS_WEIGHT * rest
    variants = [
        ("baseline: pitcher outs mean", base),
        ("shipped: + BABIP + rest", shipped),
        ("shipped + ERA-vs-skill gap", shipped + w_era * era_gap),
        ("ERA-vs-skill gap alone", base + w_era * era_gap),
    ]
    print(f"\n{'outs construction':38s} {'R2':>9s} {'slope':>8s} {'RMSE':>8s}")
    print("-" * 66)
    for label, projection in variants:
        r2, slope, rmse = score(projection, actual)
        print(f"{label:38s} {r2:+9.4f} {slope:8.3f} {rmse:8.4f}")
    print(f"  fitted ERA-gap weight: {w_era:+.4f} outs per run of gap")


def main() -> None:
    frame = build()
    cut = int(len(frame) * TRAIN_FRAC)
    train, test = frame.iloc[:cut], frame.iloc[cut:]
    print(f"starts {len(frame)}   holdout {len(test)}\n")
    er_variants(train, test)
    outs_variants(train, test)


if __name__ == "__main__":
    main()
