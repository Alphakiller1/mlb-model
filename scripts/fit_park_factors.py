"""Empirical-Bayes park factors: shrink each park by its OWN reliability, not one global prior.

A single global prior over-shrinks the genuine outliers. Coors measured 1.167 in 2026 and got
pulled to 1.04, which is why the model prices a Rockies home game ~2 runs under the market.
Estimating the between-park variance lets each park keep the share of its signal that its own
sample supports.
"""
from __future__ import annotations

import collections
import json
import math
import statistics
import urllib.request

import numpy as np

from mlbmodel import settings

U = settings.SUPABASE_URL.rstrip("/")
K = settings.supabase_read_key()


def fetch(path):
    rows, offset = [], 0
    while True:
        request = urllib.request.Request(
            f"{U}/rest/v1/{path}&offset={offset}&limit=1000",
            headers={"apikey": K, "Authorization": f"Bearer {K}"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            batch = json.loads(response.read().decode())
        rows += batch
        offset += len(batch)
        if len(batch) < 1000:
            break
    return rows


outcomes = {r["game_pk"]: float(r["total_runs"]) for r in
            fetch("game_outcomes?select=game_pk,total_runs&total_runs=not.is.null")}
meta = {g["game_pk"]: g for g in fetch("games?select=game_pk,game_date,home_team,away_team")}
games = sorted(
    ({"pk": pk, "total": t, **meta[pk]} for pk, t in outcomes.items() if pk in meta),
    key=lambda g: (str(g["game_date"]), g["pk"]),
)
print(f"games: {len(games)}")

cut = int(len(games) * 0.70)
train, test = games[:cut], games[cut:]


def raw_factors(rows):
    """Per-park home/road total ratio, with the sampling variance of the log ratio."""
    home = collections.defaultdict(list)
    road = collections.defaultdict(list)
    for game in rows:
        home[settings.team_abbr(game["home_team"])].append(game["total"])
        road[settings.team_abbr(game["away_team"])].append(game["total"])
    out = {}
    for team, values in home.items():
        away_values = road.get(team) or []
        if len(values) < 10 or len(away_values) < 10:
            continue
        home_mean, away_mean = statistics.mean(values), statistics.mean(away_values)
        if home_mean <= 0 or away_mean <= 0:
            continue
        log_ratio = math.log(home_mean / away_mean)
        # var(log mean) ~ var/(n*mean^2); the ratio's variance is the sum of both sides.
        var = (
            statistics.pvariance(values) / (len(values) * home_mean**2)
            + statistics.pvariance(away_values) / (len(away_values) * away_mean**2)
        )
        out[team] = (log_ratio, var, len(values))
    return out


def empirical_bayes(rows):
    """Shrink each park's log factor toward the league mean by its own reliability."""
    measured = raw_factors(rows)
    logs = np.array([v[0] for v in measured.values()])
    variances = np.array([v[1] for v in measured.values()])
    grand = float(logs.mean())
    # Between-park variance = total spread minus the average sampling noise (floored at 0).
    tau2 = max(0.0, float(logs.var(ddof=1) - variances.mean()))
    table = {}
    for team, (log_ratio, var, _n) in measured.items():
        weight = tau2 / (tau2 + var) if (tau2 + var) > 0 else 0.0
        table[team] = math.exp(grand + (log_ratio - grand) * weight)
    return table, tau2, grand


def rmse(table, rows, league):
    errors = [
        (league * table.get(settings.team_abbr(g["home_team"]), 1.0) - g["total"]) ** 2
        for g in rows
    ]
    return float(np.sqrt(np.mean(errors)))


league = statistics.mean(g["total"] for g in train)
flat = float(np.sqrt(np.mean([(league - g["total"]) ** 2 for g in test])))
eb_table, tau2, grand = empirical_bayes(train)
print(f"\nbetween-park variance tau^2 = {tau2:.5f}  (sd {math.sqrt(tau2)*100:.1f}% in log space)")
print(f"holdout RMSE   no park factor : {flat:.4f}")
print(f"holdout RMSE   settings table : {rmse(settings.PARK_FACTORS, test, league):.4f}")
print(f"holdout RMSE   empirical Bayes: {rmse(eb_table, test, league):.4f}")

final, tau2_full, _ = empirical_bayes(games)
print(f"\nfull-season tau^2 = {tau2_full:.5f}")
print(f"{'park':5} {'raw 2026':>9} {'EB shrunk':>10} {'current':>9}")
raw_all = raw_factors(games)
for team, value in sorted(final.items(), key=lambda kv: -kv[1]):
    raw = math.exp(raw_all[team][0])
    print(f"{team:5} {raw:9.3f} {value:10.3f} {settings.PARK_FACTORS.get(team, 1.0):9.2f}")

print("\nPARK_FACTORS = {")
items = sorted(final.items(), key=lambda kv: -kv[1])
for index in range(0, len(items), 5):
    chunk = items[index:index + 5]
    print("    " + " ".join(f'"{t}": {v:.3f},' for t, v in chunk))
print("}")
