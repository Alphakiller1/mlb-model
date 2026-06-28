"""Situational trend detectors.

Each detector takes the resolved :class:`SituationalContext` plus one team's
:class:`TeamSituation` and returns a :class:`Trend` (or ``None`` when the signal is absent
or too weak to be "dominant"). Detectors only read columns that exist in the materialized
MLBMA tables — verified against the live schema — and report honest sample sizes and
deviations. Magnitude/significance gating happens here; cross-trend ranking is the scorer's
job.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from mlbmodel.trends.context import SituationalContext, TeamSituation, _f
from mlbmodel.trends.types import RUN_BOOST, RUN_SUPPRESSION, Trend


def _zscore(value: float, series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 3:
        return 0.0
    sd = float(s.std(ddof=0))
    if sd <= 1e-9:
        return 0.0
    return float((value - float(s.mean())) / sd)


def _significance(abs_z: float, sample: int) -> str:
    if sample < 4:
        return "small-sample"
    if abs_z >= 1.5:
        return "strong"
    if abs_z >= 0.9:
        return "moderate"
    return "weak"


def _confidence(sample: int, data_backed: bool) -> str:
    if not data_backed:
        return "low"
    if sample >= 10:
        return "high"
    if sample >= 6:
        return "medium"
    return "low"


# ── detector 1: bullpen fatigue (reliever_log) ─────────────────────────────────
def detect_bullpen_fatigue(ctx: SituationalContext, sit: TeamSituation) -> Trend | None:
    log = ctx.reliever_log
    if log.empty or "pitcher_team" not in log.columns:
        return None
    log = log.copy()
    log["date"] = log["date"].astype(str)
    dates = sorted(d for d in log["date"].unique() if d and d <= (ctx.slate_date or "9999"))
    if len(dates) < 2:
        return None
    window = dates[-3:]
    recent = log[log["date"].isin(window)]
    agg = recent.groupby("pitcher_team").agg(
        pitches=("pitches", "sum"),
        apps=("pitcher_id", "count"),
        high_lev=("leverage_situation", lambda s: int((s.astype(str) == "High").sum())),
        inherited=("inherited_runners", "sum"),
        inherited_scored=("inherited_scored", "sum"),
    )
    if sit.team not in agg.index:
        return None
    row = agg.loc[sit.team]
    pitches = float(row["pitches"])
    z = _zscore(pitches, agg["pitches"])
    apps = int(row["apps"])
    high = int(row["high_lev"])
    inh = float(row["inherited"]) or 0.0
    inh_scored = float(row["inherited_scored"]) or 0.0
    # Only a heavy load is a "dominant" fatigue signal.
    if z < 0.6:
        return None
    inh_rate = round(100 * inh_scored / inh, 1) if inh > 0 else None
    days = len(window)
    desc = (
        f"{sit.team}'s bullpen has thrown {int(pitches)} pitches across {apps} relief "
        f"appearances over its last {days} games ({high} in high-leverage spots) — "
        f"{z:+.1f} SD above the league's recent reliever load."
    )
    diffs: dict[str, float] = {"recent_relief_pitches_z": round(z, 2), "high_lev_apps": float(high)}
    if inh_rate is not None:
        diffs["inherited_scored_pct"] = inh_rate
    return Trend(
        trend_id=f"{sit.team}_bullpen_fatigue",
        team=sit.team, side=sit.side, category="bullpen_fatigue",
        trend_description=desc,
        situation_key=f"{sit.team}|bullpen_fatigue|w{days}",
        direction=RUN_BOOST,                      # tired pen => opponent scores more late
        sample_size=apps,
        effect_size=round(abs(z), 3),
        z_score=round(z, 3),
        significance=_significance(abs(z), apps),
        confidence=_confidence(apps, True),
        key_rate_diffs=diffs,
        mechanistic_explanation=(
            "Heavy recent relief load thins the high-leverage corps and forces earlier, "
            "lower-quality middle relief; a patient opponent exploits the soft middle innings "
            "once the starter exits."
        ),
        betting_implications=[
            f"{sit.opp_team} team total OVER (late-inning leak risk)",
            f"{sit.team} run line — fade in close, bullpen-dependent games",
            "Live: target the opponent once the starter is pulled",
        ],
        suggested_model_feature={f"{sit.team}_bullpen_recent_load_z": round(z, 3)},
        data_backed=True,
        relevance=0.9,
    )


# ── detector 2: recent offense vs opposing starter hand (team_l10_sp_hand) ──────
def detect_form_vs_hand(ctx: SituationalContext, sit: TeamSituation) -> Trend | None:
    df = ctx.l10_sp_hand
    if df.empty or "wrc_plus" not in df.columns:
        return None
    hand = sit.opp_starter_hand
    sub = df.copy()
    sub["hand"] = sub["opp_starter_hand"].astype(str).str.upper().str[0]
    match = sub[(sub["team"] == sit.team) & (sub["hand"] == hand)]
    if match.empty:
        return None
    r = match.iloc[0]
    wrc = _f(r.get("wrc_plus"))
    if wrc is None:
        return None
    games = int(_f(r.get("games")) or 0)
    wins = int(_f(r.get("wins")) or 0)
    qs_pct = _f(r.get("qs_against_pct"))
    ops = _f(r.get("ops"))
    z = _zscore(wrc, sub[sub["hand"] == hand]["wrc_plus"])
    if abs(z) < 0.6:
        return None
    boosted = wrc >= float(pd.to_numeric(sub["wrc_plus"], errors="coerce").mean())
    direction = RUN_BOOST if boosted else RUN_SUPPRESSION
    verb = "mashing" if boosted else "struggling against"
    desc = (
        f"{sit.team} over its last {games} games vs {hand}HP is {verb} — {wrc:.0f} wRC+ "
        f"({z:+.1f} SD vs the league's split), {wins}-{games - wins} with opposing starters "
        f"earning a quality start {qs_pct:.0%}" if qs_pct is not None else
        f"{sit.team} last {games} vs {hand}HP: {wrc:.0f} wRC+ ({z:+.1f} SD), {wins}-{games - wins}"
    )
    diffs = {"wrc_plus_vs_hand": round(wrc, 1), "wrc_plus_z": round(z, 2)}
    if ops is not None:
        diffs["ops_vs_hand"] = round(ops, 3)
    if qs_pct is not None:
        diffs["opp_qs_against_pct"] = round(qs_pct * 100, 1)
    return Trend(
        trend_id=f"{sit.team}_form_vs_{hand}hp",
        team=sit.team, side=sit.side, category="form_vs_hand",
        trend_description=desc,
        situation_key=f"{sit.team}|form_vs_{hand}HP|l{games}",
        direction=direction,
        historical_record=f"{wins}-{games - wins}",
        sample_size=games,
        effect_size=round(abs(z), 3),
        z_score=round(z, 3),
        significance=_significance(abs(z), games),
        confidence=_confidence(games, True),
        key_rate_diffs=diffs,
        mechanistic_explanation=(
            "Recent split-specific production captures lineup platoon construction and hot/cold "
            "streaks that season-long marks wash out; it persists short-term via the same "
            "handedness matchup tonight."
        ),
        betting_implications=(
            [f"{sit.team} team total OVER", f"{sit.team} ML / run line value vs {hand}HP"]
            if boosted else
            [f"{sit.team} team total UNDER", f"Oppose {sit.team}; {hand}HP has shut them down"]
        ),
        suggested_model_feature={f"{sit.team}_l10_wrcplus_vs_{hand}hp_z": round(z, 3)},
        data_backed=True,
        relevance=0.95,
    )


# ── detector 3: starter-quality × offense interaction (sp_profiles × l10 form) ──
def detect_starter_quality_interaction(ctx: SituationalContext, sit: TeamSituation) -> Trend | None:
    sp = ctx.sp_profiles
    if sp.empty or "pitcher_name" not in sp.columns:
        return None
    opp = sp[sp["pitcher_name"].astype(str).str.strip() == sit.opp_starter.strip()]
    if opp.empty:
        return None
    p = opp.iloc[0]
    xfip = _f(p.get("xFIP")) or _f(p.get("FIP"))
    k_pct = _f(p.get("K_pct"))
    if xfip is None:
        return None
    # team recent form vs this hand (reuse l10)
    df = ctx.l10_sp_hand
    wrc = None
    if not df.empty and "wrc_plus" in df.columns:
        sub = df.copy()
        sub["hand"] = sub["opp_starter_hand"].astype(str).str.upper().str[0]
        m = sub[(sub["team"] == sit.team) & (sub["hand"] == sit.opp_starter_hand)]
        if not m.empty:
            wrc = _f(m.iloc[0].get("wrc_plus"))
    league_xfip = float(pd.to_numeric(sp["xFIP"], errors="coerce").mean()) if "xFIP" in sp.columns else 4.1
    weak_starter = xfip >= league_xfip + 0.25
    strong_starter = xfip <= league_xfip - 0.4
    if not (weak_starter or strong_starter):
        return None
    hot_offense = wrc is not None and wrc >= 105
    cold_offense = wrc is not None and wrc <= 95
    # Interaction only fires when the offense form aligns with the starter quality gap.
    if weak_starter and hot_offense:
        direction, mag = RUN_BOOST, min(2.2, (xfip - league_xfip) * 1.6 + (wrc - 100) / 25)
    elif strong_starter and cold_offense:
        direction, mag = RUN_SUPPRESSION, min(2.2, (league_xfip - xfip) * 1.6 + (100 - wrc) / 25)
    elif weak_starter and wrc is None:
        direction, mag = RUN_BOOST, min(1.4, (xfip - league_xfip) * 1.4)
    elif strong_starter and wrc is None:
        direction, mag = RUN_SUPPRESSION, min(1.4, (league_xfip - xfip) * 1.4)
    else:
        return None
    desc = (
        f"{sit.team} faces {sit.opp_starter} ({sit.opp_starter_hand}HP, {xfip:.2f} xFIP, "
        f"{('%.0f%% K' % (k_pct)) if k_pct is not None else 'n/a K'}) — a "
        f"{'below-average' if weak_starter else 'plus'} arm"
        + (f" against a lineup at {wrc:.0f} wRC+ vs the hand." if wrc is not None else ".")
    )
    return Trend(
        trend_id=f"{sit.team}_starter_quality_x_form",
        team=sit.team, side=sit.side, category="starter_quality",
        trend_description=desc,
        situation_key=f"{sit.team}|sp_quality_x_form|{sit.opp_starter_hand}HP",
        direction=direction,
        sample_size=int(_f(p.get("starts")) or 0),
        effect_size=round(abs(mag), 3),
        z_score=round(mag, 3),
        significance="moderate" if abs(mag) >= 0.9 else "weak",
        confidence="medium" if wrc is not None else "low",
        key_rate_diffs={
            "opp_starter_xfip": round(xfip, 2),
            "opp_starter_xfip_vs_lg": round(xfip - league_xfip, 2),
            **({"team_wrcplus_vs_hand": round(wrc, 1)} if wrc is not None else {}),
        },
        mechanistic_explanation=(
            "A below-average starter's contact-management gap, magnified when the opposing "
            "lineup is already producing against that hand, compounds into run expectancy the "
            "market under-prices on the starter's name alone."
            if direction == RUN_BOOST else
            "A plus starter's swing-and-miss and weak-contact profile suppresses a lineup that "
            "is already cold against the hand — a compounding under the starter's surface line "
            "may not fully reflect."
        ),
        betting_implications=(
            [f"{sit.team} team total OVER", f"{sit.opp_starter} hits/ER prop OVER"]
            if direction == RUN_BOOST else
            [f"{sit.team} team total UNDER", f"{sit.opp_starter} strikeouts prop OVER"]
        ),
        suggested_model_feature={
            f"{sit.team}_starter_quality_x_form": round(
                mag if direction == RUN_BOOST else -mag, 3
            )
        },
        data_backed=True,
        relevance=0.85 if wrc is not None else 0.6,
    )


# ── detector 4: park run environment (park_factor) ─────────────────────────────
def detect_park(ctx: SituationalContext, sit: TeamSituation) -> Trend | None:
    # Park is a game-level modifier; emit it once, on the home side.
    if sit.side != "home" or ctx.park_factor is None:
        return None
    pf = ctx.park_factor
    if 0.98 <= pf <= 1.02:
        return None
    boosted = pf > 1.0
    z = (pf - 1.0) / 0.06  # ~6% park swing ≈ 1 SD
    desc = (
        f"{ctx.stadium or 'The home park'} plays as a {'hitter' if boosted else 'pitcher'}'s "
        f"environment ({pf:.2f} run factor, {z:+.1f} SD) for both lineups."
    )
    return Trend(
        trend_id=f"{ctx.home}_park_run_env",
        team=ctx.home, side="home", category="park",
        trend_description=desc,
        situation_key=f"{ctx.home}|park|{pf:.2f}",
        direction=RUN_BOOST if boosted else RUN_SUPPRESSION,
        sample_size=0,
        effect_size=round(abs(z), 3),
        z_score=round(z, 3),
        significance="moderate" if abs(z) >= 0.9 else "weak",
        confidence="medium",
        key_rate_diffs={"park_run_factor": round(pf, 3)},
        mechanistic_explanation=(
            "Park run factor modulates extra-base outcomes and pitcher comfort identically for "
            "both clubs — a game-total signal, not a one-sided edge."
        ),
        betting_implications=[
            "Game total " + ("OVER" if boosted else "UNDER"),
            "Both team totals " + ("up" if boosted else "down"),
        ],
        suggested_model_feature={f"{ctx.home}_park_run_factor": round(pf, 3)},
        data_backed=True,
        relevance=0.5,
    )


# Registry — order is irrelevant; the scorer ranks the output.
DETECTORS: list[Callable[[SituationalContext, TeamSituation], Trend | None]] = [
    detect_bullpen_fatigue,
    detect_form_vs_hand,
    detect_starter_quality_interaction,
    detect_park,
]


def run_detectors(ctx: SituationalContext) -> list[Trend]:
    """Run every detector for both teams; return all non-empty trends (unscored)."""
    out: list[Trend] = []
    for sit in ctx.situations():
        for detector in DETECTORS:
            try:
                trend = detector(ctx, sit)
            except Exception:  # one bad detector must not sink the slate
                trend = None
            if trend is not None:
                out.append(trend)
    return out
