"""The decisive test: does the rebuilt projection beat the market's own line?

Everything else measures the model against the league mean, which is a low bar. This scores it
against the number the book actually posted, on the same starts, and reports which is the
better point forecast. That is the only comparison that says whether a disagreement with the
market is an edge or an error.

Lines and realised values come from the settled `model_leans` ledger. Projections are rebuilt
point-in-time from `sp_game_log.csv` using the shipped matrix, so no start informs itself.

Run:  PYTHONPATH=. python scripts/model_vs_market.py
"""
from __future__ import annotations

import collections
import math
import statistics as st

import numpy as np

from mlbmodel.props import matrix as mx
from mlbmodel.props.model import _norm
from scripts.factor_study import add_features, load_starts
from scripts.fit_rate_shrinkage import build, engine_rate, shrunk_rate
from mlbmodel.storage.supabase import SupabaseReader

LEDGER_MARKETS = {"k": "K", "bb": "BB", "h": "H", "outs": "outs", "er": "ER"}


def ledger_rows() -> list[dict]:
    reader = SupabaseReader()
    result = reader.get_all(
        "model_leans?select=slate_date,market,line,realized_value,pitcher_name,source,void"
        "&sport=eq.mlb&source=eq.prop",
        page_size=1000,
        max_rows=60000,
    )
    if result.error:
        raise SystemExit(f"warehouse read failed: {result.error}")
    rows = {}
    for row in result.rows:
        if row.get("void") or row.get("realized_value") is None or row.get("line") is None:
            continue
        market = str(row.get("market") or "").lower()
        if market not in LEDGER_MARKETS:
            continue
        # one row per pitcher/date/market: the ledger repeats a line once per book
        key = (row["slate_date"], _norm(row.get("pitcher_name")), market)
        rows[key] = {
            "line": float(row["line"]),
            "actual": float(row["realized_value"]),
        }
    return rows


def projections() -> dict:
    """Point-in-time projection per (date, pitcher, market), old construction and new."""
    rates = build(load_starts())
    rates = rates[rates["starts_before"] >= 2].copy()
    feats, _ = add_features(load_starts())
    frame = rates.merge(
        feats[["date", "game_pk", "pitcher_id", "so_all", "luck_babip", "rest_days",
               "p_outs_mean", "p_fip"]],
        on=["date", "game_pk", "pitcher_id"], how="left",
    )
    league = {
        column: float(frame[column].sum() / frame["bf"].sum()) for column in ("K", "BB", "H")
    }
    out = {}
    bf = frame["bf"].to_numpy(dtype=float)
    built = {}
    for market, column in (("k", "K"), ("bb", "BB"), ("h", "H")):
        old = engine_rate(frame, column, league[column]) * bf
        new = shrunk_rate(frame, column, league[column], mx.RATE_SHRINK_BF[market]) * bf
        if market == "k":
            new = new + mx.OPPONENT_K_WEIGHT * (frame["so_all"].to_numpy() - 1.0)
        centre = float(np.nanmean(new))
        new = centre + (new - centre) * mx.SPREAD_CALIBRATION[market]
        built[market] = (old, new)
    old_o = frame["p_outs_mean"].to_numpy(dtype=float)
    new_o = (
        old_o
        + mx.BABIP_OUTS_WEIGHT * np.clip(frame["luck_babip"].to_numpy(), -0.06, 0.06)
        + mx.REST_OUTS_WEIGHT * (np.clip(frame["rest_days"].to_numpy(), 3, 10) - 5.0)
    )
    centre_o = float(np.nanmean(new_o))
    new_o = centre_o + (new_o - centre_o) * mx.SPREAD_CALIBRATION["outs"]
    built["outs"] = (old_o, new_o)

    dates = frame["date"].dt.strftime("%Y-%m-%d").to_numpy()
    names = frame["pitcher_name"].map(_norm).to_numpy()
    for market, (old, new) in built.items():
        for date, name, o, n in zip(dates, names, old, new, strict=True):
            out[(date, name, market)] = (float(o), float(n))
    return out


def main() -> None:
    ledger = ledger_rows()
    proj = projections()
    joined = collections.defaultdict(list)
    for key, row in ledger.items():
        if key not in proj:
            continue
        old, new = proj[key]
        if not (math.isfinite(old) and math.isfinite(new)):
            continue
        joined[key[2]].append((row["line"], old, new, row["actual"]))

    print("POINT-FORECAST CONTEST vs the book's own line, on the same starts")
    print(f"{'market':7s} {'n':>4s} | {'MAE line':>9s} {'MAE orig':>9s} {'MAE new':>9s}"
          f" | {'RMSE line':>10s} {'RMSE new':>9s} | {'winner':>8s}")
    print("-" * 84)
    for market in ("k", "bb", "h", "outs"):
        rows = joined.get(market) or []
        if len(rows) < 20:
            print(f"{market:7s} {len(rows):>4d} | insufficient overlap")
            continue
        mae_l = st.mean(abs(line - a) for line, _o, _n, a in rows)
        mae_o = st.mean(abs(o - a) for _l, o, _n, a in rows)
        mae_n = st.mean(abs(n - a) for _l, _o, n, a in rows)
        rmse_l = math.sqrt(st.mean((line - a) ** 2 for line, _o, _n, a in rows))
        rmse_n = math.sqrt(st.mean((n - a) ** 2 for _l, _o, n, a in rows))
        winner = "MARKET" if mae_l < mae_n else "model"
        print(f"{market:7s} {len(rows):>4d} | {mae_l:9.3f} {mae_o:9.3f} {mae_n:9.3f}"
              f" | {rmse_l:10.3f} {rmse_n:9.3f} | {winner:>8s}")

    print("\nHOW FAR THE PROJECTION SITS FROM THE LINE (|projection - line|)")
    print(f"{'market':7s} {'n':>4s} {'original':>10s} {'new':>8s} {'change':>9s}")
    for market in ("k", "bb", "h", "outs"):
        rows = joined.get(market) or []
        if len(rows) < 20:
            continue
        go = st.mean(abs(o - line) for line, o, _n, _a in rows)
        gn = st.mean(abs(n - line) for line, _o, n, _a in rows)
        print(f"{market:7s} {len(rows):>4d} {go:10.3f} {gn:8.3f} {gn-go:+9.3f}")


if __name__ == "__main__":
    main()
