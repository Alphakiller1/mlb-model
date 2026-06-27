# Matchup Intelligence Report — Specification & Audit

> **Implementation update 2026-06-27:** the report is now self-contained, switches across
> every slate matchup, uses paired de-vigged market probabilities, separates contextual
> MLBMA statistics from true model drivers, and cannot display BET unless the relevant
> strategy is promoted. Remaining analytical gaps are tracked in
> `IMPLEMENTATION-STATUS-2026-06-27.md`.

Version 1.0.0 · 2026-06-27. The canonical output of the unified MLB Model. Covers the charter's 12
deliverables. **Status: a working v1 exists** (`mlbmodel/report/matchup.py`, generated live for
NYY@BOS, action ABSTAIN) — analytically real and design-compliant, but **not yet complete**: many
of the 24 content items await underlying data/logic migration (gaps below).

## 1. Design-source inventory (evidence)
- **Chase Analytics ecosystem** (`chase-analytics-ecosystem/index.html`) — the approved token set
  (dark navy, teal #2dd4bf + violet #8b5cf6, Inter, glassy panels, 26px grid). **Authoritative.**
- **Sharp Money Tracker** (`sharp-money-tracker/docs/`) — dashboard pattern reference.
- **SCL workspace** (`Projects/SCL`) — planning/QA layer; design contract guidance. *No MLB Model
  code goes here.*
- **Legacy Command Center** (`bet-evaluator/command_center.py`) — now rebranded to the tokens.

## 2. Design-contract precedence map
On conflict: **Chase Analytics ecosystem tokens > Sharp Money Tracker > legacy Command Center.**
Codified in [DESIGN-CONTRACT.md](DESIGN-CONTRACT.md) (the single source of tokens).

## 3. Current MLB Model UX assessment
Before: no MLB Model UI (Python package only); legacy Command Center was off-polish. Now: tokens
canonicalized; Command Center rebranded; **the Matchup Report is the first true product surface** in
the brand. Gap: still no shared frontend framework — report is server-rendered HTML (acceptable v1).

## 4. Matchup Report information architecture (implemented v1)
Compact header (teams/SP/park/weather + model & data version) → 4 summary cards (win prob, expected
total, fair edge, **action**) → markets table (fair vs available, vig-free, EV/u, **max entry =
break-even**) → factor-contribution table → sharp-money panel → progressive-disclosure details
(risks/counterarguments/invalidation; model & data audit). Responsive (grid collapses ≤760px).

## 5. Factor-to-conclusion data map (implemented)
Each factor row carries: name · value · baseline · direction · **effect % on expected runs** ·
markets affected · confidence · priced-in? · stability. Trace structure realized:
`observation → regressed feature → multiplicative effect → expected runs → fair price → market`.
Correlated SP+bullpen blended once (no double-count). Source: `bet_evaluator.offense_factor /
pitch_factor / park`.

## 6. Source-logic traceability matrix (each section → real logic)
| Report section | Source logic | Data |
|---|---|---|
| Win prob / expected runs | `bet_evaluator.model_probabilities` | hub_dataset features + settled-finals anchors |
| Fair prices / EV / max entry | `bet_evaluator.market_probability` + `value_layer` | model prob + market odds |
| Factor contribution | `offense_factor`/`pitch_factor`/park | OSI, FIP, bullpen, park |
| Sharp money | warehouse `sharp_signals` (de-vig + steam) | point-in-time signals |
| Risks / invalidation | `bet_evaluator.risk_layer` + variance anchors | team profiles, weather |
| Action | honest-empty + value verdicts + promotion-gate philosophy | — |
| Audit | `config.MODEL_VERSION/METRIC_VERSION` + anchors | versions + timestamps |

## 7. Reusable component plan
Shared tokens (DESIGN-CONTRACT) → components: `card`, `panel`, scannable `table`, `pill`/status,
`details` progressive disclosure, `trace` source caption. No per-page styles. As a real frontend is
chosen, port these 1:1.

## 8. Responsive interface spec
Desktop: 1080px max, 4-col cards, full tables. Mobile (≤760px): 2-col cards, tables scroll, details
collapsed — **risk, pricing, and uncertainty never hidden** (charter). AA contrast via tokens.

## 9. Missing-data & analytical-gap report (honest)
Implemented: matchup summary, win prob, expected runs/total, fair ML/total/runline, factor table,
sharp money, risks/invalidation, action, audit. **Not yet (need migrated data/logic):** run-line/
F5 fair set beyond -1.5, pitcher/hitter **props**, pitch-mix/platoon interaction surfacing,
defense/baserunning, **umpire**, rest/travel/circadian, injury feed, projection **charts/
distributions**, scenario/sensitivity sweep, historical analogs, portfolio/correlated exposure.
Also: weather not in the runs model; OSI is a team proxy; no validated OOS edge (gate = ABSTAIN).

## 10. Implementation roadmap (dependency-aware)
1. Migrate de-vig + expected-runs into `mlbmodel` (parity-tested) → drop the legacy import.
2. Add props + F5 fair prices (board_analytics/pitcher_model_layers migration).
3. Add distribution/sharp-timeline charts (lightweight SVG, token-styled).
4. Pull pitch-mix/platoon + bullpen-fatigue surfacing from hub_dataset.
5. Scenario/sensitivity + correlated-exposure once a portfolio module exists.
6. Choose the unified-UI framework; port components; add Playwright visual-regression.

## 11. Visual & functional QA checklist
- [ ] Tokens only (no per-page hex) — **pass** · [ ] Inter + JetBrains Mono — **pass**
- [ ] Versions + timestamps visible — **pass** · [ ] Explicit BET/MONITOR/AVOID/ABSTAIN — **pass**
- [ ] Model vs market vs EV distinct — **pass** · [ ] Uncertainty/counterarguments shown — **pass**
- [ ] Responsive ≤760px — **pass (CSS)** · [ ] No implied profit guarantee — **pass**
- [ ] Empty/stale states styled — *partial (weather-missing degrades gracefully; needs stale badge)*
- [ ] Visual-regression snapshots — **todo**

## 12. Reproducibility evidence
The report is a pure function of versioned inputs: `build_report(away, home)` → model prob/fair/EV
recomputed from `bet_evaluator` + warehouse, stamped with model/metric version + UTC timestamp +
deterministic `game_pk`. Re-running on the same point-in-time inputs yields identical numbers. The
oddsmath underpinning is parity-verified vs legacy (`tests/test_parity_oddsmath.py`).

## Acceptance (not yet met)
v1 is analytically traceable, design-compliant, responsive, reproducible — but **incomplete** on the
24-item content set and still imports legacy logic. Not claiming completion; roadmap above closes it.
