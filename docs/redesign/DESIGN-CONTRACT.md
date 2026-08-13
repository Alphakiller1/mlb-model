# Design Contract — MLB Model (Purple · Black Desk)

Version 2.2.0 · 2026-07-23  
**Supersedes** v2.1.0 muddy purple-black tokens.

MLBMA research boards keep their own contract. This file governs `mlb_model_app.html` and redesign mockups.

## Tokens

```css
:root {
  /* Neutrals = graphite (no purple cast). Brand = bright violet only. */
  --bg: #0A0A0B;
  --bg-raised: #111113;
  --panel: #161618;
  --panel-2: #1E1E22;
  --line: #2C2C33;
  --line-strong: #454552;
  --ink: #F5F5F7;
  --ink-2: #B4B4BE;
  --mut: #8A8A96;
  --brand: #B794FF;
  --brand-deep: #9B6DFF;
  --brand-light: #D8C8FF;
  --v-grad: linear-gradient(135deg, #D0BAFF 0%, #B794FF 45%, #9B6DFF 100%);
  --signal: #2EE59D;   /* BET */
  --watch: #F5C14A;    /* MONITOR */
  --cut: #FF4D5E;      /* AVOID */
  --mute: #6E6E7A;     /* NO-EDGE */
  --gold: #F0C75E;
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

1. Identity = graphite surfaces + bright violet accent. Do not tint panels purple.
2. Status greens/ambers/corals stay for BET/MONITOR/AVOID only — never for brand chrome.
3. Status always = color + label text.
4. Mono for odds/probs/EV; display for titles + team names.
5. Panels are solid graphite with 1px neutral rules; violet only on active/brand accents.
6. Freshness + model version on every data view.
7. Empty / stale / error states styled, never blank.

## Status map

| State | Color |
|-------|-------|
| BET | `--signal` |
| MONITOR | `--watch` |
| AVOID | `--cut` |
| NO-EDGE | `--mute` |
