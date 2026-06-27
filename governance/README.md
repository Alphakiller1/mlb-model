# Governance — MLB MODEL

The enforceable charter for the platform. Read in this order:

1. **[MODEL-CONSTITUTION.md](MODEL-CONSTITUTION.md)** — 18 versioned standards, each mapped to an
   enforcement mechanism (test / gate / schema / registry / human). The supreme document.
2. **[CURRENT-STATE-AUDIT.md](CURRENT-STATE-AUDIT.md)** — evidence-based maturity audit (what is
   implemented & verified vs documented but absent), strengths to preserve, gaps, unsupported claims.
3. **[VERIFICATION-AUDIT.md](VERIFICATION-AUDIT.md)** — forensic integration verification with
   lineage matrices (Betting Brain / MLBMA / Sharp Money Tracker / Bet Evaluator), the real
   point-in-time OOS + ablation results, and acceptance criteria for "integration complete".
4. **[ADVANCEMENT-FRAMEWORK.md](ADVANCEMENT-FRAMEWORK.md)** — traceability, extensibility boundaries,
   research/model lifecycle, MLBMA governance, per-market promotion gates.
5. **[ROADMAP-AND-RISK.md](ROADMAP-AND-RISK.md)** — classified recommendations
   (Required/Recommended/Experimental/Rejected), migration & rollback, risk register, open questions.

## What is enforced in code today
- `mlbmodel/market/oddsmath.py` + `tests/test_oddsmath.py` — STD-11 invariants.
- `mlbmodel/quant/selection.py` + `tests/test_selection.py` — STD-7 Deflated-Sharpe / PBO.
- `mlbmodel/backtest/walkforward.py` + `tests/test_walkforward.py` — STD-10 point-in-time / no-leakage.
- `mlbmodel/quant/promotion_gate.py` + `tests/test_promotion_gate.py` — STD-7/10/12 promotion gate,
  run daily as the final step of `refresh.sh`.

**Default outcome is ABSTAIN.** Nothing is promoted without OOS lower bound > hurdle **and** DSR
clearance **and** sufficient sample. As of the last audit, no segment meets the bar — by design.
