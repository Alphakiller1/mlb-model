"""Does the pitch-mix matchup term predict anything, and is it internally consistent?

Two questions, because they have different answers:

1. **Predictive value.** The term is scored against realised strikeouts using the CURRENT
   season-aggregate pitch-mix tables. That is hindsight-contaminated on purpose: the season
   totals already know how each start turned out. A factor that cannot predict *with*
   hindsight is broken outright, not merely weak.

2. **Internal consistency.** The engine compares three different tables against one baseline
   built from only one of them, so the same matchup scores differently depending on whether a
   lineup has been posted yet.

Run:  PYTHONPATH=. python scripts/pitch_mix_audit.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mlbmodel.props.model import SKIP_PITCH_TYPES, _norm, _pitch_type

DATA = "data/"


def load():
    pitcher = pd.read_csv(DATA + "pitch_mix_pitcher.csv")
    team = pd.read_csv(DATA + "pitch_mix_team_batting.csv")
    batter = pd.read_csv(DATA + "pitch_mix_batter.csv")
    for frame in (pitcher, team, batter):
        frame["pt"] = frame["pitch_type"].map(_pitch_type)
        for column in ("whiff_rate", "xwoba", "chase_rate", "pitch_pct", "pitches"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return pitcher, team, batter


def baselines(team: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Exactly what the engine builds: PA-weighted league means from TEAM batting only."""
    out = {}
    for pitch, group in team[~team["pt"].isin(SKIP_PITCH_TYPES)].groupby("pt"):
        weights = group["pitches"].clip(lower=1.0)
        out[pitch] = {
            column: float(np.average(group[column], weights=weights))
            for column in ("xwoba", "whiff_rate", "chase_rate")
        }
    return out


def score_matchup(pitcher_rows, opponent_by_pitch, base) -> tuple[float, float]:
    """Replicates PitcherProjectionEngine._pitch_matchup. Returns (raw_total, coverage)."""
    total = 0.0
    coverage = 0.0
    for row in pitcher_rows.itertuples():
        pitch = row.pt
        usage = row.pitch_pct or 0.0
        opponent = opponent_by_pitch.get(pitch)
        reference = base.get(pitch)
        if pitch in SKIP_PITCH_TYPES or usage < 3 or opponent is None or not reference:
            continue
        weight = usage / 100
        coverage += weight
        whiff_edge = (
            (row.whiff_rate - reference["whiff_rate"])
            + (opponent["whiff_rate"] - reference["whiff_rate"])
        ) / 100
        contact_edge = (
            (reference["xwoba"] - row.xwoba) + (reference["xwoba"] - opponent["xwoba"])
        )
        chase_edge = (
            (row.chase_rate - reference["chase_rate"])
            + (opponent["chase_rate"] - reference["chase_rate"])
        ) / 100
        total += weight * (0.42 * whiff_edge + 0.43 * contact_edge + 0.15 * chase_edge)
    return total, coverage


