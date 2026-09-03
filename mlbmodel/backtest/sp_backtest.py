"""Walk-forward validation harness for starting-pitcher projections.

Every projection here is built only from information available before first pitch of the
start being predicted. Two rules make that true, and are the reason this module exists:

1. Pitcher form uses ``shift(1).expanding()`` -- a start never informs itself.
2. Opponent offence is rebuilt **from this log**, as the running total of what a club did
   against every starter it had already faced. The ``opponent_*`` columns shipped in
   ``sp_game_log.csv`` cannot be used: they are a back-join of the season-to-date team
   index onto every historical row (all 30 clubs carry exactly one distinct value for the
   whole season), so on opening day they already encode end-of-season knowledge.

A projection is scored against two baselines -- the league mean and the pitcher's own
shrunk prior -- because a projection that cannot beat "predict this pitcher's average" is
adding no matchup information, whatever its raw correlation looks like.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

COUNT_COLUMNS = ("K", "BB", "H", "ER", "R", "HR", "pitches", "strikes")


def innings_to_outs(value) -> float:
    """MLB innings notation (6.1 = six and one third) -> outs."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    whole = int(number)
    partial = round((number - whole) * 10)
    return whole * 3 + (partial if partial in (1, 2) else 0)


def load_starts(path: str) -> pd.DataFrame:
    """Read the SP game log into one clean, chronologically sorted row per start."""
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"])
    for column in COUNT_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["outs"] = frame["IP"].map(innings_to_outs)
    frame["bf"] = pd.to_numeric(frame["batters_faced"], errors="coerce")
    frame = frame[(frame["bf"] > 0) & frame["outs"].notna()].copy()
    return frame.sort_values(["date", "game_pk", "pitcher_id"]).reset_index(drop=True)


def league_rates(frame: pd.DataFrame) -> dict[str, float]:
    """Pooled league rates -- the prior every thin sample is shrunk toward."""
    batters = float(frame["bf"].sum())
    outs = float(frame["outs"].sum())
    return {
        "k": float(frame["K"].sum()) / batters,
        "bb": float(frame["BB"].sum()) / batters,
        "h": float(frame["H"].sum()) / batters,
        "hr": float(frame["HR"].sum()) / batters,
        "er_per_out": float(frame["ER"].sum()) / outs,
        "outs": float(frame["outs"].mean()),
        "bf_per_out": batters / outs,
    }


