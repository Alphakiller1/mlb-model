"""End-to-end: the original rate construction vs the rebuilt matrix, on the same holdout.

Combines everything that changed in the projection path — per-market rate shrinkage, the
fitted opponent-strikeout term, and the BABIP/rest terms on Outs — and scores it against the
construction the engine shipped before. Point-in-time throughout; fit on the earlier 70% of
the season by date, scored on the later 30%.

This does NOT emulate the whole live engine (it has no pitch mix, weather, umpire or posted
lineups, none of which exist historically). It measures the spine: the pitcher's own rates
plus the fitted matchup terms, which is where the over-dispersion lived.

Run:  PYTHONPATH=. python scripts/validate_prop_matrix.py
"""
from __future__ import annotations

import numpy as np

from mlbmodel.props import matrix as mx
from scripts.factor_study import TRAIN_FRAC, add_features, load_starts
from scripts.fit_rate_shrinkage import build, engine_rate, shrunk_rate


def report(label: str, projected: np.ndarray, actual: np.ndarray) -> tuple:
    keep = np.isfinite(projected) & np.isfinite(actual)
    projected, actual = projected[keep], actual[keep]
    sse = float(np.sum((projected - actual) ** 2))
    sst = float(np.sum((actual - actual.mean()) ** 2))
    slope = float(np.polyfit(projected, actual, 1)[0])
    return label, 1 - sse / sst, slope, float(np.sqrt(sse / len(actual))), float(
        np.mean(np.abs(projected - actual))
    )


def main() -> None:
    rates = build(load_starts())
    rates = rates[rates["starts_before"] >= 2].copy()
    feats, _ = add_features(load_starts())
    feats = feats[["date", "game_pk", "pitcher_id", "so_all", "luck_babip", "rest_days",
                   "p_outs_mean"]]
    frame = rates.merge(feats, on=["date", "game_pk", "pitcher_id"], how="left")
    frame = frame.dropna(subset=["so_all", "p_outs_mean"])
    cut = int(len(frame) * TRAIN_FRAC)
    train, test = frame.iloc[:cut], frame.iloc[cut:]
    print(f"starts {len(frame)}   holdout {len(test)}\n")

    print(f"{'market':6s} {'construction':34s} {'R2 vs league':>13s} {'slope':>8s} {'RMSE':>8s} {'MAE':>8s}")
    print("-" * 84)

    # ---- strikeouts ----
    league_k = float(train["K"].sum() / train["bf"].sum())
    bf = test["bf"].to_numpy(dtype=float)
    actual_k = test["K"].to_numpy(dtype=float)
    before_k = engine_rate(test, "K", league_k) * bf
    shrunk_k = shrunk_rate(test, "K", league_k, mx.RATE_SHRINK_BF["k"]) * bf
    after_k = shrunk_k + mx.OPPONENT_K_WEIGHT * (test["so_all"].to_numpy() - 1.0)
    for row in (
        report("original: season+L14, unshrunk", before_k, actual_k),
        report("+ per-market shrinkage", shrunk_k, actual_k),
        report("+ opponent K term (shipped)", after_k, actual_k),
    ):
        print(f"{'K':6s} {row[0]:34s} {row[1]:+13.4f} {row[2]:8.3f} {row[3]:8.4f} {row[4]:8.4f}")
    print()

    # ---- walks ----
    league_bb = float(train["BB"].sum() / train["bf"].sum())
    actual_bb = test["BB"].to_numpy(dtype=float)
    for row in (
        report("original: season+L14, unshrunk",
               engine_rate(test, "BB", league_bb) * bf, actual_bb),
        report("+ per-market shrinkage (shipped)",
               shrunk_rate(test, "BB", league_bb, mx.RATE_SHRINK_BF["bb"]) * bf, actual_bb),
    ):
        print(f"{'BB':6s} {row[0]:34s} {row[1]:+13.4f} {row[2]:8.3f} {row[3]:8.4f} {row[4]:8.4f}")
    print()

    # ---- hits ----
    league_h = float(train["H"].sum() / train["bf"].sum())
    actual_h = test["H"].to_numpy(dtype=float)
    for row in (
        report("original: season+L14, unshrunk",
               engine_rate(test, "H", league_h) * bf, actual_h),
        report("+ per-market shrinkage (shipped)",
               shrunk_rate(test, "H", league_h, mx.RATE_SHRINK_BF["h"]) * bf, actual_h),
    ):
        print(f"{'H':6s} {row[0]:34s} {row[1]:+13.4f} {row[2]:8.3f} {row[3]:8.4f} {row[4]:8.4f}")
    print()

    # ---- outs ----
    actual_o = test["outs"].to_numpy(dtype=float)
    base_o = test["p_outs_mean"].to_numpy(dtype=float)
    after_o = (
        base_o
        + mx.BABIP_OUTS_WEIGHT * np.clip(test["luck_babip"].to_numpy(), -0.06, 0.06)
        + mx.REST_OUTS_WEIGHT * (np.clip(test["rest_days"].to_numpy(), 3, 10) - 5.0)
    )
    for row in (
        report("original: pitcher outs mean", base_o, actual_o),
        report("+ regression & rest (shipped)", after_o, actual_o),
    ):
        print(f"{'Outs':6s} {row[0]:34s} {row[1]:+13.4f} {row[2]:8.3f} {row[3]:8.4f} {row[4]:8.4f}")

    print("\nslope 1.000 = the projection's spread exactly matches its predictive content;")
    print("below 1.000 = spread too wide, which is what manufactures edges against the market.")


if __name__ == "__main__":
    main()
