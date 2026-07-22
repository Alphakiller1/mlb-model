# Visual Matrix Audit - MLB Model

Date: 2026-07-22
Branch: `codex/mlb-model-visual-primitives`
Fixture: `deployment_data`
Rendered app: `python -m mlbmodel.report.app --game TEX@TOR --out ... --no-fetch --data-dir deployment_data`

## Executive Verdict

This branch is a material visual and product-structure upgrade over the prior MLB Model shell.
It is strong enough to push for review. It is not yet a final design freeze.

Overall grade: `B+ / branch-ready, not production-polish-complete`.

The work succeeds at the main goal: the MLB Model now reads like a Chase Analytics product with
a real command-board workflow instead of a dense generic research table. The strongest areas are
Today, Matchups, Pitcher Props, and the new Results tracker scaffold. The weakest areas are live
browser-verified live market coverage, remaining token debt, and player-prop settlement inputs.

## Evidence Captured

Local visual evidence was rendered to:

`C:/Users/user/Documents/Codex/2026-07-12/run/outputs/`

Primary matrix screenshots:

- `matrix_today_1280.png`
- `matrix_today_375.png`
- `matrix_matchups_1280.png`
- `matrix_matchups_375_cdp.png`
- `matrix_trends_1280.png`
- `matrix_trends_375_cdp.png`
- `matrix_markets_1280.png`
- `matrix_markets_375.png`
- `matrix_props_1280.png`
- `matrix_props_375.png`
- `matrix_portfolio_1280.png`
- `matrix_portfolio_375.png`
- `matrix_results_1280.png`
- `matrix_results_375.png`
- `matrix_research_1280.png`
- `matrix_research_375.png`

Post-update low-data captures:

- `post_portfolio_1280.png`
- `post_portfolio_375_tall.png`
- `post_results_1280.png`
- `post_results_375_tall.png`
- `post_research_1280.png`
- `post_research_375_tall.png`

Important viewport note: plain Chrome CLI screenshots on Windows can crop a wider browser window
when asked for 375px. Chrome DevTools Protocol was used for true 375px CSS viewport checks.

CDP verification:

- Matchups at 375px: `innerWidth=375`, `scrollWidth=375`, active nav rect `191..362`.
- Trends at 375px: `innerWidth=375`, `scrollWidth=375`, first trend card rect `29..346`.
- Post-update Portfolio at 375px: `innerWidth=375`, `scrollWidth=360`, readiness cards `29..331`.
- Post-update Results at 375px: `innerWidth=375`, `scrollWidth=360`, readiness cards `29..331`.
- Post-update Research at 375px: `innerWidth=375`, `scrollWidth=360`, readiness cards `29..331`.

Strict conclusion: no page-level horizontal overflow was observed at a true 375px CSS viewport.

## Mockup-Direction Comparison

Baseline visual direction artifact:

- `mlb_model_visual_primitives_1280.png`

That earlier state already had the Chase header, rail, dark grid, and card language, but the Today
surface still behaved like a premium table. The current branch moves substantially closer to the
intended mockup/product direction:

| Target from mockup direction | Current state | Verdict |
|---|---|---|
| Chase Analytics identity must be first-read | Header, icon, wordmark, product tag, side rail are persistent | Pass |
| Slate should feel like a command board, not a spreadsheet | Today now uses per-game rows with logos, SPs, time, projected score, total, margin, and sharp count chips | Pass |
| Matchups need analyst-grade breakdowns | Matchup hero, decision strip, advantage matrix, run-impact panel, risks, and market state are visible | Pass |
| Pitcher props need research-tool density | Props now has headshots, starter identity, baseline, K/BB/ER/outs projections, market state, and mobile cards | Pass |
| Projection grading/progress tracker must be visible | Results now has grading progress, settlement counts, calibration, and ledger scaffold | Pass, data-dependent |
| Mobile should be cards-first | Matchups, Trends, Props, Results, Research are mobile card/scaffold driven | Pass |
| Live betting confidence should remain honest | HOLD/ABSTAIN, NO ACTION, NO MARKET, and unavailable states are visible | Pass |
| Every live decision state must be visually exercised | Unit fixtures now render live Markets and Props rows; browser screenshots still depend on a live price slate | Conditional |

