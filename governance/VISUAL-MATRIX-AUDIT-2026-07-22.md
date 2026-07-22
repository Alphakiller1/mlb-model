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
market verification coverage, token discipline, and low-data desktop empty states.

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

Important viewport note: plain Chrome CLI screenshots on Windows can crop a wider browser window
when asked for 375px. Chrome DevTools Protocol was used for true 375px CSS viewport checks.

CDP verification:

- Matchups at 375px: `innerWidth=375`, `scrollWidth=375`, active nav rect `191..362`.
- Trends at 375px: `innerWidth=375`, `scrollWidth=375`, first trend card rect `29..346`.

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
| Every live decision state must be visually exercised | Fixture has no live market or prop price snapshot, so BET/LEAN cards are not visually exercised with live rows | Conditional |

## Route Matrix

| Route / tab | Desktop verdict | Mobile verdict | Strict notes |
|---|---|---|---|
| Today | Pass | Pass | Biggest improvement. Rows now have hierarchy, team marks, pitcher context, projection chips, and a model-focus rail. Mobile stacks cleanly. |
| Matchups | Pass | Pass | Strongest analytical surface. Desktop is dense but deliberate. Mobile CDP confirms no overflow. |
| Trends | Pass | Pass | Desktop table is acceptable for analyst scanning. Mobile now uses trend cards and one-column stat blocks. |
| Markets | Conditional pass | Conditional pass | Empty state is clean. Live sharp-vs-soft play cards were not visually exercised because fixture has no actionable sharp divergence. |
| Props | Pass | Pass | Strong visual lift: headshots, team logos, projection chips, and no-market state are clear. Price snapshot absence remains data/config, not UI. |
| Portfolio | Polish fail, not blocker | Pass | Honest unavailable state works, but desktop feels sparse when warehouse credentials are absent. Needs richer empty-state framing later. |
| Results | Polish fail, not blocker | Pass | Tracker scaffold is good. Desktop has too much empty vertical space with no warehouse rows. |
| Research | Polish fail, not blocker | Pass | Gate/sample/F5/calibration layout is coherent. Like Results, it needs richer low-data state on desktop. |

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
surfaces. Results/Research can still feel like a dark dashboard when data is unavailable, but the
promotion gate language keeps them from looking dead.

### 2. Layout and hierarchy

Verdict: Pass with polish gaps.

Improvements:

- Today moved from table-first to command-board-first.
- Matchups keeps decision content above the fold.
- Props makes each pitcher row inspectable and visually anchored.
- Results now exposes grading coverage instead of a blank/unavailable dead end.
- Trends mobile no longer relies on a cropped table.

Remaining strict issues:

- Results and Research desktop have large unused lower canvas when warehouse reads fail.
- Portfolio desktop is honest but thin.
- Markets cannot be fully judged until live sharp/price rows exist in the visual fixture.

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

Verdict: Partial.

The visual language uses the vendored Chase token layer and shared CSS, but strict token compliance
is not perfect.

Known token debt:

- `mlbmodel/report/app.py` still contains inline `style=` fragments for card font sizes, progress
  widths, edgebar widths, and old Markets verdict styling.
- `_VERDICT` still stores hard-coded colors in Python.
- `mlbmodel/report/matchup.py` and `chase_components.css` include some hard-coded hex values that
  are effectively Chase token copies, but not always referenced through CSS variables.

Strict standard: this should be cleaned before declaring a final design system. It is acceptable for
this branch because the colors match the Chase/SMT ecosystem, but it is not fully compliant with a
"tokens only" rule.

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

Verdict: Improved, but not complete for every future projection shape.

Implemented:

- `model_predictions` can now settle against final game outcomes.
- settlement records actual winner/runs/margin and `settled_time`.
- rows without a clear side remain ungraded; the loop does not guess.
- updates require a unique `prediction_id` or `id`; game-only updates are intentionally blocked.

Strict limitations:

- the current `grade_model_prediction` grades team-side/winner style predictions only.
- if future `model_predictions` rows represent totals, run lines, player props, or F5 markets, they
  need explicit market-aware grading.
- rows without a unique ID will stay safely ungraded until schema/IDs are corrected.
- migration `0003_model_prediction_settlement.sql` must be applied before remote persistence works.

## Strict Finding List

### Blockers

None found for pushing this branch.

### Should-fix before product/design freeze

1. Market and prop live states need a real visual exercise.
   - Evidence: fixture renders `NO SNAPSHOT`, `NO MARKET`, and no sharp-vs-soft plays.
   - Risk: the new mobile Markets card and live prop market report are structurally present but not
     pixel-proven with live price rows.

2. Token debt should be paid down.
   - Evidence: inline styles and hard-coded verdict colors remain in `app.py`; token-like hex values
     remain in `matchup.py` and shared component CSS.
   - Risk: future design changes will drift if colors are not centralized.

3. Results/Research/Portfolio need richer low-data desktop states.
   - Evidence: desktop screenshots show coherent panels but large empty lower canvas.
   - Risk: public users may read these surfaces as unfinished when warehouse data is absent.

4. Projection grading must become market-aware.
   - Evidence: current settlement handles predicted winner/team side. It does not yet grade totals,
     run lines, F5, or player props.
   - Risk: "model projections grade themselves" can be overclaimed unless row shapes are constrained.

5. Governance typography contract needs reconciliation.
   - Evidence: `DESIGN-CONTRACT.md` and `DESIGN-COMPLIANCE-CHECKLIST.md` describe different font
     systems.
   - Risk: future agents may "fix" the app toward the wrong document.

### Polish

1. Desktop Today is strong but could use a denser sticky slate filter/date selector.
2. Mobile nav is clean at true 375px but consumes a large first-viewport block.
3. Matchups desktop is analytically excellent but very dense; future pass could add stronger section
   anchors once data volume grows.
4. Empty-state language is honest but could be more operational, for example "Apply migration 0003"
   where relevant.

## Final Route Verdicts

| Surface | Verdict |
|---|---|
| Today | Pass |
| Matchups | Pass |
| Trends | Pass |
| Markets | Conditional pass |
| Props | Conditional pass |
| Portfolio | Pass with polish |
| Results | Pass with polish |
| Research | Pass with polish |

## Final Recommendation

Push the branch. It improves the MLB Model's visual foundation, preserves Chase Analytics identity,
adds real product structure, and fixes a real grading gap. Do not call the visual system complete
until live price states, market-aware settlement, token cleanup, and richer low-data desktop states
are completed.

