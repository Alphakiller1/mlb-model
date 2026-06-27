# Design & Copy Compliance Checklist (consolidated from every prior prompt)

> **Updated 2026-06-27:** the current report uses a decision layer, model-driver layer,
> context-only matchup matrix, responsive table containers, matchup selection, visible
> freshness, and explicit no-price/no-promotion states. Browser verification covered
> desktop and 390px mobile layouts.

Binding requirements distilled from all conversation prompts. Each is audited against the current
Matchup Report + Command Center. Status: ✅ met · ◐ partial · ❌ not met · ⛔ blocked (no data).

| # | Requirement (source: prior prompts) | Status | Note |
|---|---|---|---|
| 1 | Match Chase Analytics / Sharp Money Tracker design (violet, Roboto Condensed, tabular nums, percentile chips, premium tables) | ✅ | tokens adopted from real SMT CSS |
| 2 | Numbers-first; presentation order raw→visual→effect→market→explanation | ◐ | mostly; section subtitles still explanatory (this pass) |
| 3 | Stat standard: raw·baseline·Δ·percentile·rank·sample | ✅ | matrix rows |
| 4 | Scannable: winner, win%, score, total, fair+market lines, top discrepancy, risks, freshness, **action** | ◐ | action not surfaced at top (this pass adds verdict bar) |
| 5 | Semantic color paired with label/number (not color-only) | ✅ | chips + pills + labels |
| 6 | Minimal prose; no AI commentary / hype / profit guarantee | ◐ | headings wordy; methodology long (this pass) |
| 7 | Progressive disclosure for methodology | ✅ | drawer |
| 8 | Short, consistent headings & labels | ❌→✅ | this pass shortens all section headings |
| 9 | No repeated values / no repeated disclaimers | ◐ | subtitle text repeated column meanings (this pass) |
| 10 | Decision states BET/MONITOR/AVOID/NO-EDGE | ✅ | per-market pills + (new) top verdict |
| 11 | Responsive desktop/mobile | ✅ | media queries |
| 12 | No chain-of-thought; reproducible rationale | ✅ | only evidence shown |
| 13 | Defense / rest-travel factors | ⛔ | no pipeline data — honestly omitted |
| 14 | Real browser screenshots desktop+mobile | ◐ | attempted headless capture (see audit); cannot run a full browser harness here |

## Page-by-page text audit (Matchup Report)
- **Section headings**: were explanatory subtitles (e.g. "Market grid · fair vs available (net of
  vig) · max entry = break-even"). → shortened to one word ("Markets", "Matchup", "Drivers", …).
- **Advantage column headers**: "{AWAY} (raw Δ pct)" → "{AWAY}" (format self-evident from chips).
- **Methodology drawer**: 3 sentences → 2 tight bullets.
- **Top of page**: added a single **verdict bar** (action + best edge) so bet/monitor/avoid/no-edge
  is visible without reading.
- **Prose remaining**: only the methodology drawer + risk rows (both concise, behind/at edges).

## Removed / condensed
Explanatory section subtitles; per-column restatement in headers; one redundant strip cell
("Margin" — already in score/run-dist); verbose methodology.

## Prose → visual conversions (already done in prior passes, retained)
Worded "strong matchup" → percentile chips + Δ + rank; verdict prose → state pills + verdict bar;
risk essay → risk table; factor prose → contribution bars.

## Terminology (locked, consistent)
Mkt · Fair · Impl · Model · Edge · EV/u · Max · State · pct · Δ · OSI · FIP · wOBA · OBR · F5.

## Honest remaining gaps
Defense/rest-travel (no data); recent-form trend not yet wired; automated visual-regression needs a
browser harness; Command Center (legacy) still renders bet_evaluator's worded markdown (out of scope
for this pass — it's the legacy surface, not the canonical report).
