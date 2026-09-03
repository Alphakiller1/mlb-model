"""Should the per-batter rates be shrunk, and by how much?

The engine shrinks only `skill_era`, by `starts / (starts + 6)`. The three rates that actually
drive the K, BB and H projections -- `k_rate`, `bb_rate`, `h_rate` -- are used raw: a season
number blended with a 14-day number, plus a trend nudge. A pitcher with two starts contributes
his unregressed rate, which is most of why the shipped projections were spread about twice as
wide as their predictive content justified.

This A/Bs the engine's construction against a beta-binomial posterior at the shrinkage
strengths already fitted in `mlbmodel.props.challenger.FITTED`, walk-forward and
point-in-time, and re-fits those strengths on this log so the shipped constants are
defensible rather than borrowed.

Run:  PYTHONPATH=. python scripts/fit_rate_shrinkage.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.factor_study import TRAIN_FRAC, load_starts

# Recent-form window the engine blends in (its `l14` table is a 14-day cut).
RECENT_DAYS = 14
MARKETS = (
    # market, event column, denominator, the strength challenger fitted (batters faced)
    ("K", "K", "bf", 113.0),
    ("BB", "BB", "bf", 193.0),
    ("H", "H", "bf", 461.0),
)


def build(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values(["pitcher_id", "date"]).reset_index(drop=True)
    grouped = frame.groupby("pitcher_id", sort=False)
    frame["prior_bf"] = grouped["bf"].transform(lambda s: s.shift(1).expanding().sum())
    frame["starts_before"] = grouped.cumcount()
    for _market, column, _den, _strength in MARKETS:
        frame[f"prior_{column}"] = grouped[column].transform(
            lambda s: s.shift(1).expanding().sum()
        )
    # Recent-form window: the same events restricted to the trailing 14 days before the start.
    recent_events = {column: [] for _m, column, _d, _s in MARKETS}
    recent_bf = []
    for pitcher_id, group in frame.groupby("pitcher_id", sort=False):
        dates = group["date"].to_numpy()
        for position in range(len(group)):
            cutoff = dates[position] - np.timedelta64(RECENT_DAYS, "D")
            window = group.iloc[:position]
            window = window[window["date"].to_numpy() >= cutoff]
            recent_bf.append(float(window["bf"].sum()))
            for _m, column, _d, _s in MARKETS:
                recent_events[column].append(float(window[column].sum()))
    order = frame.groupby("pitcher_id", sort=False).cumcount().index
    frame.loc[order, "recent_bf"] = recent_bf
    for _m, column, _d, _s in MARKETS:
        frame.loc[order, f"recent_{column}"] = recent_events[column]
    return frame


def engine_rate(frame: pd.DataFrame, column: str, league: float) -> np.ndarray:
    """What the engine builds: season rate blended with the 14-day rate, unshrunk."""
    season = np.where(
        frame["prior_bf"] > 0, frame[f"prior_{column}"] / frame["prior_bf"].replace(0, np.nan), league
    )
    recent = np.where(
        frame["recent_bf"] > 0,
        frame[f"recent_{column}"] / frame["recent_bf"].replace(0, np.nan),
        season,
    )
    # `recent_weight = min(0.50, TBF / 140)`, exactly as in props/model.py
    weight = np.minimum(0.50, frame["recent_bf"].to_numpy() / 140.0)
    return np.nan_to_num(season, nan=league) * (1 - weight) + np.nan_to_num(recent, nan=league) * weight


def shrunk_rate(frame: pd.DataFrame, column: str, league: float, strength: float) -> np.ndarray:
    events = frame[f"prior_{column}"].fillna(0.0).to_numpy()
    batters = frame["prior_bf"].fillna(0.0).to_numpy()
    return (events + strength * league) / (batters + strength)


def score(projected: np.ndarray, actual: np.ndarray) -> tuple[float, float, float]:
    keep = np.isfinite(projected) & np.isfinite(actual)
    projected, actual = projected[keep], actual[keep]
    sse = float(np.sum((projected - actual) ** 2))
    sst = float(np.sum((actual - actual.mean()) ** 2))
    slope = float(np.polyfit(projected, actual, 1)[0]) if projected.std() > 1e-12 else float("nan")
    return 1 - sse / sst, slope, float(np.sqrt(sse / len(actual)))


def main() -> None:
    frame = build(load_starts())
    frame = frame[frame["starts_before"] >= 2].copy()
    cut = int(len(frame) * TRAIN_FRAC)
    train, test = frame.iloc[:cut], frame.iloc[cut:]
    print(f"starts: {len(frame)}   holdout {len(test)}\n")

    print("Projected COUNT for the start (rate x batters faced), scored on the holdout.")
    print(f"{'market':7s} {'construction':22s} {'R2 vs league':>13s} {'slope':>8s} {'RMSE':>8s}")
    print("-" * 64)
    shipped = {}
    for market, column, _den, borrowed in MARKETS:
        league = float(train[column].sum() / train["bf"].sum())
        actual = test[column].to_numpy(dtype=float)
        rows = []

        engine = engine_rate(test, column, league) * test["bf"].to_numpy()
        rows.append(("engine: season+L14, unshrunk", *score(engine, actual)))

        # Re-fit the strength on the TRAIN half only, then score on the holdout.
        best, best_sse = borrowed, None
        train_actual = train[column].to_numpy(dtype=float)
        for candidate in np.arange(20.0, 1400.0, 10.0):
            projected = shrunk_rate(train, column, league, candidate) * train["bf"].to_numpy()
            sse = float(np.sum((projected - train_actual) ** 2))
            if best_sse is None or sse < best_sse:
                best_sse, best = sse, float(candidate)

        rows.append((
            f"shrunk, challenger {borrowed:.0f} BF",
            *score(shrunk_rate(test, column, league, borrowed) * test["bf"].to_numpy(), actual),
        ))
        rows.append((
            f"shrunk, re-fit {best:.0f} BF",
            *score(shrunk_rate(test, column, league, best) * test["bf"].to_numpy(), actual),
        ))
        for label, r2, slope, rmse in rows:
            print(f"{market:7s} {label:22s} {r2:+13.4f} {slope:8.3f} {rmse:8.4f}")
        print()
        shipped[market] = (borrowed, best, league)

    print("Re-fit strengths vs the challenger's (stability check):")
    for market, (borrowed, best, league) in shipped.items():
        print(f"  {market:4s} challenger {borrowed:6.0f} BF   re-fit here {best:6.0f} BF"
              f"   league rate {league:.4f}")


if __name__ == "__main__":
    main()
