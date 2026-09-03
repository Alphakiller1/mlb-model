"""What is each matrix factor actually worth to a pitcher prop? Point-in-time, walk-forward.

Every feature is built only from games strictly BEFORE the start being predicted
(Constitution STD-1/STD-5). Each factor is scored by the out-of-sample variance it removes
from the residual of a shrunk self-history baseline -- i.e. what it adds on top of "just
project this pitcher's own record". A factor that cannot beat that is not matchup
information, whatever its raw correlation looks like.

Opponent strength is rebuilt here from `batter_gamelog.csv` rather than read from the
`opponent_*` columns of `sp_game_log.csv`: those are a back-join of the season-to-date team
index onto every historical row (all 30 clubs carry one value for the whole season), so they
encode end-of-season knowledge on opening day.

The created-metric proxies (ABQ / OBR / RCV axes) use the same information the pipeline's
metrics are built from -- K-avoidance and walk discipline for ABQ, on-base for OBR, extra-base
and run conversion for RCV -- restricted to what was knowable at first pitch.

Run:  python scripts/factor_study.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mlbmodel.backtest.sp_backtest import innings_to_outs

SP_LOG = "data/sp_game_log.csv"
BATTER_LOG = r"C:\Users\chase\mlbma_pipeline\data\batter_gamelog.csv"
TRAIN_FRAC = 0.70
# Shrinkage strengths (in PA) for the point-in-time opponent metrics. Deliberately heavy:
# a club's true offensive quality moves slowly, and a light prior would let three good games
# masquerade as a matchup edge.
OPP_PRIOR_PA = 900.0
PLATOON_PRIOR_PA = 700.0


# --------------------------------------------------------------------------- loading
def load_starts() -> pd.DataFrame:
    frame = pd.read_csv(SP_LOG)
    frame["date"] = pd.to_datetime(frame["date"])
    for column in ("K", "BB", "H", "ER", "HR", "pitches", "batters_faced"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["outs"] = frame["IP"].map(innings_to_outs)
    frame["bf"] = frame["batters_faced"]
    frame = frame[(frame["bf"] > 0) & frame["outs"].notna()].copy()
    frame["hand"] = frame["pitcher_hand"].fillna("R").astype(str).str.upper().str[0]
    frame["home"] = (
        frame["home_away"].astype(str).str.lower().str.startswith("h")
    ).astype(float)
    return frame.sort_values(["date", "game_pk", "pitcher_id"]).reset_index(drop=True)


def _running_before(frame: pd.DataFrame, keys: list[str], columns: list[str]) -> pd.DataFrame:
    """Cumulative totals of `columns` over `keys`, EXCLUDING the current row's date."""
    daily = frame.groupby(keys + ["date"], as_index=False)[columns].sum()
    daily = daily.sort_values(keys + ["date"])
    grouped = daily.groupby(keys, sort=False)
    for column in columns:
        daily[f"cum_{column}"] = grouped[column].transform(
            lambda s: s.shift(1).expanding().sum()
        )
    return daily