## Route Matrix

| Route / tab | Desktop verdict | Mobile verdict | Strict notes |
|---|---|---|---|
| Today | Pass | Pass | Biggest improvement. Rows now have hierarchy, team marks, pitcher context, projection chips, and a model-focus rail. Mobile stacks cleanly. |
| Matchups | Pass | Pass | Strongest analytical surface. Desktop is dense but deliberate. Mobile CDP confirms no overflow. |
| Trends | Pass | Pass | Desktop table is acceptable for analyst scanning. Mobile now uses trend cards and one-column stat blocks. |
| Markets | Conditional pass | Conditional pass | Empty state is clean. Unit fixtures now exercise live sharp/model cards; browser fixture still needs a real priced slate. |
| Props | Pass | Pass | Strong visual lift: headshots, team logos, projection chips, no-market state, and a tested priced prop state are clear. |
| Portfolio | Pass with polish | Pass | Unavailable and zero-position states now use readiness cards instead of a single sparse box. |
| Results | Pass with polish | Pass | Tracker scaffold plus settlement-readiness cards make low-data desktop states intentional. |
| Research | Pass with polish | Pass | Gate/sample/F5/calibration layout now includes research-readiness framing when samples are absent. |

## Standards Audit

### 1. Identity and brand

Verdict: Pass.

The branch preserves and strengthens Chase Analytics identity:

- persistent Chase header and icon;
- dark grid environment;
- purple/violet active states;
- team logos and pitcher headshots;
- board/panel framing across Today, Matchups, Props, Results, and Research.

Strict note: this no longer reads like a generic AI dashboard on the primary Today/Matchups/Props
surfaces. Results/Research/Portfolio now carry operational readiness cards when data is unavailable,
which keeps low-sample states from looking dead.

### 2. Layout and hierarchy

Verdict: Pass with polish gaps.

Improvements:

- Today moved from table-first to command-board-first.
- Matchups keeps decision content above the fold.
- Props makes each pitcher row inspectable and visually anchored.
- Results now exposes grading coverage instead of a blank/unavailable dead end.
- Trends mobile no longer relies on a cropped table.

Remaining strict issues:

- Markets cannot be fully judged in browser screenshots until a live sharp/price slate exists.
- Player-prop settlement still needs a dedicated player outcome source before auto-grading can be claimed.

### 3. Mobile behavior

Verdict: Pass.

True 375px CDP checks confirm:

- document width stays at 375px;
- nav active states fit inside the viewport;
- Trends cards fit inside the viewport;
- Matchups stacks decision-strip values and advantage cards without page overflow.

Plain Chrome CLI `--window-size=375` is not reliable on this machine because it cropped a wider
minimum browser layout. CDP evidence should be treated as authoritative.

### 4. Data honesty and no-action states

Verdict: Pass.

The interface does not fake confidence:

- price snapshot missing -> `NO SNAPSHOT` / `NO MARKET`;
- promotion gate blocked -> `HOLD/ABSTAIN`;
- no paired market snapshot -> `NO ACTION`;
- warehouse unavailable -> visible unavailable state, not blank;
- projection settlement coverage -> visible 0 percent tracker.

This aligns with the repo safety invariant that missing prices and failed reads produce visible
no-action states.

### 5. Token and color discipline

Verdict: Improved partial.

The visual language uses the vendored Chase token layer and shared CSS, but strict token compliance
is not perfect.

Known token debt:

- `mlbmodel/report/app.py` still contains dynamic inline `style=` fragments for progress and edgebar
  widths.
- `mlbmodel/report/matchup.py` and `chase_components.css` include some hard-coded hex values that
  are effectively Chase token copies, but not always referenced through CSS variables.
- Markets verdicts now use semantic pill/data classes instead of hard-coded Python colors.

Strict standard: dynamic bar widths are acceptable as data visualization, but copied token values
should still be centralized before declaring a final design system.

