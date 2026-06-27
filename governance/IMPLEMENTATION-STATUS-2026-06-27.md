# Implementation Status — 2026-06-27

This is the controlling current-state record. Older audit documents remain as historical
evidence and are explicitly marked where their conclusions were invalidated.

## What Is Implemented

| Capability | Status | Evidence |
|---|---|---|
| Unified expected-runs runtime | Implemented | `mlbmodel/baseball/` |
| Exact model-factor lineage | Implemented | probability output owns its factor contributions |
| Overdispersed run simulation | Implemented as challenger | 25,000 deterministic draws; no betting authority |
| MLBMA context metrics | Implemented as context | ABQ, RCV, PALS, projOSI, recent OSI, OBR, wOBA, platoon |
| Paired book-level de-vig | Implemented and tested | `market/quotes.py`, `test_quotes.py` |
| Value state controlled by promotion | Implemented and tested | `market/value.py`, `test_value.py` |
| Sharp-versus-soft collection | Implemented | `market/collect.py` |
| Sharp observation settlement | Implemented | `market/settle.py` |
| Executable-entry validation | Implemented and tested | `backtest/walkforward.py` |
| DSR/PBO/OOS promotion gate | Implemented | `quant/promotion_gate.py` |
| Collision-safe doubleheaders | Implemented for new slates/results | game number is included after game 1 |
| Unified interactive report | Implemented | all slate games, tabs, matchup selection |
| Pitcher-prop research board | Implemented as research | starter K%, FIP, HR/9; no price or action authority |
| Paper portfolio risk view | Implemented; migration pending | exposure totals, game concentration, promotion-gated sizing |
| Responsive tables | Implemented | contained horizontal scrolling; no page overflow at 390px |
| Self-contained daily pipeline | Implemented | `refresh.sh` has no legacy runtime calls |
| MLBMA deployment synchronization | Implemented | current hub inputs, exact slate reconciliation, visible live fallback |

## Invalidated Claim

The previous `steam >= 4pt` test selected contracts using their eventual closing movement
while scoring them at the opening price. That is decision-time leakage. The result must not
be treated as a tradable edge.

The replacement gate requires:

1. `signal_time`
2. `signal_delta` known at that time
3. `entry_prob` available after the signal
4. whole-game grouped time splits
5. positive OOS bootstrap lower bound
6. minimum OOS sample
7. DSR clearance
8. PBO clearance

Historical rows without those fields are correctly held at `HOLD/ABSTAIN`.

## Remaining Gaps

- Historical data reconciliation and a parallel-run window remain incomplete.
- A validated player-prop projection model and executable player-market price feed do not
  exist yet; the current Props view is research-only.
- The paper-position schema exists, but migration `0002_paper_portfolio.sql` is not applied
  to the remote warehouse. Live-money execution and bankroll custody are out of scope.
- The baseline probability model is transparent but not yet calibrated strongly enough to
  claim a durable betting edge.
- MLBMA context metrics remain non-causal research context until ablation and walk-forward
  tests prove incremental value.
- Weather, umpire, injury, travel, and lineup-confirmation feeds remain incomplete.
- Model and feature registries, drift automation, and formal rollback controls remain open.

## Cutover Status

The active core runtime no longer depends on Bet Evaluator or Sharp Money Tracker. Keep both
repositories available as read-only parity references until historical reconciliation,
both warehouse migrations, and the parallel-run acceptance window are complete.

Do not archive either legacy repository yet.
