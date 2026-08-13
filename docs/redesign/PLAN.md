# MLB Model — Full Platform Redesign Plan

**Status:** Desk product shell live (sidebar + composition rewrite — not CSS veneer)  
**Direction:** **Purple · Black Desk** — Terminal Desk density + Chase purple/black identity  
**Date:** 2026-07-23

---

## 1. North star

Surface the **most pertinent information** for the sharpest, most informed bet — organized, appropriately concise, never decorative.

Workflow: discover slate → open matchup → see action + price → only then dig into evidence.

**Palette:** graphite surfaces + bright violet accent. Status mint / amber / coral for BET / MONITOR / AVOID only.

**Matchup law:** comparable metrics stay symmetric — `Away | label | Home`.

### Product promise
- Verdict + markets above the fold; depth on demand
- No empty KPI strips, duplicate boards, or prose walls
- Model vs market vs EV visually separated
- Numbers over narrative; honest empty / no-edge / stale states

---

## 2. What changes vs what stays

| Layer | Keep | Reinvention |
|-------|------|-------------|
| IA / routes | Today · Matchups · Trends · Markets · Props · Results · Research | Visual language, density, hierarchy |
| Decision states | BET / MONITOR / AVOID / NO-EDGE | New status chrome (mint / amber / coral / mute) |
| Data contracts | Same report builders / CSV / warehouse | Presentation only in Phase 1 |
| MLBMA sync | Data feed unchanged | Stop vendoring MLBMA violet board CSS as identity |
| Brand | Chase wordmark in shell | Model product mark + desk chrome |

**Structure lock for Phase 1:** same seven views and matchup decision→evidence flow. No section merge/split until mockups are approved.

---

## 3. Visual system (Terminal Desk)

### Surfaces
- Black page `#07060C`, raised `#0C0B14`, panel `#12101C` → `#1A1728`
- Purple hairlines `#2A2540` / `#4A3F6E`
- Radius: 6px desk
- Soft violet inset highlight OK; no multi-layer neon glow stacks

### Accent & status
| Role | Token | Use |
|------|-------|-----|
| Brand | `--brand` `#9A6BFF` | Wordmark, active nav, axes, logos |
| Brand deep | `--brand-deep` `#5B2BE0` | Gradients |
| Edge / BET | `--signal` mint `#3DFF9A` | Positive EV, BET pill |
| MONITOR | `--watch` amber `#E8B84A` | Caution |
| AVOID | `--cut` coral `#FF5C6A` | Negative edge |
| NO-EDGE | `--mute` `#6B6680` | Abstain |
| Gold meta | `--gold` `#E8C24A` | Freshness / version |

### Matchup symmetry
Primary breakdown is a mirrored board (see mockup `02_matchup.html`):
hero Away↔Home, then metric rows, then equal Away edges | Home edges columns.

### Typography
- **UI:** IBM Plex Sans
- **Prices / tables:** IBM Plex Mono (tabular)
- **Display:** Barlow Condensed (page titles, KPI values only)
- Avoid Inter / Roboto / system-default stacks as primary

### Density
- Sidebar 220px → 56px icon rail on ≤960px
- Table row ~36px; KPI strip single row; verdict bar sticky under pagehead
- Max content width ~1280px

---

## 4. Information architecture (unchanged workflow)

```
discover → inspect → evaluate → compare → decide → track → review
   Today    Matchups   Markets/Props   Markets    verdict  (paper)  Results
```

| View | Job | Above-the-fold |
|------|-----|----------------|
| **Today** | Discover slate | Freshness + slate table + top leans rail |
| **Matchups** | Decide one game | Context → verdict → KPI → Why/Risks → Markets tabs |
| **Trends** | Form signals | Ranked trend list → open matchup |
| **Markets** | Cross-slate sharp | Divergence / steam table |
| **Props** | Player markets | Channel filter → prop cards/table |
| **Results** | Grade & CLV | Record strip + settled table |
| **Research** | Model health | Gate / calibration / sync status |

Canonical ownership rules from `governance/INFORMATION-ARCHITECTURE.md` remain binding.

---

## 5. Screen specs (mockup set)

| # | File | Purpose |
|---|------|---------|
| 00 | `mockups/index.html` | Hub + direction summary |
| 01 | `mockups/01_today.html` | Slate desk + leans |
| 02 | `mockups/02_matchup.html` | Decision-first matchup (canonical) |
| 03 | `mockups/03_markets.html` | Sharp vs soft cross-slate |
| 04 | `mockups/04_props.html` | Pitcher/hitter prop desk |
| 05 | `mockups/05_results.html` | Settled + CLV |
| 06 | `mockups/06_trends.html` | Per-matchup form signals |
| 07 | `mockups/07_research.html` | Gate · F5 · Kalshi |

Shared: `mockups/desk.css` (tokens + components).

---

## 6. Implementation phases (after mockup sign-off)

### Phase 0 — Contract
- Replace `governance/DESIGN-CONTRACT.md` with Terminal Desk tokens
- Freeze MLBMA CSS sync for *visual* identity (`scripts/sync_chase_css.py` → data/helpers only)

### Phase 1 — Shell + all views (in progress / shipping)
- Purple · black `desk_global.css` on every section
- Unified `desk_pagehead` on Today · Matchups · Trends · Markets · Props · Results · Research
- Symmetric slate columns (Win% A|H, SP A/H, K% A/H) + matchup sym boards
- Regenerate `mlb_model_app.html`

### Phase 2 — Markets · Trends · Props · Results · Research
- Apply same table/KPI/empty patterns
- Props: real empty vs loaded states; no fake EV

### Phase 3 — Polish
- Motion: view fade 180ms, row hover only (respect reduced-motion)
- Stale-data banner → Research deep-link
- Visual regression screenshots in `docs/screenshots/`

**Out of scope until asked:** React rewrite, live SPA routing, Portfolio ledger, auto-betting.

---

## 7. Acceptance criteria

- [ ] First glance: not MLBMA violet boards
- [ ] BET/MONITOR/AVOID/NO-EDGE readable without color alone
- [ ] Matchup: verdict above fold; methodology collapsed
- [ ] Today: full slate scannable in one scroll on 1440px
- [ ] Mobile ≤760px: nav wraps/rail; tables horizontal-scroll
- [ ] Freshness + model version visible on every data view
- [ ] No fake production stats in empty states
- [ ] Report HTML builders still drive content (mockups are design target, not a second app)

---

## 8. Open for approval

Review mockups in `docs/redesign/mockups/`. Approve to start Phase 0–1 implementation in `mlbmodel/report/`.
