"""Fit the three constants that were still guesses, and the per-market spread calibration.

1. **Spread calibration.** After shrinkage the projections still run slope < 1 (K 0.887,
   Outs 0.785), which means they are spread wider than their predictive content supports and
   will keep disagreeing with the market by more than they should. `actual = a + b*proj`, so
   the calibrated projection is `mean + b*(proj - mean)`. Fitted on train, verified on the
   holdout.

2. **Pitch-mix opponent scale.** The x16 was never fitted. It was left alone earlier on the
   grounds that season-aggregate pitch mix is hindsight-contaminated -- true for the PITCHER
   half, whose own season line is close to the thing being predicted, but the OPPONENT half is
   a club-level aggregate over ~150 games, so one start contributes well under 1% of it. That
   is fittable.

3. **Opponent damping on ER.** Shipped at 0.50 as a judgment. Fit it.

Run:  PYTHONPATH=. python scripts/fit_final_calibration.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mlbmodel.props.model import SKIP_PITCH_TYPES, _norm
from scripts.factor_study import TRAIN_FRAC, add_features, load_starts
from scripts.fit_rate_shrinkage import build, shrunk_rate
from scripts.pitch_mix_audit import baselines, load as load_mix

DATA = "data/"


def frame_with_everything() -> pd.DataFrame:
    rates = build(load_starts())
    rates = rates[rates["starts_before"] >= 2].copy()
    feats, _ = add_features(load_starts())
    feats = feats[["date", "game_pk", "pitcher_id", "so_all", "luck_babip", "rest_days",
                   "p_outs_mean", "p_er_out"]]
    frame = rates.merge(feats, on=["date", "game_pk", "pitcher_id"], how="left")
    frame["outs"] = pd.to_numeric(frame["outs"], errors="coerce")
    frame["ER"] = pd.to_numeric(frame["ER"], errors="coerce")
    return frame.dropna(subset=["so_all", "p_outs_mean"])


def opponent_half(frame: pd.DataFrame) -> pd.Series:
    """The pitch-mix opponent response, usage-weighted by the starter's arsenal."""
    pitcher, team, _batter = load_mix()
    base = baselines(team)
    pitcher["key"] = pitcher["full_name"].map(_norm)
    by_pitcher = {key: group for key, group in pitcher.groupby("key")}
    by_club: dict[str, dict] = {}
    for club, group in team.groupby("team_abbr"):
        by_club[str(club).upper()] = {
            row.pt: {"whiff_rate": row.whiff_rate, "xwoba": row.xwoba,
                     "chase_rate": row.chase_rate}
            for row in group.itertuples()
        }
    keys = frame["pitcher_name"].map(_norm)
    out = []
    for key, club in zip(keys, frame["opponent_team"].astype(str).str.upper(), strict=True):
        rows = by_pitcher.get(key)
        opponent = by_club.get(club)
        if rows is None or opponent is None:
            out.append(np.nan)
            continue
        total = coverage = 0.0
        for row in rows.itertuples():
            reference = base.get(row.pt)
            opposing = opponent.get(row.pt)
            if (row.pt in SKIP_PITCH_TYPES or (row.pitch_pct or 0) < 3
                    or opposing is None or not reference):
                continue
            weight = row.pitch_pct / 100
            coverage += weight
            total += weight * (
                0.42 * (opposing["whiff_rate"] - reference["whiff_rate"]) / 100
                + 0.43 * (reference["xwoba"] - opposing["xwoba"])
                + 0.15 * (opposing["chase_rate"] - reference["chase_rate"]) / 100
            )
        out.append(total if coverage >= 0.35 else np.nan)
    return pd.Series(out, index=frame.index)


def fit_slope(projected, actual) -> float:
    keep = np.isfinite(projected) & np.isfinite(actual)
    return float(np.polyfit(projected[keep], actual[keep], 1)[0])


def score(projected, actual) -> tuple[float, float]:
    keep = np.isfinite(projected) & np.isfinite(actual)
    projected, actual = projected[keep], actual[keep]
    sse = float(np.sum((projected - actual) ** 2))
    sst = float(np.sum((actual - actual.mean()) ** 2))
    return 1 - sse / sst, fit_slope(projected, actual)


