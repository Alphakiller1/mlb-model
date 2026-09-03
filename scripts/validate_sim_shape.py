"""Do the simulation's shape constants match reality?

This matters more now than it used to. Prices used to be a normal refitted to (mean, sd), so
only two moments of the simulation reached the board. They are now read straight off the
simulated distribution, which means every shape constant in the sampler is priced directly --
and none of them has ever been checked against an actual season.

Checked here, all against `sp_game_log.csv`:

  * batters faced per inning, sampled as normal(4.25, 0.16)
  * the innings-pitched spread, `ip_sd` clipped to [0.65, 1.35]
  * the earned-run overdispersion shape, gamma(4.5)
  * the first-five-innings earned-run shape, gamma(5.0), against the log's own `f5_er`

Run:  PYTHONPATH=. python scripts/validate_sim_shape.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mlbmodel.props.model import _innings


def load() -> pd.DataFrame:
    frame = pd.read_csv("data/sp_game_log.csv")
    for column in ("ER", "K", "BB", "H", "batters_faced", "f5_er"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame["ip"] = frame["IP"].map(_innings)
    frame["outs"] = frame["ip"] * 3
    frame = frame[(frame["outs"] > 0) & frame["batters_faced"].notna()].copy()
    return frame


def batters_per_inning(frame: pd.DataFrame) -> None:
    ratio = frame["batters_faced"] / frame["ip"]
    ratio = ratio[np.isfinite(ratio) & (ratio > 1) & (ratio < 15)]
    print("BATTERS FACED PER INNING — sampled as normal(4.25, 0.16)")
    print(f"  realised mean {ratio.mean():.3f}   sd {ratio.std():.3f}   n={len(ratio)}")
    print("  shipped       4.250            0.160")
    print(f"  -> mean is {'HIGH' if ratio.mean() < 4.25 else 'LOW'} by "
          f"{abs(ratio.mean() - 4.25):.3f} batters/inning; the sd is understated "
          f"{ratio.std() / 0.16:.1f}x")
    # A start's batters faced is bounded below by outs; the ratio is high for short outings.
    for low, high, label in ((0, 12, "<4 IP"), (12, 18, "4-6 IP"), (18, 30, "6+ IP")):
        chunk = frame[(frame["outs"] >= low) & (frame["outs"] < high)]
        sub = (chunk["batters_faced"] / chunk["ip"]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) > 30:
            print(f"     {label:8s} mean {sub.mean():.3f}  sd {sub.std():.3f}  n={len(sub)}")


def innings_spread(frame: pd.DataFrame) -> None:
    per_pitcher = frame.groupby("pitcher_id")["ip"].agg(["std", "count"])
    per_pitcher = per_pitcher[per_pitcher["count"] >= 5]["std"].dropna()
    print("\nINNINGS SPREAD PER PITCHER — `ip_sd` clipped to [0.65, 1.35]")
    print(f"  realised median {per_pitcher.median():.3f}   "
          f"p10 {per_pitcher.quantile(0.10):.3f}   p90 {per_pitcher.quantile(0.90):.3f}"
          f"   n={len(per_pitcher)}")
    below = (per_pitcher < 0.65).mean() * 100
    above = (per_pitcher > 1.35).mean() * 100
    print(f"  clipped low {below:.0f}% of pitchers, clipped high {above:.0f}%")


def earned_run_shape(frame: pd.DataFrame) -> None:
    """Compare realised ER dispersion to what gamma(shape)+Poisson produces."""
    print("\nEARNED-RUN OVERDISPERSION — sampled as Poisson(gamma(shape=4.5, scale=mean/4.5))")
    # Group starts by their expected ER (proxied by the pitcher's own rate x that start's outs)
    rate = frame.groupby("pitcher_id")["ER"].transform("sum") / frame.groupby("pitcher_id")["outs"].transform("sum")
    expected = rate * frame["outs"]
    data = pd.DataFrame({"expected": expected, "actual": frame["ER"]}).dropna()
    data = data[(data["expected"] > 0.3) & (data["expected"] < 8)]
    bins = pd.cut(data["expected"], [0.3, 1.5, 2.0, 2.5, 3.0, 4.0, 8.0])
    print(f"  {'expected ER':>14s} {'n':>5s} {'realised mean':>14s} {'realised var':>13s} "
          f"{'var/mean':>9s} {'gamma4.5 var/mean':>18s}")
    for interval, chunk in data.groupby(bins, observed=True):
        if len(chunk) < 40:
            continue
        mean = chunk["actual"].mean()
        var = chunk["actual"].var()
        # Poisson-gamma: var = mean + mean^2/shape  ->  var/mean = 1 + mean/shape
        predicted = 1 + chunk["expected"].mean() / 4.5
        print(f"  {str(interval):>14s} {len(chunk):5d} {mean:14.3f} {var:13.3f} "
              f"{var / mean:9.3f} {predicted:18.3f}")
    overall_mean = data["actual"].mean()
    overall_var = data["actual"].var()
    implied_shape = overall_mean**2 / max(1e-9, overall_var - overall_mean)
    print(f"  overall var/mean {overall_var / overall_mean:.3f} -> implied gamma shape "
          f"{implied_shape:.2f} (shipped 4.5)")


def f5_shape(frame: pd.DataFrame) -> None:
    data = frame[frame["f5_er"].notna()].copy()
    if len(data) < 100:
        print("\nFIRST-FIVE EARNED RUNS — no usable f5_er column")
        return
    print(f"\nFIRST-FIVE EARNED RUNS — sampled as Poisson(gamma(shape=5.0)), n={len(data)}")
    mean = data["f5_er"].mean()
    var = data["f5_er"].var()
    implied = mean**2 / max(1e-9, var - mean)
    print(f"  realised mean {mean:.3f}  var {var:.3f}  var/mean {var / mean:.3f}")
    print(f"  implied gamma shape {implied:.2f} (shipped 5.0)")
    full = data["ER"].mean()
    print(f"  f5 ER is {mean / full * 100:.0f}% of full-game ER "
          f"(the engine assumes min(5, IP)/IP = {min(5.0, data['ip'].mean()) / data['ip'].mean() * 100:.0f}%)")


def main() -> None:
    frame = load()
    print(f"starts: {len(frame)}\n")
    batters_per_inning(frame)
    innings_spread(frame)
    earned_run_shape(frame)
    f5_shape(frame)


if __name__ == "__main__":
    main()
