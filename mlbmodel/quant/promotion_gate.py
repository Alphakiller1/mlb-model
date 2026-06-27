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

from mlbmodel.backtest.walkforward import net_roi, steam_rule, walk_forward
from mlbmodel.quant.selection import dsr_gate

# canonical movement segments (mirrors market_edge; self-contained so the gate has no
# dependency on the sharp-money-tracker repo).
_SEGMENTS = {
    "steam>=0.02": steam_rule(0.02),
    "steam>=0.04": steam_rule(0.04),
    "steam>=0.06": steam_rule(0.06),
    "up+liquid>=120k": lambda r: steam_rule(0.02)(r) and (r.get("volume") or 0) >= 120000,
    "fade(down<=-0.02)": lambda r: (r.get("delta") or 0) <= -0.02,
    "dog+steam": lambda r: (r.get("open_prob") or 1) < 0.45 and steam_rule(0.02)(r),
}


def promotion_verdict(rows: list[dict], *, hurdle: float = 0.0, dsr_threshold: float = 0.95,
                      min_oos_n: int = 50, train_frac: float = 0.7) -> dict:
    """Return the gated promotion decision with reasons."""
    wf = walk_forward(rows, train_frac)
    if "error" in wf:
        return {"verdict": "ABSTAIN", "reasons": [wf["error"]]}
    oos = wf["out_of_sample"]

    # DSR over the full-sample segment scan (selection-bias correction across segments tried),
    # using execution-cost-net per-bet ROI as the return series.
    seg_returns = {
        name: [net_roi(r["open_prob"], r["won"]) for r in rows if pred(r)]
        for name, pred in _SEGMENTS.items()
    }
    dsr = dsr_gate(seg_returns, threshold=dsr_threshold)

    reasons = []
    ok_oos_lb = oos.get("roi_lb", -1) > hurdle
    ok_n = oos.get("n", 0) >= min_oos_n
    ok_dsr = bool(dsr.get("ok"))
    if not ok_oos_lb:
        reasons.append(f"OOS ROI 95% LB {oos.get('roi_lb')} <= hurdle {hurdle}")
    if not ok_n:
        reasons.append(f"OOS n {oos.get('n')} < min {min_oos_n} (under-powered)")
    if not ok_dsr:
        reasons.append(f"DSR {dsr.get('dsr')} < {dsr_threshold} (selection bias not cleared)")

    promote = ok_oos_lb and ok_n and ok_dsr
    return {
        "verdict": "PROMOTE" if promote else "HOLD/ABSTAIN",
        "fitted_threshold": wf.get("fitted_threshold"),
        "oos": oos, "dsr": dsr, "reasons": reasons or ["all gates passed"],
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
    print(json.dumps({k: v[k] for k in ("fitted_threshold", "oos", "dsr", "reasons")}, indent=2))


if __name__ == "__main__":
    main()