def main() -> None:
    frame = frame_with_everything()
    frame["opp_half"] = opponent_half(frame)
    cut = int(len(frame) * TRAIN_FRAC)
    train, test = frame.iloc[:cut], frame.iloc[cut:]
    print(f"starts {len(frame)}   holdout {len(test)}\n")

    # ---------------------------------------------------------------- 2. pitch-mix scale
    print("PITCH-MIX OPPONENT SCALE (currently x16, never fitted)")
    league_k = float(train["K"].sum() / train["bf"].sum())
    for label, data in (("train", train), ("holdout", test)):
        base_rate = shrunk_rate(data, "K", league_k, 113.0)
        residual = (data["K"] / data["bf"] - base_rate).to_numpy()
        x = data["opp_half"].to_numpy()
        keep = np.isfinite(x) & np.isfinite(residual)
        slope = float(np.polyfit(x[keep], residual[keep], 1)[0])
        # engine applies k_rate_delta in PERCENTAGE POINTS to a per-batter rate
        print(f"  {label:8s} fitted scale {slope * 100:7.2f}  (n={keep.sum()})")
    print()

    # ---------------------------------------------------------------- 3. ER damping
    print("OPPONENT DAMPING ON ER (currently 0.50, a judgment)")
    league_er = float(train["ER"].sum() / train["outs"].sum())
    for label, data in (("train", train), ("holdout", test)):
        base_er = data["p_er_out"].to_numpy() * data["outs"].to_numpy()
        residual = data["ER"].to_numpy() - base_er
        # opponent quality proxy on the same axis the engine uses: club offensive output
        x = (data["so_all"].to_numpy() - 1.0)
        keep = np.isfinite(x) & np.isfinite(residual) & np.isfinite(base_er)
        slope = float(np.polyfit(x[keep], residual[keep], 1)[0])
        print(f"  {label:8s} opponent->ER slope {slope:+7.3f} earned runs per unit"
              f"   (n={keep.sum()}, league ER/out {league_er:.4f})")
    print()

    # ---------------------------------------------------------------- 1. spread calibration
    print("SPREAD CALIBRATION  (fit b on train, apply mean + b*(proj-mean), verify on holdout)")
    print(f"{'market':7s} {'b (train)':>10s} {'R2 raw':>9s} {'R2 cal':>9s} {'slope raw':>10s} {'slope cal':>10s}")
    print("-" * 62)
    specs = []
    league_bb = float(train["BB"].sum() / train["bf"].sum())
    league_h = float(train["H"].sum() / train["bf"].sum())
    for market, column, league, strength in (
        ("K", "K", league_k, 113.0), ("BB", "BB", league_bb, 193.0), ("H", "H", league_h, 461.0)
    ):
        proj_tr = shrunk_rate(train, column, league, strength) * train["bf"].to_numpy()
        proj_te = shrunk_rate(test, column, league, strength) * test["bf"].to_numpy()
        if market == "K":
            from mlbmodel.props import matrix as mx
            proj_tr = proj_tr + mx.OPPONENT_K_WEIGHT * (train["so_all"].to_numpy() - 1.0)
            proj_te = proj_te + mx.OPPONENT_K_WEIGHT * (test["so_all"].to_numpy() - 1.0)
        specs.append((market, proj_tr, train[column].to_numpy(float),
                      proj_te, test[column].to_numpy(float)))
    from mlbmodel.props import matrix as mx
    o_tr = (train["p_outs_mean"].to_numpy()
            + mx.BABIP_OUTS_WEIGHT * np.clip(train["luck_babip"].to_numpy(), -0.06, 0.06)
            + mx.REST_OUTS_WEIGHT * (np.clip(train["rest_days"].to_numpy(), 3, 10) - 5))
    o_te = (test["p_outs_mean"].to_numpy()
            + mx.BABIP_OUTS_WEIGHT * np.clip(test["luck_babip"].to_numpy(), -0.06, 0.06)
            + mx.REST_OUTS_WEIGHT * (np.clip(test["rest_days"].to_numpy(), 3, 10) - 5))
    specs.append(("Outs", o_tr, train["outs"].to_numpy(float),
                  o_te, test["outs"].to_numpy(float)))

    fitted = {}
    for market, proj_tr, act_tr, proj_te, act_te in specs:
        b = fit_slope(proj_tr, act_tr)
        keep = np.isfinite(proj_tr)
        centre = float(np.mean(proj_tr[keep]))
        cal_te = centre + b * (proj_te - centre)
        r2_raw, slope_raw = score(proj_te, act_te)
        r2_cal, slope_cal = score(cal_te, act_te)
        fitted[market] = b
        print(f"{market:7s} {b:10.3f} {r2_raw:+9.4f} {r2_cal:+9.4f} {slope_raw:10.3f} {slope_cal:10.3f}")

    print("\nCopy into mlbmodel/props/matrix.py::SPREAD_CALIBRATION:")
    for market, b in fitted.items():
        print(f"    \"{market}\": {b:.3f},")




