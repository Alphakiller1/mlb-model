# Design Contract — MLB Model (Purple · Black Desk)

Version 2.1.0 · 2026-07-23  
**Supersedes** v2.0.0 steel-accent desk tokens.

MLBMA research boards keep their own contract. This file governs `mlb_model_app.html` and redesign mockups.

## Tokens

```css
:root {
  --bg: #07060C;
  --bg-raised: #0C0B14;
  --panel: #12101C;
  --panel-2: #1A1728;
  --line: #2A2540;
  --line-strong: #4A3F6E;
  --ink: #F4F2FA;
  --ink-2: #C8C2D8;
  --mut: #8A839E;
  --brand: #9A6BFF;
  --brand-deep: #5B2BE0;
  --brand-light: #C4B0FF;
  --v-grad: linear-gradient(135deg, #9A6BFF 0%, #5B2BE0 100%);
  --signal: #3DFF9A;   /* BET */
  --watch: #E8B84A;    /* MONITOR */
  --cut: #FF5C6A;      /* AVOID */
  --mute: #6B6680;     /* NO-EDGE */
  --gold: #E8C24A;
  --font-ui: "IBM Plex Sans", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
  --font-display: "Barlow Condensed", "IBM Plex Sans", sans-serif;
}
```

## Matchup symmetry (required)

Comparable metrics render as a **mirrored board**:

```
[ Away value ]  |  LABEL  |  [ Home value ]
```

- Hero: Away team ← → Home team with centered VS axis  
- Rows: Win%, Proj R, Fair ML, SP FIP, SP K%, OSI, wOBA, etc.  
- Factor lists: equal-width Away edges | Home edges  
- Do **not** dump one-sided “why” tables as the primary breakdown  

Shared risks / park / methodology may sit below the symmetric board.

## Rules

1. Purple + black is identity; status greens/ambers/corals stay for BET/MONITOR/AVOID only.
2. Status always = color + label text.
3. Mono for odds/probs/EV; display for titles + team names.
4. Panels: dark purple-black fills + violet hairlines — avoid heavy neon glow stacks.
5. Freshness + model version on every data view.
6. Empty / stale / error states styled, never blank.

## Status map

| State | Color |
|-------|-------|
| BET | `--signal` |
| MONITOR | `--watch` |
| AVOID | `--cut` |
| NO-EDGE | `--mute` |
