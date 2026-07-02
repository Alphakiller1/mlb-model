# Implementation Status — 2026-06-27

This is the controlling current-state record. Older audit documents remain as historical
evidence and are explicitly marked where their conclusions were invalidated.

## What Is Implemented

| Capability | Status | Evidence |
|---|---|---|
| Context-aware expected-runs runtime | Implemented as unpromoted champion candidate | `mlbmodel/baseball/` |
| Exact model-factor lineage | Implemented | probability output owns its factor contributions |
| Overdispersed run simulation | Implemented as challenger | 25,000 deterministic draws; no betting authority |
| MLBMA skill and context metrics | Implemented in projections | team/batter splits, SP season/L14, bullpen quality/workload, pitch response |
| Paired book-level de-vig | Implemented and tested | `market/quotes.py`, `test_quotes.py` |
| Value state controlled by promotion | Implemented and tested | `market/value.py`, `test_value.py` |
| Sharp-versus-soft collection | Implemented | `market/collect.py` |
| Sharp observation settlement | Implemented | `market/settle.py` |
| Executable-entry validation | Implemented and tested | `backtest/walkforward.py` |
| DSR/PBO/OOS promotion gate | Implemented | `quant/promotion_gate.py` |
| Collision-safe doubleheaders | Implemented for new slates/results | game number is included after game 1 |
| Unified interactive report | Implemented | concise matchup decision flow, full slate selection |
| Pitcher-prop projection engine | Implemented as unpromoted challenger | 30,000 draws for K/BB/ER/outs/F5 ER |
| Pitcher-prop market report | Implemented; public price snapshot not configured | paired de-vig, best price, model/market gap, EV, action state |
| Pitcher vs lineup pitch map | Implemented | batting-order player response when posted; team response fallback |
| Live lineup/weather/umpire/injury/travel contract | Implemented | official MLB + first-pitch Open-Meteo; explicit unavailable states |
| Official probable-pitcher fallback | Implemented | fills MLBMA lag with lower-confidence MLB season stats |
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
- The player-prop model and event-level price adapter exist, but neither is promoted. The
  public deployment has no `ODDS_API_KEY`, so it correctly displays `NO MARKET`.
- The paper-position schema exists, but migration `0002_paper_portfolio.sql` is not applied
  to the remote warehouse. Live-money execution and bankroll custody are out of scope.
- The context-aware probability model is transparent but not yet calibrated strongly enough to
  claim a durable betting edge.
- New lineup, weather, umpire, injury, travel, bullpen-workload, and pitch-response effects
  remain unpromoted until ablation and point-in-time walk-forward tests prove incremental value.
- Lineups and umpires are legitimately unavailable before MLB posts them; confidence and
  action state degrade automatically rather than inferring them.
- Model and feature registries, drift automation, and formal rollback controls remain open.

## Cutover Status

The active core runtime no longer depends on Bet Evaluator or Sharp Money Tracker. Keep both
repositories available as read-only parity references until historical reconciliation,
both warehouse migrations, and the parallel-run acceptance window are complete.

Do not archive either legacy repository yet.
