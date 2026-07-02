"""
Promotion gate (Constitution STD-7, STD-10, STD-12) — the single, enforceable check that
decides whether ANY market-movement segment may be promoted from research to production.

A candidate is PROMOTABLE only if ALL hold:
  1. Point-in-time walk-forward OOS lower bound (net of execution cost) clears the hurdle.
  2. The selected segment survives Deflated-Sharpe selection-bias correction (DSR >= threshold).
  3. The OOS sample meets the minimum size.

Otherwise the verdict is HOLD/ABSTAIN with explicit reasons. This is what `refresh.sh` runs
daily so the pipeline self-enforces the constitution instead of relying on a label
(`market_edge`'s "TRADEABLE" is necessary but NOT sufficient — DSR + OOS are required).
"""
from __future__ import annotations

from mlbmodel.backtest.walkforward import (
    executable_rows,
    net_roi,
    steam_rule,
    time_ordered_split,
    walk_forward,
)
from mlbmodel.quant.selection import (
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe,
)

# canonical movement segments (mirrors market_edge; self-contained so the gate has no
# dependency on the sharp-money-tracker repo).
_SEGMENTS = {
    "steam>=0.02": steam_rule(0.02),
    "steam>=0.04": steam_rule(0.04),
    "steam>=0.06": steam_rule(0.06),
    "up+liquid>=120k": lambda r: steam_rule(0.02)(r) and (r.get("volume") or 0) >= 120000,
    "fade(down<=-0.02)": lambda r: (r.get("signal_delta") or 0) <= -0.02,
    "dog+steam": lambda r: (r.get("entry_prob") or 1) < 0.45 and steam_rule(0.02)(r),
}


def promotion_verdict(rows: list[dict], *, hurdle: float = 0.0, dsr_threshold: float = 0.95,
                      pbo_threshold: float = 0.25, min_oos_n: int = 50,
                      train_frac: float = 0.7) -> dict:
    """Return the gated promotion decision with reasons."""
    wf = walk_forward(rows, train_frac)
    if "error" in wf:
        return {"verdict": "HOLD/ABSTAIN", "reasons": [wf["error"]]}
    oos = wf["out_of_sample"]

    tradable = executable_rows(rows)
    train, _ = time_ordered_split(tradable, train_frac)

    # Selection controls use training data only. The OOS period remains untouched.
    seg_returns = {
        name: [net_roi(r["entry_prob"], r["won"]) for r in train if pred(r)]
        for name, pred in _SEGMENTS.items()
    }
    usable = {name: values for name, values in seg_returns.items() if len(values) >= 2}
    fitted_name = f"steam>={wf['fitted_threshold']:.2f}"
    if fitted_name not in usable or len(usable) < 2:
        dsr = {
            "ok": False,
            "selected": fitted_name,
            "dsr": None,
            "reason": "candidate or comparison strategies are under-powered",
        }
    else:
        sharpes = {name: sharpe(values) for name, values in usable.items()}
        mean_sharpe = sum(sharpes.values()) / len(sharpes)
        variance = sum(
            (value - mean_sharpe) ** 2 for value in sharpes.values()
        ) / (len(sharpes) - 1)
        ratio = deflated_sharpe_ratio(
            usable[fitted_name],
            n_trials=len(usable),
            var_sr_across_trials=variance,
        )
        dsr = {
            "ok": ratio >= dsr_threshold,
            "selected": fitted_name,
            "dsr": round(ratio, 4),
            "n_trials": len(usable),
            "threshold": dsr_threshold,
            "observed_sharpe": round(sharpes[fitted_name], 4),
        }
    matrix = [
        [
            net_roi(row["entry_prob"], row["won"]) if predicate(row) else 0.0
            for predicate in _SEGMENTS.values()
        ]
        for row in train
    ]
    pbo = probability_of_backtest_overfitting(matrix, n_splits=8)

    reasons = []
    ok_oos_lb = oos.get("roi_lb", -1) > hurdle
    ok_n = oos.get("n", 0) >= min_oos_n
    ok_dsr = bool(dsr.get("ok"))
    ok_pbo = pbo == pbo and pbo <= pbo_threshold
    if not ok_oos_lb:
        reasons.append(f"OOS ROI 95% LB {oos.get('roi_lb')} <= hurdle {hurdle}")
    if not ok_n:
        reasons.append(f"OOS n {oos.get('n')} < min {min_oos_n} (under-powered)")
    if not ok_dsr:
        reasons.append(f"DSR {dsr.get('dsr')} < {dsr_threshold} (selection bias not cleared)")
    if not ok_pbo:
        reasons.append(
            f"PBO {pbo:.3f} > {pbo_threshold:.2f} or unavailable"
            if pbo == pbo else "PBO unavailable"
        )

    promote = ok_oos_lb and ok_n and ok_dsr and ok_pbo
    return {
        "verdict": "PROMOTE" if promote else "HOLD/ABSTAIN",
        "fitted_threshold": wf.get("fitted_threshold"),
        "oos": oos,
        "dsr": dsr,
        "pbo": round(pbo, 4) if pbo == pbo else None,
        "reasons": reasons or ["all gates passed"],
    }


def main():  # pragma: no cover
    import argparse
    import json
    from mlbmodel.backtest.walkforward import load_settled_ml_from_env
    p = argparse.ArgumentParser(description="Constitution promotion gate for movement segments.")
    p.add_argument("--env", required=True)
    p.add_argument("--hurdle", type=float, default=0.0)
    args = p.parse_args()
    rows = load_settled_ml_from_env(args.env)
    v = promotion_verdict(rows, hurdle=args.hurdle)
    print(f"PROMOTION GATE: {v['verdict']}  (settled n={len(rows)})")
    print(json.dumps(
        {k: v[k] for k in ("fitted_threshold", "oos", "dsr", "pbo", "reasons")},
        indent=2,
    ))


if __name__ == "__main__":
    main()