### 6. Typography and numeric clarity

Verdict: Partial pass.

The current implementation follows the newer repo checklist direction: Chase/SMT styled display
type, condensed numeric rhythm, and tabular numbers. Numeric data is scannable.

Strict issue: governance docs conflict. `DESIGN-CONTRACT.md` still references Inter and JetBrains
Mono, while the newer compliance checklist references Roboto Condensed and tabular numbers. The
branch follows the newer visible Chase implementation rather than the older written contract.

Action: update governance to one typography contract before future UI work.

### 7. Accessibility

Verdict: Partial pass.

Passes:

- nav and slate rows are button/select controls;
- tap targets are generally at or above 40px;
- active/focus states exist on slate rows and nav buttons;
- color is paired with labels, not used alone.

Strict gaps:

- table-heavy desktop surfaces still need keyboard/focus QA beyond static screenshots;
- several low-contrast muted labels should be checked with an automated contrast tool;
- inline tooltips/title attributes are not a full accessible explanation pattern.

### 8. Grading and settlement correctness

Verdict: Improved, but not complete for player props.

Implemented:

- `model_predictions` can now settle ML, totals, team totals, runline/spread, and F5 markets when
  matching outcome fields exist.
- settlement records actual winner/runs/margin and `settled_time`.
- rows without a clear side remain ungraded; the loop does not guess.
- updates require a unique `prediction_id` or `id`; game-only updates are intentionally blocked.

Strict limitations:

- player props are still intentionally ungraded until the model has a player-outcome table or feed.
- rows without a unique ID will stay safely ungraded until schema/IDs are corrected.
- migration `0003_model_prediction_settlement.sql` must be applied before remote persistence works.

## Strict Finding List

### Blockers

None found for pushing this branch.

### Should-fix before product/design freeze

1. Market and prop live states need a browser visual exercise on a real priced slate.
   - Evidence: unit fixtures render live Markets and Props rows, but screenshot fixtures still render
     mostly `NO SNAPSHOT` / `NO MARKET`.
   - Risk: the live states are structurally tested but not pixel-proven against real feed density.

2. Remaining token debt should be paid down.
   - Evidence: verdict colors were moved to semantic classes, but token-like hex values remain in
     `matchup.py` and shared component CSS.
   - Risk: future design changes will drift if colors are not centralized.

3. Live priced-slate screenshots should be captured when the feed is active.
   - Evidence: low-data desktop/mobile states were recaptured after this update, but live market
     density still depends on a real priced slate.
   - Risk: static test coverage is green, but final pixel QA should compare populated Markets rows.

4. Player-prop grading needs a dedicated outcome source.
   - Evidence: game markets are now market-aware; player props still have no player result schema.
   - Risk: "all projections grade themselves" can be overclaimed unless prop rows are excluded or
     player outcomes are added.

5. Governance typography contract needs reconciliation.
   - Evidence: `DESIGN-CONTRACT.md` and `DESIGN-COMPLIANCE-CHECKLIST.md` describe different font
     systems.
   - Risk: future agents may "fix" the app toward the wrong document.

### Polish

1. Desktop Today is strong but could use a denser sticky slate filter/date selector.
2. Mobile nav is clean at true 375px but consumes a large first-viewport block.
3. Matchups desktop is analytically excellent but very dense; future pass could add stronger section
   anchors once data volume grows.
4. Empty-state language is now more operational, but final copy should be reviewed once migrations
   are applied in production.

## Final Route Verdicts

| Surface | Verdict |
|---|---|
| Today | Pass |
| Matchups | Pass |
| Trends | Pass |
| Markets | Conditional pass |
| Props | Pass |
| Portfolio | Pass with polish |
| Results | Pass with polish |
| Research | Pass with polish |

## Final Recommendation

Push the branch. It improves the MLB Model's visual foundation, preserves Chase Analytics identity,
adds real product structure, and fixes a real grading gap. Do not call the visual system complete
until live price states are browser-captured, player-prop outcomes exist, remaining token copies are
centralized, and the typography contract is reconciled.