def opponent_metrics() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Point-in-time team offence, overall and split by the hand of the starter faced."""
    bat = pd.read_csv(BATTER_LOG)
    bat["date"] = pd.to_datetime(bat["date"])
    for column in ("PA", "H", "HR", "BB", "SO", "TB", "R", "HBP", "2B", "3B"):
        bat[column] = pd.to_numeric(bat.get(column), errors="coerce").fillna(0.0)
    bat["hand"] = bat["opp_starter_hand"].fillna("R").astype(str).str.upper().str[0]
    league = {
        "so": bat["SO"].sum() / bat["PA"].sum(),
        "bb": bat["BB"].sum() / bat["PA"].sum(),
        "h": bat["H"].sum() / bat["PA"].sum(),
        "tb": bat["TB"].sum() / bat["PA"].sum(),
        "r": bat["R"].sum() / bat["PA"].sum(),
    }
    cols = ["PA", "SO", "BB", "H", "TB", "R"]

    overall = _running_before(bat, ["team"], cols)
    platoon = _running_before(bat, ["team", "hand"], cols)

    def rates(daily: pd.DataFrame, prior_pa: float, suffix: str) -> pd.DataFrame:
        out = daily[["team"] + (["hand"] if "hand" in daily else []) + ["date"]].copy()
        pa = daily["cum_PA"].fillna(0.0)
        for short, column in (("so", "SO"), ("bb", "BB"), ("h", "H"), ("tb", "TB"), ("r", "R")):
            numerator = daily[f"cum_{column}"].fillna(0.0)
            out[f"{short}{suffix}"] = (
                (numerator + prior_pa * league[short]) / (pa + prior_pa)
            ) / league[short]
        out[f"pa{suffix}"] = pa
        return out

    return (
        rates(overall, OPP_PRIOR_PA, "_all"),
        rates(platoon, PLATOON_PRIOR_PA, "_hand"),
        league,
    )


# --------------------------------------------------------------------------- features
def add_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    league = {
        "k": frame["K"].sum() / frame["bf"].sum(),
        "bb": frame["BB"].sum() / frame["bf"].sum(),
        "h": frame["H"].sum() / frame["bf"].sum(),
        "hr": frame["HR"].sum() / frame["bf"].sum(),
        "er_out": frame["ER"].sum() / frame["outs"].sum(),
    }
    grouped = frame.groupby("pitcher_id", sort=False)

    def prior(numerator: str, denominator: str, strength: float, base: float):
        num = grouped[numerator].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
        den = grouped[denominator].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
        return (num + strength * base) / (den + strength)

    # --- pitcher self-history: the baseline every factor has to beat ---
    frame["p_k"] = prior("K", "bf", 113.0, league["k"])
    frame["p_bb"] = prior("BB", "bf", 193.0, league["bb"])
    frame["p_h"] = prior("H", "bf", 461.0, league["h"])
    frame["p_hr"] = prior("HR", "bf", 923.0, league["hr"])
    frame["p_er_out"] = prior("ER", "outs", 248.0, league["er_out"])
    frame["p_starts"] = grouped.cumcount()
    frame["p_outs_mean"] = grouped["outs"].transform(
        lambda s: s.shift(1).expanding().mean()
    )

    # --- FATIGUE: rest, previous workload, rolling load ---
    frame["rest_days"] = (
        frame["date"] - grouped["date"].shift(1)
    ).dt.days.clip(upper=30)
    frame["prev_pitches"] = grouped["pitches"].shift(1)
    frame["load3"] = grouped["pitches"].transform(
        lambda s: s.shift(1).rolling(3).sum()
    )
    frame["short_rest"] = (frame["rest_days"] <= 4).astype(float)

    # --- REGRESSION / PROGRESSION: how much of the record so far was luck ---
    hits_bip = grouped.apply(
        lambda d: (d["H"] - d["HR"]).shift(1).expanding().sum(), include_groups=False
    ).reset_index(level=0, drop=True)
    bip = grouped.apply(
        lambda d: (d["bf"] - d["K"] - d["BB"] - d["HR"]).shift(1).expanding().sum(),
        include_groups=False,
    ).reset_index(level=0, drop=True)
    frame["p_babip"] = (hits_bip.fillna(0.0) + 60 * 0.295) / (bip.fillna(0.0) + 60)
    earned = grouped["ER"].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
    outs_run = grouped["outs"].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
    frame["p_era"] = (earned + 30 * league["er_out"] * 3) / (outs_run / 3 + 30)
    # FIP-shaped skill estimate from the same window, so (skill - results) is the luck gap.
    frame["p_fip"] = (
        (13 * frame["p_hr"] + 3 * frame["p_bb"] - 2 * frame["p_k"]) * 27 / 3 + 3.10
    )
    frame["luck_era"] = frame["p_fip"] - frame["p_era"]
    frame["luck_babip"] = 0.295 - frame["p_babip"]

    # --- BALLPARK: running park environment from prior games in that park only ---
    park = frame.groupby("stadium", sort=False)
    park_er = park["ER"].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
    park_outs = park["outs"].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
    frame["park_run"] = (
        (park_er + 400 * league["er_out"]) / (park_outs + 400)
    ) / league["er_out"]
    park_k = park["K"].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
    park_bf = park["bf"].transform(lambda s: s.shift(1).expanding().sum()).fillna(0.0)
    frame["park_k"] = ((park_k + 800 * league["k"]) / (park_bf + 800)) / league["k"]

    # --- CREATED METRICS (point-in-time proxies) + HANDEDNESS PLATOON ---
    overall, platoon, _ = opponent_metrics()
    frame = frame.merge(
        overall.rename(columns={"team": "opponent_team"}),
        on=["opponent_team", "date"],
        how="left",
    )
    frame = frame.merge(
        platoon.rename(columns={"team": "opponent_team"}),
        on=["opponent_team", "hand", "date"],
        how="left",
    )
    # ABQ axis: at-bat quality = walk discipline + strikeout avoidance.
    frame["abq_all"] = 0.5 * frame["bb_all"] + 0.5 * (2.0 - frame["so_all"])
    frame["abq_hand"] = 0.5 * frame["bb_hand"] + 0.5 * (2.0 - frame["so_hand"])
    # OBR axis: on-base production.  RCV axis: run conversion from that production.
    frame["obr_all"], frame["obr_hand"] = frame["h_all"], frame["h_hand"]
    frame["rcv_all"], frame["rcv_hand"] = frame["r_all"], frame["r_hand"]
    frame["osi_all"] = 0.40 * frame["obr_all"] + 0.35 * frame["rcv_all"] + 0.25 * frame["abq_all"]
    frame["osi_hand"] = (
        0.40 * frame["obr_hand"] + 0.35 * frame["rcv_hand"] + 0.25 * frame["abq_hand"]
    )
    # The PLATOON signal is what the hand-specific split adds OVER the club's overall rate.
    for axis in ("so", "bb", "h", "abq", "obr", "rcv", "osi"):
        frame[f"platoon_{axis}"] = frame[f"{axis}_hand"] - frame[f"{axis}_all"]
    return frame, league


# --------------------------------------------------------------------------- scoring
def oos_gain(frame: pd.DataFrame, target: str, base: str, features: list[str]):
    """Fit residual ~ features on the earlier 70%; score the gain on the later 30%."""
    data = frame.dropna(subset=[target, base] + features)
    if len(data) < 400:
        return None
    cut = int(len(data) * TRAIN_FRAC)
    train, test = data.iloc[:cut], data.iloc[cut:]
    y_train = (train[target] - train[base]).to_numpy()
    y_test = (test[target] - test[base]).to_numpy()
    x_train = np.column_stack([np.ones(len(train))] + [train[c].to_numpy() for c in features])
    x_test = np.column_stack([np.ones(len(test))] + [test[c].to_numpy() for c in features])
    beta, *_ = np.linalg.lstsq(x_train, y_train, rcond=None)
    predicted = x_test @ beta
    sse_base = float(np.sum(y_test**2))
    sse_new = float(np.sum((y_test - predicted) ** 2))
    gain = (1 - sse_new / sse_base) * 100 if sse_base > 0 else float("nan")
    corr = (
        float(np.corrcoef(predicted, y_test)[0, 1]) if float(np.std(predicted)) > 1e-12 else 0.0
    )
    return len(test), gain, corr, beta[1:]


TESTS = [
    ("K", "proj_k", ["platoon_so"], "K    <- handedness platoon (K axis)"),
    ("K", "proj_k", ["so_all"], "K    <- opponent K rate (created: ABQ K-avoid)"),
    ("K", "proj_k", ["abq_all"], "K    <- created metric ABQ"),
    ("K", "proj_k", ["osi_all"], "K    <- created metric OSI"),
    ("K", "proj_k", ["park_k"], "K    <- ballpark"),
    ("K", "proj_k", ["rest_days", "prev_pitches"], "K    <- fatigue"),
    ("K", "proj_k", ["home"], "K    <- home/away"),
    ("K", "proj_k", ["luck_era", "luck_babip"], "K    <- regression/progression"),
    ("ER", "proj_er", ["luck_era", "luck_babip"], "ER   <- regression/progression"),
    ("ER", "proj_er", ["park_run"], "ER   <- ballpark"),
    ("ER", "proj_er", ["platoon_osi"], "ER   <- handedness platoon (OSI axis)"),
    ("ER", "proj_er", ["osi_all"], "ER   <- created metric OSI"),
    ("ER", "proj_er", ["obr_all"], "ER   <- created metric OBR"),
    ("ER", "proj_er", ["rcv_all"], "ER   <- created metric RCV"),
    ("ER", "proj_er", ["abq_all"], "ER   <- created metric ABQ"),
    ("ER", "proj_er", ["rest_days", "prev_pitches"], "ER   <- fatigue"),
    ("ER", "proj_er", ["home"], "ER   <- home/away"),
    ("outs", "proj_outs", ["rest_days", "prev_pitches", "load3"], "Outs <- fatigue"),
    ("outs", "proj_outs", ["luck_era", "luck_babip"], "Outs <- regression/progression"),
    ("outs", "proj_outs", ["osi_all"], "Outs <- created metric OSI"),
    ("outs", "proj_outs", ["platoon_osi"], "Outs <- handedness platoon"),
    ("outs", "proj_outs", ["park_run"], "Outs <- ballpark"),
    ("outs", "proj_outs", ["home"], "Outs <- home/away"),
]


def main() -> None:
    frame, _ = add_features(load_starts())
    frame = frame[frame["p_starts"] >= 3].copy()
    frame["proj_k"] = frame["p_k"] * frame["bf"]
    frame["proj_er"] = frame["p_er_out"] * frame["outs"]
    frame["proj_outs"] = frame["p_outs_mean"]
    matched = frame["osi_all"].notna().mean() * 100
    print(
        f"starts usable: {len(frame)}   "
        f"{frame['date'].min().date()} -> {frame['date'].max().date()}   "
        f"opponent metric matched on {matched:.0f}% of starts"
    )
    print(f"fit on the earlier {TRAIN_FRAC:.0%} by date, scored on the later {1-TRAIN_FRAC:.0%}\n")
    print(f"{'factor':46s} {'n_oos':>6s} {'OOS R2 gain':>12s} {'corr':>7s}")
    print("-" * 76)
    for target, base, features, label in TESTS:
        result = oos_gain(frame, target, base, features)
        if result is None:
            print(f"{label:46s} {'--':>6s} {'insufficient':>12s}")
            continue
        n, gain, corr, _ = result
        flag = "  <-- REAL" if gain > 0.25 and abs(corr) > 0.05 else ""
        print(f"{label:46s} {n:6d} {gain:+11.2f}% {corr:+7.3f}{flag}")


if __name__ == "__main__":
    main()


# --------------------------------------------------------------- component breakdown
COMPONENT_TESTS = [
    ("K", "proj_k", ["so_all"], "K    <- opp K-avoidance (ABQ component)"),
    ("K", "proj_k", ["so_hand"], "K    <- opp K-avoidance vs THIS hand"),
    ("K", "proj_k", ["so_all", "platoon_so"], "K    <- opp K-avoid + platoon delta"),
    ("K", "proj_k", ["bb_all"], "K    <- opp walk discipline (ABQ component)"),
    ("K", "proj_k", ["h_all"], "K    <- opp contact/on-base (OBR component)"),
    ("K", "proj_k", ["r_all"], "K    <- opp run conversion (RCV component)"),
    ("K", "proj_k", ["so_all", "bb_all", "h_all", "r_all"], "K    <- ALL components, free weights"),
    ("K", "proj_k", ["so_hand", "home", "park_k"], "K    <- best-K stack"),
    ("BB", "proj_bb", ["bb_all"], "BB   <- opp walk discipline"),
    ("BB", "proj_bb", ["bb_hand"], "BB   <- opp walk discipline vs THIS hand"),
    ("BB", "proj_bb", ["so_all"], "BB   <- opp K-avoidance"),
    ("ER", "proj_er", ["so_all", "bb_all", "h_all", "r_all"], "ER   <- ALL components, free weights"),
    ("ER", "proj_er", ["r_all"], "ER   <- opp run conversion (RCV)"),
    ("ER", "proj_er", ["tb_all"], "ER   <- opp extra-base power"),
    ("ER", "proj_er", ["luck_babip"], "ER   <- BABIP luck alone"),
    ("ER", "proj_er", ["luck_era"], "ER   <- ERA-vs-skill gap alone"),
    ("outs", "proj_outs", ["luck_era"], "Outs <- ERA-vs-skill gap alone"),
    ("outs", "proj_outs", ["luck_babip"], "Outs <- BABIP luck alone"),
    ("outs", "proj_outs", ["rest_days"], "Outs <- rest days alone"),
    ("outs", "proj_outs", ["prev_pitches"], "Outs <- prior pitch count alone"),
    ("outs", "proj_outs", ["load3"], "Outs <- 3-start pitch load alone"),
    ("outs", "proj_outs", ["luck_era", "rest_days", "prev_pitches", "home"], "Outs <- best-Outs stack"),
]


def components() -> None:
    frame, _ = add_features(load_starts())
    frame = frame[frame["p_starts"] >= 3].copy()
    frame["proj_k"] = frame["p_k"] * frame["bf"]
    frame["proj_bb"] = frame["p_bb"] * frame["bf"]
    frame["proj_er"] = frame["p_er_out"] * frame["outs"]
    frame["proj_outs"] = frame["p_outs_mean"]
    print(f"\n{'component':46s} {'n_oos':>6s} {'OOS R2 gain':>12s} {'corr':>7s}  weights")
    print("-" * 100)
    for target, base, features, label in COMPONENT_TESTS:
        result = oos_gain(frame, target, base, features)
        if result is None:
            print(f"{label:46s} {'--':>6s} {'insufficient':>12s}")
            continue
        n, gain, corr, beta = result
        flag = "  <-- REAL" if gain > 0.25 and abs(corr) > 0.05 else ""
        weights = " ".join(f"{b:+.3f}" for b in beta)
        print(f"{label:46s} {n:6d} {gain:+11.2f}% {corr:+7.3f}  {weights}{flag}")