def main() -> None:
    pitcher, team, batter = load()
    base = baselines(team)

    # ---------- 2. internal consistency: three tables, one baseline ----------
    print("SCALE OF EACH TABLE AGAINST THE SINGLE SHARED BASELINE")
    print("(the baseline is built from TEAM batting only, so team offsets are 0 by construction)")
    print(f"{'table':22s} {'whiff offset':>13s} {'xwoba offset':>13s} {'chase offset':>13s}")
    for label, frame in (
        ("pitcher mix", pitcher),
        ("team batting mix", team),
        ("individual batter mix", batter),
    ):
        offsets = []
        for column in ("whiff_rate", "xwoba", "chase_rate"):
            deltas = [
                getattr(row, column) - base[row.pt][column]
                for row in frame.itertuples()
                if row.pt in base and pd.notna(getattr(row, column))
            ]
            offsets.append(float(np.mean(deltas)))
        print(f"{label:22s} {offsets[0]:+13.3f} {offsets[1]:+13.4f} {offsets[2]:+13.3f}")

    # ---------- 1. predictive value, WITH hindsight ----------
    logs = pd.read_csv(DATA + "sp_game_log.csv")
    logs["K"] = pd.to_numeric(logs["K"], errors="coerce")
    logs["bf"] = pd.to_numeric(logs["batters_faced"], errors="coerce")
    logs = logs[(logs["bf"] > 0) & logs["K"].notna()].copy()
    logs["k_rate"] = logs["K"] / logs["bf"]
    logs["key"] = logs["pitcher_name"].map(_norm)

    pitcher["key"] = pitcher["full_name"].map(_norm)
    by_pitcher = {key: group for key, group in pitcher.groupby("key")}
    team_by_club: dict[str, dict] = {}
    for club, group in team.groupby("team_abbr"):
        team_by_club[str(club).upper()] = {
            row.pt: {"whiff_rate": row.whiff_rate, "xwoba": row.xwoba,
                     "chase_rate": row.chase_rate}
            for row in group.itertuples()
        }

    scores, raw_scores, k_rates, ks, covs = [], [], [], [], []
    for row in logs.itertuples():
        rows = by_pitcher.get(row.key)
        opponent = team_by_club.get(str(row.opponent_team).upper())
        if rows is None or opponent is None:
            continue
        total, coverage = score_matchup(rows, opponent, base)
        if coverage < 0.35:
            continue
        raw_scores.append(total)
        scores.append(total / coverage)          # coverage-normalised
        covs.append(coverage)
        k_rates.append(row.k_rate)
        ks.append(row.K)

    n = len(scores)
    raw_scores = np.array(raw_scores)
    scores = np.array(scores)
    k_rates = np.array(k_rates)
    ks = np.array(ks)
    covs = np.array(covs)
    print(f"\nPREDICTIVE VALUE against realised strikeouts (n={n} starts, WITH hindsight)")
    print(f"{'variant':34s} {'corr vs K rate':>15s} {'corr vs K':>11s}")
    print(f"{'raw total (what ships)':34s} {np.corrcoef(raw_scores, k_rates)[0,1]:+15.4f}"
          f" {np.corrcoef(raw_scores, ks)[0,1]:+11.4f}")
    print(f"{'coverage-normalised':34s} {np.corrcoef(scores, k_rates)[0,1]:+15.4f}"
          f" {np.corrcoef(scores, ks)[0,1]:+11.4f}")

    print("\nCOVERAGE CONTAMINATION (the raw total is a weighted SUM, not an average)")
    print(f"  corr(coverage, raw total)          {np.corrcoef(covs, raw_scores)[0,1]:+.4f}")
    print(f"  corr(coverage, normalised total)   {np.corrcoef(covs, scores)[0,1]:+.4f}")
    print(f"  coverage range {covs.min():.2f} - {covs.max():.2f}, sd {covs.std():.3f}")

    shipped = np.clip(raw_scores * 16, -2.5, 2.5)
    print("\nSHIPPED k_rate_delta = clip(total*16, -2.5, 2.5)")
    print(f"  range {shipped.min():+.2f} to {shipped.max():+.2f}  sd {shipped.std():.3f}")
    print(f"  share pinned at a clip bound: {np.mean(np.abs(np.abs(shipped)-2.5) < 1e-9)*100:.1f}%")
    print(f"  corr(shipped delta, realised K rate) {np.corrcoef(shipped, k_rates)[0,1]:+.4f}")