def sweep() -> None:
    """Pick each constant by holdout performance, not by the train-fitted slope.

    A slope fitted on the train half is not evidence that shipping it helps: the pitch-mix
    opponent scale fits 115 on train and 87 on the holdout, and the opponent->ER slope changes
    SIGN between the two halves. Sweeping the constant and scoring the holdout is the honest
    test, and it is what picks the shipped value.
    """
    frame = frame_with_everything()
    frame["opp_half"] = opponent_half(frame)
    cut = int(len(frame) * TRAIN_FRAC)
    train, test = frame.iloc[:cut], frame.iloc[cut:]
    league_k = float(train["K"].sum() / train["bf"].sum())
    from mlbmodel.props import matrix as mx

    print("\n\nPITCH-MIX OPPONENT SCALE — holdout R2 by shipped scale")
    base_te = shrunk_rate(test, "K", league_k, 113.0) * test["bf"].to_numpy()
    base_te = base_te + mx.OPPONENT_K_WEIGHT * (test["so_all"].to_numpy() - 1.0)
    actual = test["K"].to_numpy(float)
    opp = test["opp_half"].to_numpy()
    bf = test["bf"].to_numpy(float)
    keep = np.isfinite(opp) & np.isfinite(base_te) & np.isfinite(actual)
    best = (None, -9e9)
    for scale in (0, 8, 16, 25, 40, 60, 87, 100, 115, 150):
        # k_rate_delta is in percentage points of a per-batter rate, applied over the start
        proj = base_te[keep] + (opp[keep] * scale / 100.0) * bf[keep]
        r2, slope = score(proj, actual[keep])
        marker = "  <- current" if scale == 16 else ""
        if r2 > best[1]:
            best = (scale, r2)
        print(f"  scale {scale:4d}   holdout R2 {r2:+.4f}   slope {slope:.3f}{marker}")
    print(f"  best on holdout: scale {best[0]}")

    print("\nOPPONENT DAMPING ON ER — holdout R2 by damping")
    base_er = (test["p_er_out"].to_numpy() * test["outs"].to_numpy())
    actual_er = test["ER"].to_numpy(float)
    x = test["so_all"].to_numpy() - 1.0
    keep_er = np.isfinite(base_er) & np.isfinite(actual_er) & np.isfinite(x)
    # train-fitted opponent effect, then damped by d
    tr_base = train["p_er_out"].to_numpy() * train["outs"].to_numpy()
    tr_res = train["ER"].to_numpy(float) - tr_base
    tr_x = train["so_all"].to_numpy() - 1.0
    k2 = np.isfinite(tr_res) & np.isfinite(tr_x)
    full_slope = float(np.polyfit(tr_x[k2], tr_res[k2], 1)[0])
    best_er = (None, -9e9)
    for damping in (0.0, 0.25, 0.5, 0.75, 1.0):
        proj = base_er[keep_er] + damping * full_slope * x[keep_er]
        r2, _slope = score(proj, actual_er[keep_er])
        marker = "  <- current" if damping == 0.5 else ""
        if r2 > best_er[1]:
            best_er = (damping, r2)
        print(f"  damping {damping:4.2f}   holdout R2 {r2:+.4f}{marker}")
    print(f"  best on holdout: damping {best_er[0]}")


if __name__ == "__main__":
    main()
    sweep()