def add_pitcher_priors(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach each pitcher's prior-only workload and rate history."""
    frame = frame.sort_values(["pitcher_id", "date", "game_pk"]).copy()
    grouped = frame.groupby("pitcher_id", sort=False)
    frame["p_starts"] = grouped.cumcount()
    frame["p_bf"] = grouped["bf"].transform(lambda s: s.shift().expanding().sum())
    frame["p_outs_total"] = grouped["outs"].transform(lambda s: s.shift().expanding().sum())
    frame["p_outs_mean"] = grouped["outs"].transform(lambda s: s.shift().expanding().mean())
    frame["p_outs_l3"] = grouped["outs"].transform(
        lambda s: s.shift().rolling(3, min_periods=1).mean()
    )
    for key, column in (("k", "K"), ("bb", "BB"), ("h", "H"), ("hr", "HR"), ("er", "ER")):
        frame[f"p_{key}_num"] = grouped[column].transform(lambda s: s.shift().expanding().sum())
    return frame


def add_opponent_priors(frame: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time opponent offence: what this club did to the starters it already faced.

    This is the honest replacement for the back-joined ``opponent_OSI``/``ABQ``/``RCV``
    columns, and it is built from the same log so it needs no external source.
    """
    frame = frame.sort_values(["opponent_team", "date", "game_pk"]).copy()
    grouped = frame.groupby("opponent_team", sort=False)
    frame["o_games"] = grouped.cumcount()
    frame["o_bf"] = grouped["bf"].transform(lambda s: s.shift().expanding().sum())
    frame["o_outs"] = grouped["outs"].transform(lambda s: s.shift().expanding().sum())
    for key, column in (("k", "K"), ("bb", "BB"), ("h", "H"), ("hr", "HR"), ("er", "ER")):
        frame[f"o_{key}_num"] = grouped[column].transform(lambda s: s.shift().expanding().sum())
    return frame


def shrunk_rate(numerator, denominator, prior: float, strength: float) -> np.ndarray:
    """Beta-binomial posterior mean: (events + strength*prior) / (trials + strength)."""
    numerator = np.nan_to_num(np.asarray(numerator, dtype=float), nan=0.0)
    denominator = np.nan_to_num(np.asarray(denominator, dtype=float), nan=0.0)
    return (numerator + strength * prior) / (denominator + strength)


@dataclass
class Scorecard:
    """Accuracy of one projected market against realised outcomes."""

    market: str
    n: int
    projected_mean: float
    actual_mean: float
    bias: float
    mae: float
    rmse: float
    correlation: float
    r2_vs_league: float
    r2_vs_pitcher_prior: float
    projected_sd: float
    actual_sd: float

    def row(self) -> str:
        return (
            f"{self.market:9} {self.n:5d} {self.projected_mean:7.2f} {self.actual_mean:7.2f} "
            f"{self.bias:+6.2f} {self.mae:6.2f} {self.rmse:6.2f} {self.correlation:6.3f} "
            f"{self.r2_vs_league:+8.3f} {self.r2_vs_pitcher_prior:+9.3f}"
        )


HEADER = (
    f"{'market':9} {'n':>5} {'proj':>7} {'actual':>7} {'bias':>6} {'MAE':>6} {'RMSE':>6} "
    f"{'corr':>6} {'R2_lg':>8} {'R2_prior':>9}"
)


def score(market: str, projected, actual, prior_baseline=None) -> Scorecard:
    """Score a projection against the league mean and, when given, the pitcher prior."""
    projected = np.asarray(projected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    keep = np.isfinite(projected) & np.isfinite(actual)
    if prior_baseline is not None:
        prior_baseline = np.asarray(prior_baseline, dtype=float)
        keep &= np.isfinite(prior_baseline)
        prior_baseline = prior_baseline[keep]
    projected, actual = projected[keep], actual[keep]
    n = len(actual)
    if n == 0:
        return Scorecard(market, 0, *([math.nan] * 11))
    residual = projected - actual
    sse = float(np.sum(residual**2))
    sst = float(np.sum((actual - actual.mean()) ** 2))
    sse_prior = (
        float(np.sum((prior_baseline - actual) ** 2)) if prior_baseline is not None else math.nan
    )
    sd_p, sd_a = float(np.std(projected)), float(np.std(actual))
    correlation = (
        float(np.mean((projected - projected.mean()) * (actual - actual.mean())) / (sd_p * sd_a))
        if sd_p > 0 and sd_a > 0
        else 0.0
    )
    return Scorecard(
        market=market,
        n=n,
        projected_mean=float(projected.mean()),
        actual_mean=float(actual.mean()),
        bias=float(residual.mean()),
        mae=float(np.mean(np.abs(residual))),
        rmse=math.sqrt(sse / n),
        correlation=correlation,
        r2_vs_league=1 - sse / sst if sst > 0 else math.nan,
        r2_vs_pitcher_prior=(
            1 - sse / sse_prior if isinstance(sse_prior, float) and sse_prior > 0 else math.nan
        ),
        projected_sd=sd_p,
        actual_sd=sd_a,
    )


def build_dataset(
    path: str,
    *,
    min_prior_starts: int = 3,
    min_opponent_games: int = 10,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Log -> modelling frame carrying point-in-time pitcher and opponent history."""
    frame = load_starts(path)
    priors = league_rates(frame)
    frame = add_pitcher_priors(frame)
    frame = add_opponent_priors(frame)
    frame = frame[
        (frame["p_starts"] >= min_prior_starts) & (frame["o_games"] >= min_opponent_games)
    ]
    return frame.sort_values(["date", "game_pk"]).reset_index(drop=True), priors