# --------------------------------------------------------------------- decomposition
def decompose() -> None:
    """Split the score into its pitcher half and its opponent half.

    The engine adds `k_rate_delta` on top of the pitcher's own season K rate. If the score is
    mostly a restatement of that same skill, the engine is counting the pitcher twice and
    inflating the spread of every projection -- which is what an over-dispersed board looks
    like from the inside.
    """
    pitcher, team, batter = load()
    base = baselines(team)
    logs = pd.read_csv(DATA + "sp_game_log.csv")
    logs["K"] = pd.to_numeric(logs["K"], errors="coerce")
    logs["bf"] = pd.to_numeric(logs["batters_faced"], errors="coerce")
    logs = logs[(logs["bf"] > 0) & logs["K"].notna()].copy()
    logs["k_rate"] = logs["K"] / logs["bf"]
    logs["key"] = logs["pitcher_name"].map(_norm)
    # The pitcher's own season K rate -- what the engine already has before adding the term.
    own = logs.groupby("key").agg(own_k=("K", "sum"), own_bf=("bf", "sum"))
    own["own_rate"] = own["own_k"] / own["own_bf"]

    pitcher["key"] = pitcher["full_name"].map(_norm)
    by_pitcher = {k: g for k, g in pitcher.groupby("key")}
    team_by_club = {}
    for club, group in team.groupby("team_abbr"):
        team_by_club[str(club).upper()] = {
            r.pt: {"whiff_rate": r.whiff_rate, "xwoba": r.xwoba, "chase_rate": r.chase_rate}
            for r in group.itertuples()
        }

    p_half, o_half, tot, actual, own_rate = [], [], [], [], []
    for row in logs.itertuples():
        rows = by_pitcher.get(row.key)
        opponent = team_by_club.get(str(row.opponent_team).upper())
        if rows is None or opponent is None or row.key not in own.index:
            continue
        pitcher_part = opponent_part = 0.0
        coverage = 0.0
        for r in rows.itertuples():
            ref = base.get(r.pt)
            opp = opponent.get(r.pt)
            if r.pt in SKIP_PITCH_TYPES or (r.pitch_pct or 0) < 3 or opp is None or not ref:
                continue
            w = r.pitch_pct / 100
            coverage += w
            pitcher_part += w * (
                0.42 * (r.whiff_rate - ref["whiff_rate"]) / 100
                + 0.43 * (ref["xwoba"] - r.xwoba)
                + 0.15 * (r.chase_rate - ref["chase_rate"]) / 100
            )
            opponent_part += w * (
                0.42 * (opp["whiff_rate"] - ref["whiff_rate"]) / 100
                + 0.43 * (ref["xwoba"] - opp["xwoba"])
                + 0.15 * (opp["chase_rate"] - ref["chase_rate"]) / 100
            )
        if coverage < 0.35:
            continue
        p_half.append(pitcher_part)
        o_half.append(opponent_part)
        tot.append(pitcher_part + opponent_part)
        actual.append(row.k_rate)
        own_rate.append(own.loc[row.key, "own_rate"])

    p_half = np.array(p_half)
    o_half = np.array(o_half)
    tot = np.array(tot)
    actual = np.array(actual)
    own_rate = np.array(own_rate)
    print(f"\n\nDECOMPOSITION: pitcher half vs opponent half (n={len(tot)})")
    print(f"{'component':26s} {'sd':>8s} {'share of total sd':>18s} {'corr vs realised K rate':>25s}")
    for label, part in (("pitcher's own stuff", p_half), ("opponent lineup", o_half),
                        ("total (shipped)", tot)):
        print(f"{label:26s} {part.std():8.5f} {part.std()/tot.std()*100:17.0f}%"
              f" {np.corrcoef(part, actual)[0,1]:+25.4f}")

    print(f"\ncorr(pitcher half, his own season K rate) = "
          f"{np.corrcoef(p_half, own_rate)[0,1]:+.4f}   <- the double-count")
    # Partial correlation of each half with the outcome, controlling for own season K rate.
    def partial(x, y, z):
        rx = x - np.polyval(np.polyfit(z, x, 1), z)
        ry = y - np.polyval(np.polyfit(z, y, 1), z)
        return float(np.corrcoef(rx, ry)[0, 1])
    print("\nControlling for the pitcher's own season K rate (what the engine already has):")
    print(f"  partial corr, pitcher half -> realised K rate  {partial(p_half, actual, own_rate):+.4f}")
    print(f"  partial corr, opponent half -> realised K rate {partial(o_half, actual, own_rate):+.4f}")
    print(f"  partial corr, TOTAL -> realised K rate         {partial(tot, actual, own_rate):+.4f}")




