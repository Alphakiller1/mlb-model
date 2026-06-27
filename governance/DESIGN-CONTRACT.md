# Design Contract — Chase Analytics / MLB MODEL

Version 1.0.0 · 2026-06-26. The **required** visual spec for every MLB MODEL surface. Tokens are
extracted verbatim from the approved Chase Analytics ecosystem site (`chase-analytics-ecosystem/
index.html :root`) — **not invented**. The unified product must feel like a more capable evolution
of the Sharp Money Tracker + Chase Analytics, not a new redesign.

## Design tokens (canonical — copy, don't fork per page)

```css
:root{
  /* surfaces */
  --bg:#070b12; --band:#0c111c; --panel:#111827; --panel-2:#151d2c;
  --line:rgba(148,163,184,.18); --line-strong:rgba(196,181,253,.34);
  /* text */
  --ink:#f3f6fb; --soft:#cbd5e1; --mut:#94a3b8;
  /* brand accents */
  --teal:#2dd4bf; --violet:#8b5cf6; --violet-2:#c4b5fd; --blue:#60a5fa;
  /* status */
  --green:#22c55e; --amber:#f59e0b; --red:#fb7185;
  /* depth */
  --shadow:0 18px 60px rgba(0,0,0,.34);
  --radius:14px; --radius-sm:10px;
}
/* type */ font-family: Inter, "DM Sans", "Segoe UI", system-ui, sans-serif;
/* mono (data/terminal) */ "JetBrains Mono", Consolas, monospace;
/* page bg: faint 26px grid over a deep navy vertical gradient */
/* panels: linear-gradient(160deg, rgba(17,24,39,.7), rgba(8,13,22,.82)) + --shadow */
/* brand wordmark: text gradient 90deg teal -> violet-2 */
/* primary button / active nav: gradient 135deg violet -> teal */
```

## Status → color mapping (uncertainty-honest, charter UX)
- **BET / PLAY** → teal · **MONITOR / WATCH** → amber · **AVOID / PASS** → red ·
  **NO-EDGE / ABSTAIN** → muted. Model prob (teal), market prob (blue), EV (violet-2) are
  visually distinct. Never imply guaranteed profit.

## Compliance checklist (every surface)
- [ ] Uses the canonical tokens (no hardcoded hex per page)
- [ ] Inter for UI, JetBrains Mono for data/tables
- [ ] Dense, scannable tables; consistent filters
- [ ] Visible **market timestamp** + **model/data version** on every data view
- [ ] Explicit BET / MONITOR / AVOID / NO-EDGE state with the color mapping
- [ ] Model vs market probability vs EV visually separated
- [ ] Prominent uncertainty + conflicting-evidence display
- [ ] Loading / empty / error / **stale-data** states styled (not blank)
- [ ] Accessible contrast (AA) + keyboard-navigable controls
- [ ] Responsive desktop + mobile

## Current compliance status (evidence)
- **Legacy `command_center` (bet-evaluator)** — **rebranded to these tokens this session**
  (Inter, teal→violet gradient wordmark, glassy panels, status colors). Serves at :8787. This is
  the **parallel-run** UI; it is NOT the unified product home.
- **Gap (must flag, per charter "identify missing access"):** MLB MODEL has **no existing frontend
  framework/component system** yet — it is a Python package. The charter's "use the MLB Model's
  existing frontend framework" cannot be satisfied until a unified-UI stack is chosen (decision
  required: extend the stdlib-HTTP command_center, or a real framework). Until then, the design
  contract is enforced via these tokens + the checklist, applied to the parallel-run UI.
