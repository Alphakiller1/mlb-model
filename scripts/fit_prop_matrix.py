"""Fit the shipped pitcher-prop matrix constants, and validate them out of sample.

This produces the numbers hard-coded in `mlbmodel.props.matrix.FITTED`. Every feature is
point-in-time (built only from starts before the one being predicted) and every reported
number is from the held-out later 30% of the season by date.

Only factors that survived `scripts/factor_study.py` are fitted here. The ones that did not
are listed in `docs/PROP-MATRIX-FINDINGS.md` with the measurement that killed them, so a
future reader can see they were tested rather than forgotten.

Run:  PYTHONPATH=. python scripts/fit_prop_matrix.py
"""
from __future__ import annotations

import numpy as np

from scripts.factor_study import TRAIN_FRAC, add_features, load_starts


def fit_single(frame, target: str, base: str, feature: str, centre: float):
    """Fit residual ~ w*(feature - centre) on train; report the OOS gain on holdout."""
    data = frame.dropna(subset=[target, base, feature])
    cut = int(len(data) * TRAIN_FRAC)
    train, test = data.iloc[:cut], data.iloc[cut:]
    x_train = (train[feature] - centre).to_numpy()
    y_train = (train[target] - train[base]).to_numpy()
    design = np.column_stack([np.ones(len(train)), x_train])
    beta, *_ = np.linalg.lstsq(design, y_train, rcond=None)
    intercept, weight = float(beta[0]), float(beta[1])
    x_test = (test[feature] - centre).to_numpy()
    y_test = (test[target] - test[base]).to_numpy()
    # Ship the slope only. The intercept is a train-period level offset, not matchup
    # information, and carrying it forward would bake a stale season mean into every start.
    predicted = weight * x_test
    sse_base = float(np.sum(y_test**2))
    sse_new = float(np.sum((y_test - predicted) ** 2))
    gain = (1 - sse_new / sse_base) * 100
    return weight, intercept, gain, len(test)


def main() -> None:
    frame, _ = add_features(load_starts())
    frame = frame[frame["p_starts"] >= 3].copy()
    frame["proj_k"] = frame["p_k"] * frame["bf"]
    frame["proj_outs"] = frame["p_outs_mean"]

    print("Fitted on the earlier 70% by date; gain measured on the held-out later 30%.\n")
    print(f"{'term':44s} {'weight':>9s} {'OOS gain':>10s} {'n_oos':>6s}")
    print("-" * 74)

    specs = [
        ("K", "proj_k", "so_all", 1.0, "K    += w * (opp K rate / league - 1)"),
        ("outs", "proj_outs", "luck_babip", 0.0, "Outs += w * (.295 - BABIP to date)"),
        ("outs", "proj_outs", "rest_days", 5.0, "Outs += w * (rest days - 5)"),
    ]
    fitted = {}
    for target, base, feature, centre, label in specs:
        weight, _intercept, gain, n = fit_single(frame, target, base, feature, centre)
        fitted[(target, feature)] = weight
        print(f"{label:44s} {weight:+9.3f} {gain:+9.2f}% {n:6d}")

    # --- combined check: do the shipped terms together still beat the baseline? ---
    print("\nCombined shipped matrix vs the self-history baseline, on the same holdout:")
    data = frame.dropna(subset=["K", "proj_k", "so_all", "home", "outs", "proj_outs",
                                "luck_babip", "rest_days"])
    test = data.iloc[int(len(data) * TRAIN_FRAC):]

    # home/away is deliberately absent: it scored +0.61% with a free intercept but
    # -0.49% once the intercept was dropped, i.e. it was a season level offset, not a
    # matchup effect. Slope-only is the honest test because only the slope ships.
    k_adj = fitted[("K", "so_all")] * (test["so_all"] - 1.0)
    outs_adj = (
        fitted[("outs", "luck_babip")] * test["luck_babip"].clip(-0.06, 0.06)
        + fitted[("outs", "rest_days")] * (test["rest_days"].clip(3, 10) - 5.0)
    )
    for label, actual, baseline, adjusted in (
        ("K", test["K"], test["proj_k"], test["proj_k"] + k_adj),
        ("Outs", test["outs"], test["proj_outs"], test["proj_outs"] + outs_adj),
    ):
        base_sse = float(np.sum((baseline - actual) ** 2))
        new_sse = float(np.sum((adjusted - actual) ** 2))
        base_mae = float(np.mean(np.abs(baseline - actual)))
        new_mae = float(np.mean(np.abs(adjusted - actual)))
        verdict = "BETTER" if new_sse < base_sse else "WORSE"
        print(
            f"  {label:5s} n={len(test):4d}  RMSE {np.sqrt(base_sse/len(test)):.4f}"
            f" -> {np.sqrt(new_sse/len(test)):.4f}   MAE {base_mae:.4f} -> {new_mae:.4f}"
            f"   [{verdict}]"
        )

    print("\nCopy into mlbmodel/props/matrix.py::FITTED:")
    print(f"    OPPONENT_K_WEIGHT = {fitted[('K', 'so_all')]:.3f}")
    print(f"    BABIP_OUTS_WEIGHT = {fitted[('outs', 'luck_babip')]:.3f}")
    print(f"    REST_OUTS_WEIGHT  = {fitted[('outs', 'rest_days')]:.3f}")


if __name__ == "__main__":
    main()