def er_and_overlap() -> None:
    """Does the term predict ER at all, and does its opponent half duplicate matrix.opponent_k?"""
    from mlbmodel.props import matrix as mx
    pitcher, team, _batter = load()
    base = baselines(team)
    logs = pd.read_csv(DATA + "sp_game_log.csv")
    for c in ("K", "ER", "batters_faced"):
        logs[c] = pd.to_numeric(logs[c], errors="coerce")
    logs = logs[(logs["batters_faced"] > 0) & logs["K"].notna() & logs["ER"].notna()].copy()
    logs["outs"] = logs["IP"].map(
        lambda v: (lambda w, p: w * 3 + (p if p in (1, 2) else 0))(
            int(float(v)), round((float(v) - int(float(v))) * 10)
        ) if pd.notna(v) else np.nan
    )
    logs = logs[logs["outs"] > 0].copy()
    logs["k_rate"] = logs["K"] / logs["batters_faced"]
    logs["er_rate"] = logs["ER"] / logs["outs"]
    logs["key"] = logs["pitcher_name"].map(_norm)
    own = logs.groupby("key").agg(k=("K", "sum"), bf=("batters_faced", "sum"),
                                  er=("ER", "sum"), o=("outs", "sum"))
    own["own_k"] = own["k"] / own["bf"]
    own["own_er"] = own["er"] / own["o"]

    rates, league = mx.opponent_strikeout_rates(logs.to_dict("records"))
    pitcher["key"] = pitcher["full_name"].map(_norm)
    by_pitcher = {k: g for k, g in pitcher.groupby("key")}
    team_by_club = {}
    for club, group in team.groupby("team_abbr"):
        team_by_club[str(club).upper()] = {
            r.pt: {"whiff_rate": r.whiff_rate, "xwoba": r.xwoba, "chase_rate": r.chase_rate}
            for r in group.itertuples()
        }

    opp_half, tot, kr, err, ok, oe, mk = [], [], [], [], [], [], []
    for row in logs.itertuples():
        rows = by_pitcher.get(row.key)
        opponent = team_by_club.get(str(row.opponent_team).upper())
        if rows is None or opponent is None or row.key not in own.index:
            continue
        p_part = o_part = cov = 0.0
        for r in rows.itertuples():
            ref = base.get(r.pt)
            opp = opponent.get(r.pt)
            if r.pt in SKIP_PITCH_TYPES or (r.pitch_pct or 0) < 3 or opp is None or not ref:
                continue
            w = r.pitch_pct / 100
            cov += w
            p_part += w * (0.42 * (r.whiff_rate - ref["whiff_rate"]) / 100
                           + 0.43 * (ref["xwoba"] - r.xwoba)
                           + 0.15 * (r.chase_rate - ref["chase_rate"]) / 100)
            o_part += w * (0.42 * (opp["whiff_rate"] - ref["whiff_rate"]) / 100
                           + 0.43 * (ref["xwoba"] - opp["xwoba"])
                           + 0.15 * (opp["chase_rate"] - ref["chase_rate"]) / 100)
        if cov < 0.35:
            continue
        delta, _idx = mx.opponent_k_delta(row.opponent_team, rates, league)
        opp_half.append(o_part)
        tot.append(p_part + o_part)
        kr.append(row.k_rate)
        err.append(row.er_rate)
        ok.append(own.loc[row.key, "own_k"])
        oe.append(own.loc[row.key, "own_er"])
        mk.append(delta)
    opp_half = np.array(opp_half)
    tot = np.array(tot)
    kr = np.array(kr)
    err = np.array(err)
    ok = np.array(ok)
    oe = np.array(oe)
    mk = np.array(mk)

    def partial(x, y, z):
        rx = x - np.polyval(np.polyfit(z, x, 1), z)
        ry = y - np.polyval(np.polyfit(z, y, 1), z)
        return float(np.corrcoef(rx, ry)[0, 1])

    print(f"\n\nER CHANNEL  (er_factor = 1 - total*1.8), n={len(tot)}")
    print(f"  corr(total, ER per out)                      {np.corrcoef(tot, err)[0,1]:+.4f}")
    print(f"  partial vs own season ER rate, TOTAL         {partial(tot, err, oe):+.4f}")
    print(f"  partial vs own season ER rate, OPPONENT half {partial(opp_half, err, oe):+.4f}")

    print("\nOVERLAP with the fitted matrix opponent-K term")
    print(f"  corr(pitch-mix OPPONENT half, matrix opp-K delta) {np.corrcoef(opp_half, mk)[0,1]:+.4f}")
    print(f"  corr(pitch-mix TOTAL,          matrix opp-K delta) {np.corrcoef(tot, mk)[0,1]:+.4f}")
    both = np.column_stack([np.ones(len(mk)), mk, opp_half])
    beta, *_ = np.linalg.lstsq(both, kr - ok, rcond=None)
    print(f"  joint fit on (K rate - own rate): matrix {beta[1]:+.4f}, pitch-mix opp {beta[2]:+.4f}")
    print(f"\n  scale check: opponent half sd {opp_half.std():.5f}"
          f" -> shipped k_rate_delta sd would be {opp_half.std()*16:.3f} pts at the current x16")


if __name__ == "__main__":
    main()
    decompose()
    er_and_overlap()
