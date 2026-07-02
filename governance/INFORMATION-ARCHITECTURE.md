# Information Architecture — MLB MODEL

> **Implementation update 2026-06-27:** Today rows and the Matchups selector now switch
> among all loaded games without regenerating the application. Props and Portfolio remain
> explicit placeholders rather than simulated functionality.

Version 1.0.0 · 2026-06-27. The product is one coherent app (`mlbmodel/report/app.py`), not
separate dashboards. Repository boundaries (Bet Evaluator / Sharp Money Tracker / MLBMA) are never
exposed to the user.

## Workflow
`discover → inspect → evaluate → compare → decide → track → review`
maps to: Today → Matchups → (Markets/Props evidence) → Markets price → verdict → Portfolio → Results.

## Sitemap (implemented)
```
MLB Model
├─ Today        discover: slate, model leans, sharp count, data status        [real]
├─ Matchups     inspect: full game report (decision→analysis→methodology)     [real]
├─ Markets      compare: sharp-vs-soft divergence + steam, by game            [real]
├─ Props        player markets (pitcher/hitter)                               [structured stub]
├─ Portfolio    open risk, bankroll, exposure (paper-trading)                 [structured stub]
├─ Results      settled outcomes, CLV, calibration, counts                    [real, builds w/ data]
└─ Research     model/data health, promotion gate, calibration (secondary)    [real]
```

## Page hierarchy (every analytical page)
1. Context (header: teams, SP, time, park, freshness)
2. Primary conclusion (verdict bar: action + edge + reason)
3. Price & opportunity (strip cards + Markets tab)
4. Supporting evidence (Why panel + Analysis tabs)
5. Risks & conflicting signals (Top-risks panel + Sharp tab)
6. Recommended action (verdict bar state)
7. Methodology (drawer, on demand)
**Never starts with methodology.** Decision layer is above the fold; depth is in tabs/drawers.

## Canonical ownership (one home per fact — no duplication)
| Information | Canonical home |
|---|---|
| Game projection / fair price | Matchups (report) |
| Market price / edge / EV / state | Matchups → Markets tab (per game); Markets (cross-slate sharp) |
| Sharp divergence / steam | Markets (+ Matchups Sharp tab links the same data) |
| Player props | Props |
| Open risk / bankroll | Portfolio |
| Outcomes / CLV / calibration | Results |
| Model/data health / promotion gate | Research |
Shared summaries (e.g. Today's leans) **link** to the canonical detail; they don't recompute it.

## Navigation spec
Persistent left sidebar (collapses to a top wrap on mobile ≤760px). Brand + 7 items; active item
highlighted (violet gradient). Within Matchups, the **Analysis layer uses pure-CSS radio tabs**
(no JS dependency): Markets · Charts · Matchup · Drivers · Sharp — one visible at a time.

## Consistency rules (enforced)
Terminology locked: Mkt · Fair · Impl · Model · Edge · EV/u · Max · State · OSI · FIP · wOBA · OBR ·
F5. Semantic color is constant: teal/green = advantage/over, red = disadvantage/under/avoid,
amber = monitor/caution, violet = brand/side, muted = neutral/no-edge. Color is always paired with a
number + label. Market columns are in a fixed order everywhere.

## Migration sequence (status)
1. ✅ Shell + 7 routes + nav. 2. ✅ Matchups = canonical report. 3. ✅ Today/Markets/Results/Research
real data. 4. ◐ Props/Portfolio structured stubs (need projection-market + paper-ledger wiring).
5. ◐ Persist selected game/date context across nav (currently featured-game is static per build).

## Wireframes / screenshots
`docs/screenshots/today-slate.png`, `docs/screenshots/matchup-decision-first.png` (desktop). Mobile
verified via 390px headless capture (nav wraps, tables scroll, cards 2-up).

## Remaining structural issues (honest)
- Props/Portfolio are stubs (no player-prop market feed / no paper-trading ledger yet).
- Featured matchup is static per build (a real app needs client-side game selection / routing).
- Today's "top model-market discrepancies" currently uses model leans (per-game odds not fetched
  for all 15 — would cost API credits); true discrepancy ranking needs the odds-per-game backfill.
- Empty vertical space on short tab views (cosmetic).
- Research lives outside the betting workflow (correct), but a cross-link from a stale-data warning
  to Research/Data-health is not yet wired.
