# MLB MODEL

Unified MLB betting-**intelligence** research platform. Decision-support + paper-trading only —
**not** auto-betting. Governed by a version-controlled **Model Constitution**; advancements must pass
scientific validation, point-in-time testing, uncertainty measurement, and monitoring before they get
production authority.

> This repo is **not a greenfield rebuild.** The verified production logic lives in `bet-evaluator`
> and `sharp-money-tracker`; it is preserved and folded in module-by-module per the governance docs.
> This package is the governed home for new, **tested** modules and the data glue.

## Governance (read first)
The charter and standards live in `governance/`:
- `MODEL-CONSTITUTION.md` — 18 enforceable standards + how each is enforced (test/gate/schema/registry/human)
- `CURRENT-STATE-AUDIT.md` — evidence-based audit (implemented/verified vs documented/absent)
- `ADVANCEMENT-FRAMEWORK.md` — traceability, extensibility, research lifecycle, MLBMA governance, promotion gates
- `ROADMAP-AND-RISK.md` — classified recommendations, migration/rollback, risk register, open questions

## Package
```
mlbmodel/
  market/oddsmath.py     # canonical odds math (STD-11) — consolidates duplicated copies
  quant/selection.py     # Deflated Sharpe Ratio + PBO selection-bias controls (STD-7)
  sources/               # data glue: hub_to_csv, build_today_matchups, build_game_results, seed_warehouse
tests/                   # Constitution invariants as automated tests (STD-7, STD-11)
```

## Dev
```
pip install -e ".[dev]"
pytest -q          # enforces the invariants
ruff check mlbmodel
```

## Daily pipeline
`refresh.sh` (repo root) runs the verified end-to-end chain (features → slate → finals →
seed → sharp tracker → settle) against the unified Supabase warehouse.
