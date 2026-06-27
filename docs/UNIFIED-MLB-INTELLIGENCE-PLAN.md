# Unified MLB Betting Intelligence — Strategic Plan & Architecture

> Status: **planning only — nothing built, no existing repo modified.**
> Author: independent assessment after auditing both repos + public references.
> Unified repo (**decided**): **MLB MODEL** — git/GitHub slug `mlb-model` (no spaces allowed),
> Python package `mlbmodel`. A brand-new repo that *consumes* the two betting repos' logic;
> the mlbma-pipeline and betting-brain vault stay untouched read-only fuel.

This plan deliberately does **not** assume the proposed architecture is correct. It is
based on reading both codebases in full, plus public references in MLB analytics,
betting-market microstructure, biomechanics, arbitrage, and ML validation discipline.

Guiding constraints (yours, kept front-and-center):
- Decision-support + **paper-trading** infrastructure, **not** auto-betting.
- Transparent, testable logic over black-box complexity.
- **"No play" beats noisy confidence.** Honest-empty by default.
- No fake performance claims; be explicit about uncertainty and research risk.

---

## 1. Assessment of the current two repos

### 1.1 What I actually found (not what the READMEs claim)

Both repos live under `_github-repos/` and point at `github.com/Alphakiller1/{bet-evaluator,
sharp-money-tracker}`. **They are not two systems. They are one system that bifurcated,
with the shared engine copy-pasted into both.**

Concrete evidence:
- `bet-evaluator/backtest/` is a **vendored copy** of the sharp-money-tracker engine.
  Shared files differ by only ~2–4 lines (import paths): `analyze_sharp.py`,
  `book_intel.py`, `cross_venue.py`, `market_edge.py`, `scenarios.py`, `value_board.py`,
  `prediction_markets.py`; `db.py` and `settle_sharp.py` are **byte-identical**;
  `market_data.py` is **identical** in both.
- Two **divergent** copies of `sharp_tracker.py` (310 vs 344 lines) — already drifting.
- **Two parallel quant engines** doing the same job: `quant_analysis.py` (bet-eval, 379 LOC)
  and `quant_review.py` (sharp, 268 LOC) — both compute Brier, bootstrap, Kelly, SPRT, Wilson.
- Two schema files: identical core (teams, games, outcomes, snapshots, sharp_signals,
  prediction_market_snapshots…); bet-eval adds `mlbma_signals` + `mlbma_convergence`;
  sharp adds the board/projection surface. **~70% overlap.**
- `config.py` differs by exactly **one line** (a hardcoded Windows path).

### 1.2 What each repo does well

**bet-evaluator — the single-bet UX & the model.** Genuine assets:
- `bet_evaluator.py` (874 LOC): a clean, **transparent expected-runs model**
  (`league_runs × offense(OSI) × pitch(opp SP FIP + bullpen) × park`, regressed to mean,
  normal model on margin, blended with empirical home base rate). It is honest about being
  *a heuristic prior, not a calibrated model* — that self-awareness is a strength.
- The value layer (implied→edge→EV→fair odds→Kelly→tiers), the `REVIEW` guard on
  implausible edges, and the worded risk/variance rendering.
- A GitHub Pages site with the **model ported to JS and parity-checked** against Python.
- Vault-note output (human-readable bet history feeding calibration).
- `game_report.py`, `regression.py` (FIP–ERA luck gap / workload), `command_center.py`
  (local HTTP dashboard), `chase.py` (CLI hub).

**sharp-money-tracker — the market-edge research engine.** Genuine assets:
- `market_edge.py` (187 LOC) — **the crown jewel.** ROI-at-entry (not the efficient close),
  non-parametric bootstrap CI, **Benjamini-Hochberg FDR**, Kelly, Sharpe-analogue. It reports
  *nothing* when nothing clears the bar. This is exactly the right discipline.
- `prediction_markets.py` (434 LOC) — Kalshi ingestion (ML, F5, K-ladders), candlestick
  closing-line + outcome backfill.
- `sharp_tracker.py` — de-vig, sharp-vs-soft divergence, steam detection, observations.
- `cross_venue.py` — Kalshi vs commercial books → arb / value / thin.
- `board_analytics.py` (1185 LOC) — the deep MLB layer: pitch-mix matchup, platoon splits,
  prop projections, pitcher board, market board.
- `pitcher_model_layers.py` (484 LOC) — L14 form blend, OSI-tier skill, lineup-weighted
  projection, Savant K/BB modifier, **bullpen-hook factor, rest/workload** — the natural home
  for a fatigue/biomechanics layer.
- `PROFIT-PRIORITY.md` — an already-excellent, detailed manufactured-arb roadmap and state
  machine. This is forward design, **not yet implemented**, and is the spine of Phase 4.

### 1.3 Overlap / merge / separate / rewrite

| Component | Verdict | Why |
|---|---|---|
| Shared engine (`db`, `market_data`, `cross_venue`, `book_intel`, `scenarios`, `value_board`, `prediction_markets`, `settle_sharp`, `analyze_sharp`) | **Merge → one `core` package** | Duplicated near-verbatim in both repos. |
| `quant_analysis.py` + `quant_review.py` | **Merge → one `core/quant`** | Two engines, same statistics. |
| Two `sharp_tracker.py` | **Merge → one `core/market/sharp.py`** | Already diverging (310 vs 344). |
| Two `schema.sql` | **Merge → one canonical schema** | Union of both (keep mlbma_signals/convergence + board/projection). |
| `bet_evaluator.py` model | **Preserve → `core/baseball/expected_runs.py`** | High quality, transparent, self-aware. |
| `market_edge.py` | **Preserve (canonical) → `core/quant/edge_scan.py`** | Best-in-repo; the discipline anchor. |
| `board_analytics.py`, `pitcher_model_layers.py` | **Preserve → `core/baseball/`** | Deep domain value; just needs module boundaries + tests. |
| `bet-evaluator/backtest/` vendored copy | **Discard** | Replaced by `import core`. |
| Hardcoded Windows paths in `config.py` | **Rewrite** | Make env-driven + portable (macOS/Linux). |
| `mlbma_pipeline` (upstream CSV producer) | **Keep SEPARATE** | Independent read-only data source; don't absorb. |
| Obsidian vault (`ChaseAnalytics-Brain`) | **Keep SEPARATE** | Human knowledge store; a write target, not code. |
| SCL marketplace | **Never merge** | Unrelated product. |

**Bottom line:** merge into a **single repo with one installable `core` package** and two thin
"surfaces" (single-bet eval + market-edge research) over it. Nothing is wholesale discarded
except the duplicate copies. The model and the quant gate are both worth preserving verbatim
in spirit; the work is consolidation + boundaries + tests, not a rewrite.

### 1.4 Honest risk note on existing "findings"

The sharp README's headline numbers (e.g. *"Underdog + steam-up +47.9% ROI"*) are computed on a
**small settled sample** and have all the hallmarks of in-sample overfitting despite the FDR gate.
They must be treated as **hypotheses to be re-validated out-of-sample**, never as proven edges.
The model itself is explicitly **uncalibrated**. Both facts are load-bearing for the plan below.

---

## 2. Recommended repo architecture

### 2.1 Folder structure

```
mlb-model/
├── pyproject.toml            # single installable package; pinned deps; ruff+pytest
├── README.md  ARCHITECTURE.md  .env.example
├── mlbmodel/                  # the ONE core package (import core, not copy-paste)
│   ├── config/               # pydantic-settings: paths, anchors, book lists, keys
│   ├── sources/              # INGEST adapters — read-only boundaries
│   │   ├── odds_api.py       # The Odds API           (from market_data.py)
│   │   ├── kalshi.py         # Kalshi ML/F5/K + candles(from prediction_markets.py)
│   │   ├── polymarket.py     # NEW (PROFIT Tier-1)
│   │   ├── mlb_statsapi.py   # NEW: probables/lineups/status/weather
│   │   ├── statcast.py       # NEW: pybaseball Statcast (cached parquet)
│   │   └── pipeline_csv.py   # mlbma_pipeline CSV reader (existing boundary)
│   ├── store/                # WAREHOUSE
│   │   ├── db.py             # PostgREST client (canonical, byte-identical today)
│   │   ├── schema.sql        # unified idempotent schema
│   │   └── models.py         # typed entities (pydantic/dataclass)
│   ├── market/               # MARKET microstructure
│   │   ├── devig.py          # de-vig math (one home)
│   │   ├── sharp.py          # sharp-vs-soft, steam, divergence (merged sharp_tracker)
│   │   ├── clv.py            # CLV capture: prob-space + ROI-space
│   │   └── book_intel.py     # sharp/soft book classification
│   ├── baseball/             # MLB DOMAIN model
│   │   ├── expected_runs.py  # bet_evaluator model (preserved)
│   │   ├── pitcher.py        # regression.py + pitcher_model_layers.py
│   │   ├── matchup.py        # board_analytics matchup/pitch-mix/platoon
│   │   ├── fatigue.py        # workload/rest/bullpen-hook + (Phase 5) biomech
│   │   └── projections.py    # prop projections
│   ├── quant/                # VALIDATION + SIZING (unify the two engines)
│   │   ├── metrics.py        # Brier, log-loss, Wilson, bootstrap, SPRT
│   │   ├── calibration.py    # reliability curves, isotonic (NEW)
│   │   ├── selection.py      # Benjamini-Hochberg + Deflated Sharpe / PBO (NEW)
│   │   ├── sizing.py         # Kelly, fractional, flat-unit floor logic
│   │   └── edge_scan.py      # market_edge segment scan (canonical)
│   ├── arb/                  # ARBITRAGE + manufactured-arb
│   │   ├── pure.py           # executable arb calculator (PROFIT Phase 2)
│   │   ├── cross_venue.py    # cross-venue value (preserved)
│   │   ├── hedge.py          # hedge price math + equalized-payout staking
│   │   └── state_machine.py  # manufactured-arb FSM (PROFIT Phase 3–4)
│   ├── decision/            # DECISION engine
│   │   ├── engine.py         # PASS/WATCH/PLAY/ENTER/HEDGE/EXIT
│   │   ├── checks.py         # required source checks + data-quality gates
│   │   └── explain.py        # "why this could be wrong"
│   ├── paper/               # PAPER-TRADING (never live execution)
│   │   ├── ledger.py         # auto-migrating CSV/DB ledger (kalshi-bot pattern)
│   │   ├── positions.py      # open staged positions
│   │   └── postmortem.py     # per-candidate postmortem
│   ├── backtest/            # importers/ + settle.py + workflow_sim.py
│   ├── report/             # vault.py, game_report.py, boards.py
│   └── cli/                # ONE CLI: `mlbmodel bet|game|edge|arb|scan|paper|report|serve`
├── apps/
│   ├── command_center/      # local dashboard (evolves command_center.py)
│   └── web/                 # GitHub Pages static site (today's docs/)
├── models/registry/         # versioned artifacts + model cards (only if Phase 7 justified)
├── tests/
└── data/                    # local cache (gitignored)
```

### 2.2 Module boundaries (the dependency rule)

One-directional flow; lower layers never import upper layers:

```
sources → store → {market, baseball} → quant → decision → {arb, paper} → report → cli/apps
```

- **sources**: pure ingestion, return normalized rows, **quarantine** bad rows (parse
  confidence, team-mapping confidence, price age). No business logic.
- **store**: persistence + typed entities. The only module that talks to Supabase.
- **market / baseball**: stateless computation over stored data.
- **quant**: validation + sizing; depends on nothing above it.
- **decision**: the only place that emits a verdict; consumes everything below.
- **arb / paper**: act on decisions in *simulation only*.
- **report / cli / apps**: render. The existing `command_center.py` and the JS site become
  thin clients of `core` — no duplicated model logic.

### 2.3 Core data models (typed)

`Game, Matchup, OddsSnapshot, DevigQuote, SharpSignal, PredictionMarketSnapshot,
ModelPrediction, Candidate, Decision, Position, Outcome, Settlement, CLVRecord`.
Use pydantic/dataclasses with a `metric_version` + `model_version` stamp on every row
(both already exist in config — keep them).

### 2.4 Storage layer

- **Keep Supabase/PostgREST** as the warehouse — it works and the client is tiny stdlib.
- **Add DuckDB/SQLite** as an offline mirror for fast deterministic backtests (no network).
- **CSV ledger for paper trades** (kalshi-bot lesson: an auto-migrating CSV ledger beats
  relational overhead for the trade log and is trivially diffable).
- One canonical `schema.sql`, idempotent, applied via `mlbmodel db apply`.

### 2.5 CLI / API / dashboard

- **One CLI** (`mlbmodel …`) replacing `chase.py`'s dispatch; subcommands map to surfaces.
- **Local dashboard** stays a stdlib HTTP app initially (command_center pattern); only adopt
  Flask/FastAPI when the paper-trading panels need it.
- **GitHub Pages** static site stays, but **stop porting model logic to JS by hand.**
  Instead export a `site.json` snapshot from `core` (single source of truth) and keep a
  golden-file parity test. (The hand-ported JS model is a future drift hazard.)

### 2.6 Testing strategy

- `pytest` + `ruff`. Target the high-value, deterministic surfaces first.
- **Property tests** on odds math (american↔decimal↔implied round-trips; de-vig sums to 1).
- **Golden-file tests** for the model output and the exported `site.json` (parity).
- **Seeded determinism** for bootstrap/FDR/backtest (the code already seeds RNG).
- **Source contract tests**: each adapter validates schema + exercises the quarantine path.
- **Calibration tests**: held-out Brier/log-loss must not regress beyond a threshold.
- CI: GitHub Actions running ruff + pytest on push.

---

## 3. Betting / modeling architecture

| Layer | Source today | Plan |
|---|---|---|
| **Expected runs** | `bet_evaluator.py` | Preserve. Add: explicit park/weather, lineup-confirmed gate, optional Statcast-informed offense factor. Keep regression-to-mean. |
| **Market-implied prob** | `sharp_tracker.devig` | One `market/devig.py`; multiplicative + (add) Shin/Pinnacle-power de-vig variants for comparison. |
| **Sharp vs soft** | `sharp_tracker.py` | Sharp consensus = de-vigged blend of {Pinnacle, LowVig, BetOnline, Bookmaker, Circa}. **Sharp consensus is the PRIMARY signal; the model is a prior.** (See §5 + kalshi-bot evidence.) |
| **Line movement / steam** | `sharp_tracker`, candles | Keep open→close tracking; require multi-book agreement (`STEAM_BOOK_MIN`). |
| **CLV** | partial | First-class `market/clv.py`: capture **both** `p_close − p_used` and `decimal_used/decimal_close − 1`, on **all analyzed games**, not just placed bets. |
| **Kelly / bankroll** | `value_layer`, `_kelly` | `quant/sizing.py`: fractional Kelly **with a flat-unit floor** (kalshi-bot lesson: 1/8-Kelly on thin edges rounds below min stake → never bets). Cap per-bet exposure. |
| **Calibration** | none yet | `quant/calibration.py`: reliability curves + **isotonic** recalibration once sample allows; report Brier/log-loss by market. |
| **Backtesting** | `market_edge`, `quant_*` | Unify; add walk-forward + purged CV; **Deflated Sharpe / PBO** for strategy selection. |
| **Paper trading** | none | `paper/` ledger + positions + postmortem. |
| **Arb / manufactured-arb** | `cross_venue` + `PROFIT-PRIORITY.md` | `arb/` with the documented state machine (§5). |

**Modeling philosophy (load-bearing):** the public production reference
(`mlb-kalshi-bot`) found its ML model was *anti-calibrated on disagreement games* and gave it
**zero veto power** over the sharp-book blend. Adopt the same humility: the expected-runs model
is a **structured prior and a circuit-breaker**, the sharp-consensus + validated CLV track
record is what actually authorizes a PLAY/ENTER.

---

## 4. MLB data architecture

| Source | Role | How to consume |
|---|---|---|
| **mlbma_pipeline CSVs** | offense/pitching metrics, signals, convergence | Keep read-only boundary (`sources/pipeline_csv.py`). Long-term: have the pipeline write to the shared warehouse to drop CSV brittleness. |
| **The Odds API** | sportsbook prices, movement, best price | `sources/odds_api.py`. Keep on-demand fetch to respect free tier. Store **executable** price + age + availability (PROFIT Phase 1). |
| **Kalshi** | real-money exchange prices, F5/K ladders, candles | `sources/kalshi.py`. Store **yes/no bid+ask, spread, liquidity, volume, OI, fee** — execution data, not midpoints. |
| **Polymarket** | additional prediction-market reference | NEW `sources/polymarket.py` (MLB markets where they exist). |
| **MLB Stats API** | probable pitchers, lineups, status, weather | NEW `sources/mlb_statsapi.py`. **Required source check** before confidence (see §5). |
| **Statcast / pybaseball** | pitcher/batter quality, matchup features | NEW `sources/statcast.py` via `pybaseball` (cache to parquet; respect Savant 30k-row limits). Use to *inform/filter*, not to manufacture signals. |
| **Weather / lineups / injuries / bullpen / workload** | context + false-positive filter | Per PROFIT-PRIORITY: these **explain or filter** movement, they do not create arb signals. Bullpen state + workload already partly modeled in `pitcher_model_layers.py`. |
| **Biomechanics** | fatigue/injury context | See §5.5 + Phase 5; **OpenBiomechanics** as the only credible open dataset. |

**Data-quality contract (every source emits):** source, endpoint/URL, fetch time, event id,
normalized game key, market type, selection, price, line, price age, parse confidence, warning.
**Quarantine** rows on ambiguous team/market mapping, missing timestamp, implausible gap, or
structure change. (This is straight from `PROFIT-PRIORITY.md` and is correct — formalize it.)

---

## 5. Decision engine design

### 5.1 States

```
PASS → WATCH → PLAY                         (single-bet value track)
WATCHLIST → ENTRY_CANDIDATE → ENTERED → HEDGE_AVAILABLE → HEDGED
                                  ├→ PARTIAL_HEDGED
                                  ├→ HOLD          (positive CLV + signal valid, no hedge yet)
                                  ├→ EXIT          (signal failed / stop-loss / reversal)
                                  └→ EXPIRED       (game started / market closed)
```

`decision/engine.py` emits a typed `Decision{action, confidence, size, rationale,
required_checks_passed, why_this_could_be_wrong, time_sensitivity}`.

### 5.2 Required source checks before *any* confidence (the gate stack)

Ordered, each logged with pass/fail + reason (kalshi-bot `daily_stats.csv` pattern):

1. **Probable pitcher confirmed** (MLB StatsAPI) — else cap at WATCH.
2. **Lineup posted** for totals/team-totals/props — else WATCH.
3. **Odds snapshot fresh** (< N min) and **price still available**.
4. **Sharp consensus exists** (≥2 sharp books de-vigged).
5. **Kalshi spread/liquidity adequate** for the intended (paper) size.
6. **No implausible edge/gap** — circuit-breaker (`IMPLAUSIBLE_EDGE`, `SHARP_DIVERGENCE_MAX`).
7. **Park + weather loaded** for any totals decision.

Fail any required check → **the system cannot upgrade past WATCH.** Honest-empty default = PASS.

### 5.3 What authorizes each action

- **PLAY** (single bet): sharp consensus agrees with the model edge **and** the matching
  historical segment is FDR-surviving with positive ROI lower bound **and** all required
  checks pass. Size by fractional-Kelly-with-floor.
- **ENTER** (manufactured arb): the `PROFIT-PRIORITY` entry rule — dog at open < 0.45,
  movement ≥ 0.02 toward side, sharp divergence ≥ 0.02, a slow venue still offers the old
  price, a plausible hedge path exists, modeled downside within stake limits.
- **HEDGE / PARTIAL_HEDGE / EXIT**: per the documented hedge math
  (`entry_cost + hedge_cost + fees + slippage < 1`), thresholds in PROFIT-PRIORITY §4.

### 5.4 "Why this could be wrong" (mandatory on every decision)

Every Decision enumerates its **weakest assumption**, e.g.: small settled sample; single sharp
book driving divergence; stale price on recheck; model uncalibrated for this market; early-season
metric noise; thin Kalshi liquidity; move already fully occurred. This is generated, not optional.

### 5.5 Avoiding false confidence

- **Honest-empty**: report nothing rather than chase minute edges (already the `market_edge`
  ethos — make it the global default).
- **Never pool markets**: ML / runline / totals / F5 / props graded in separate buckets
  (PROFIT-PRIORITY is explicit; the literature backs it).
- **Model is a prior, not a driver** (kalshi-bot evidence; §3).
- **Segment must survive FDR** before it can raise a candidate's grade.
- **Per-candidate logging** whether entered or not → feeds the learning loop + postmortem.

---

## 6. Validation & research plan

- **Backtest methodology**: settle vs final outcomes; ROI **at entry price**, not close;
  simulate the **full staged workflow** (entry→hedge availability→lock/hold), reporting the
  PROFIT-PRIORITY metric set, primary = **profit per bankroll-hour**.
- **Out-of-sample**: walk-forward + **Combinatorial Purged CV (CPCV)**; leakage prevention
  (rolling stats for game *i* use only games `0..i−1` — the kalshi-bot discipline).
- **Calibration**: reliability curves; **Brier score + log loss** per market; isotonic
  recalibration when sample supports it.
- **Uncertainty**: non-parametric **bootstrap CIs** on ROI (already in `market_edge`).
- **False-discovery control**: **Benjamini-Hochberg** for the segment scan (already present)
  + **Deflated Sharpe Ratio / Probability of Backtest Overfitting** for *strategy selection*
  across the many segments tried (Bailey–López de Prado). This is the missing piece that
  guards the headline "findings" against selection bias.
- **CLV & ROI tracking**: capture on **all analyzed games**; CLV is the leading indicator,
  realized ROI the lagging one.
- **Postmortem workflow**: every candidate → did the move happen? did the hedge appear? was
  entry price good? was the edge real or stale? what was the optimal action? Persist it.

---

## 7. Implementation roadmap

- **Phase 0 — Inspection & audit** *(this document)*. Deliverable: agreed merge map + schema diff.
- **Phase 1 — Scaffold & de-dup.** New repo `mlb-model`; create `mlbmodel` package; move shared
  engine in **once**; delete the vendored `backtest/` copy; unify the two quant engines and the
  two `sharp_tracker.py`; unify `schema.sql`; make `config` env-driven/portable; add
  pyproject/ruff/pytest/CI. **No behavior change** — pure consolidation, with parity tests.
- **Phase 2 — Merge core logic + surfaces.** Wire the single-bet eval CLI and market-edge scan
  to `core`; the dashboard + GitHub Pages become thin clients; one CLI.
- **Phase 3 — Paper-trading system.** `paper/` ledger (auto-migrating CSV), positions,
  per-candidate logging, postmortem; CLV capture on all analyzed games.
- **Phase 4 — Advanced market engine.** Executable-arb calculator (`arb/pure.py`),
  manufactured-arb state machine, hedge math, workflow backtest, Polymarket source, alerting
  (console → dashboard → Discord; SMS only for A-grade/lock).
- **Phase 5 — Biomechanics / fatigue layer.** `baseball/fatigue.py`: formalize rest/workload +
  bullpen-hook; integrate **OpenBiomechanics**-derived fatigue/injury-risk *context features*
  (license-respecting, used as a **filter/explainer**, not a standalone signal).
- **Phase 6 — Dashboard / reporting.** The four PROFIT-PRIORITY panels (pure arbs, manufactured
  candidates, open positions, postmortem); richer boards.
- **Phase 7 — Trained model / registry — *only if justified*.** Add a model **only** if it beats
  the sharp-blend baseline out-of-sample on CLV. If added: `models/registry/` with versioned
  artifacts + **model cards** answering the five MLOps questions (code commit, data version+hash,
  hyperparameters, metrics, environment). Default to MLflow-style tracking; the model stays a
  **fallback/circuit-breaker**, never the driver.

---

## 8. Prompts for future Claude / Codex sessions

Each is self-contained, names the files it touches, and states verification.

**Prompt 1 — Scaffold the unified repo (Phase 1a).**
> Create `mlb-model/` with `pyproject.toml` (package `mlbmodel`, deps: pandas, requests; dev:
> pytest, ruff), `README`, `ARCHITECTURE.md`, `.env.example`, and the empty `mlbmodel/` subpackage
> tree from §2.1. Add a GitHub Actions workflow running ruff + pytest. **Do not move logic yet.**
> Verify: `pip install -e .` succeeds; `ruff check` and `pytest` (0 tests) pass.

**Prompt 2 — De-duplicate the shared engine (Phase 1b).**
> Move `db.py`, `market_data.py`, `cross_venue.py`, `book_intel.py`, `scenarios.py`,
> `value_board.py`, `prediction_markets.py`, `settle_sharp.py`, `analyze_sharp.py` into the
> matching `mlbmodel/` modules **once**, fixing imports to absolute `mlbmodel.*`. Reconcile the two
> `sharp_tracker.py` into `mlbmodel/market/sharp.py` (diff them; keep the superset; note any
> behavior change). Verify: import-smoke test for every module; a golden test that de-vig of a
> known odds set sums to ~1.0; round-trip property test for the odds-math helpers.

**Prompt 3 — Unify the quant engine (Phase 1c).**
> Merge `quant_analysis.py` + `quant_review.py` into `mlbmodel/quant/{metrics,sizing,
> edge_scan}.py`; make `market_edge.scan` the canonical segment scanner. Add
> `quant/selection.py` with Benjamini-Hochberg (move existing) **and** a Deflated-Sharpe / PBO
> implementation. Verify: seeded reproducibility test (same input → same CI/FDR); unit tests for
> Wilson, bootstrap CI coverage, Kelly edge cases (b≤0, prob≤0), BH monotonicity.

**Prompt 4 — Port the model + surfaces onto core (Phase 2).**
> Move `bet_evaluator.py` → `mlbmodel/baseball/expected_runs.py` and re-expose the single-bet CLI
> via `mlbmodel/cli`. Make `command_center.py` and `export_web_data.py` import from `core` (no
> duplicated math). Verify: a golden-file test pinning the model output for a fixed fixture game;
> a parity test that the exported `site.json` matches the Python model within tolerance.

**Prompt 5 — Paper-trading ledger + CLV (Phase 3).**
> Implement `mlbmodel/paper/{ledger,positions,postmortem}.py` and `mlbmodel/market/clv.py`. Ledger
> = auto-migrating CSV (24-col style), one row per candidate with rejection reason. Capture CLV in
> both probability- and ROI-space for **all analyzed games**. Verify: round-trip ledger
> read/write; CLV math unit tests; a replay test over a captured slate that produces a postmortem.

**Prompt 6 — Decision engine + gate stack (Phase 2/3 bridge).**
> Implement `mlbmodel/decision/{engine,checks,explain}.py` emitting the typed `Decision` from §5.
> Wire the seven required source checks; default to PASS/honest-empty; generate the
> "why-this-could-be-wrong" block. Add `sources/mlb_statsapi.py` for probable-pitcher/lineup
> checks. Verify: table-driven tests mapping (inputs → expected action) including every gate-fail
> path; assert no decision exceeds WATCH when a required check fails.

**Prompt 7 — Executable arb + manufactured-arb FSM (Phase 4).**
> Implement `mlbmodel/arb/{pure,hedge,state_machine}.py` from `PROFIT-PRIORITY.md` §2–4. Include
> the fee/slippage model, equalized-payout staking, and the WATCHLIST→…→HEDGED state machine with
> per-state logging. Verify: hedge-lock unit tests (`entry+hedge+fees+slippage<1`); a simulated
> staged-workflow backtest reporting profit-per-bankroll-hour on a fixture.

**Prompt 8 — Statcast + fatigue/biomechanics context (Phase 5).**
> Add `sources/statcast.py` (pybaseball, cached parquet) and `baseball/fatigue.py` formalizing
> rest/workload + bullpen-hook; integrate OpenBiomechanics-derived fatigue context as **filter
> features only**, with license note. Verify: cache-hit test (no network on 2nd call); fatigue
> features bounded/clamped; a guard test that biomech features never *create* a PLAY on their own.

---

## Appendix — public references that shaped this plan

- **Production MLB-Kalshi bot** (sharp-blend primary, ML as fallback/circuit-breaker, dual CLV,
  flat-unit-over-Kelly, per-decision diagnostics) — github.com/mmoore07129/mlb-kalshi-bot
- **Cross-venue arb scanners** (Kalshi/Polymarket) — ImMike/polymarket-arbitrage,
  AlexM800/poly-kalshi-arb, realfishsam/prediction-market-arbitrage-bot, aarora4/Awesome-Prediction-Market-Tools
- **MLB data tooling** — jldbc/pybaseball (Statcast/FanGraphs/BBRef); MLB Stats API
- **Biomechanics** — drivelineresearch/openbiomechanics (100 pitchers / 411 pitches, C3D + processed)
- **Validation discipline** — Bailey & López de Prado, *Deflated Sharpe Ratio* and *Probability of
  Backtest Overfitting*; CPCV; isotonic calibration; Brier/log-loss
- **Betting-market theory** (already cited well in PROFIT-PRIORITY): Franck/Verbeek/Nuesch on
  inefficiency removal; favorite-longshot bias (Newall & Cortis; Paul & Weinbach); Wolfers &
  Zitzewitz prediction markets; CLV efficiency studies
- **Model/data discipline** — MLflow model registry + DVC data versioning (the five MLOps questions)

---

## 9. Scope lock + the metric & logic contract (pipeline + betting-brain as read-only fuel)

**Refined scope (confirmed):** the only repos that change are **`sharp-money-tracker` + `bet-evaluator`**,
which merge into **one unified model/engine**. The **mlbma-pipeline** and the **betting-brain vault
(ChaseAnalytics-Brain)** are **read-only fuel** — we *consume their metrics and embedded logic* to
drive the model and research; we do **not** modify or absorb them. This sharpens, not changes, the
architecture above: the unified model's job is **consume → prior → market → calibrate → decide**, not
re-deriving baseball metrics the pipeline already produces.

> Note: the vault and pipeline are not on this Mac (config points at Windows paths). The contract
> below is reconstructed from the code's `load(...)` calls and the committed dashboard exports
> (`bet-evaluator/docs/data/site.json`, `sharp-money-tracker/docs/data.json`). Confirm column names
> against the live pipeline before wiring.

### 9.1 The pipeline is the feature store (24 metric CSVs). What drives what:

| Pipeline CSV | Metrics it supplies | Drives in the unified model |
|---|---|---|
| `today_matchups.csv` | **OSI** (offense strength index), **FIP**, **HR9**, **K%**, SP names/hands | Expected-runs prior (`offense_factor`, `pitch_factor`) — the core model inputs |
| `team_profiles.csv` | `bullpen_era`, `bullpen_ir_scored_pct`, `window_direction`, `avg_ip_per_start`, `f5_win_pct`, `blown_save` | Bullpen run-prevention factor, F5 model, risk layer |
| `sp_l14.csv`, `sp_metric_splits.csv`, `sp_gamelog.csv`, `sp_standard.csv`, `sp_profiles.csv` | pitcher form, splits, game logs | `pitcher_model_layers.py` → L14 blend, **skill_era, luck, matchup_adj** (already computed!) |
| `savant_team_leaderboard.csv` | Statcast team K/BB quality | Savant K/BB modifier (a Statcast hook **already wired** — no new pybaseball needed for this) |
| `team_l10_sp_hand.csv` | team last-10 vs SP hand | platoon / hand-split adjustment |
| `metrics_pals.csv`, `metrics_oor.csv` | **PALS** + **OOR** pipeline composite metrics | snapshot features (currently imported in `import_snapshots.py`) |
| `signals_today.csv`, `signals_convergence.csv` | **the pipeline's own signal engine**: fired signals w/ `magnitude`, `direction`, `bet_angle`, `verdict_text`; convergence plays | **Embedded betting logic — consume as decision features, do NOT reinvent** |
| `today_weather.csv`, `today_lineups.csv` | weather, confirmed lineups | totals context + required-source-check gate (§5.2) |
| `game_results.csv`, `team_results.csv` | settled outcomes | **live-refreshes the model anchors** (home_winp, league_runs, SDs) + calibration corpus |
| `player_registry.csv`, `batter_profiles.csv` | id↔name resolution, batter context | name resolution, lineup-weighted projections |

**Key consequence for the merge:** the pipeline already produces the expensive parts — OSI, FIP,
bullpen factors, a Statcast hook, **and a per-pitcher skill_era/luck/matchup_adj layer**, **and a
fired-signal + convergence engine**. The unified model should treat these as **input features**, not
recompute them. This is why a new heavy ML model is *not* the priority (§7 Phase 7 stays optional).

### 9.2 The betting-brain vault is the logic spec (referenced in code, read-only)

The code points at these vault notes as the **source of truth for the logic** — mine them to keep the
unified model faithful, but never write to them except the existing bet-history output:
- `06-Betting-Logic/Win-Probability-Model` — the expected-runs model's documented calibration loop.
- `06-Betting-Logic/Unit-Sizing` — the `CONFIDENCE_TIERS` → unit map.
- `06-Betting-Logic/Market-Edge-Engine` — the `market_edge` quant-gate rationale.
- `07-Workflows/Sharp-Tools-How-To` — operating procedure.
- `13-Bet-History/` — **write target** for eval notes (the human calibration corpus). Keep writing here.

### 9.3 The unified model's data flow (everything above, in order)

```
mlbma-pipeline CSVs ──┐                         (read-only feature store)
betting-brain logic ──┤
                      ▼
        [baseball] expected-runs PRIOR  ← OSI·FIP·park·bullpen, regressed   (bet_evaluator)
                      +  pitcher skill_era/luck/matchup_adj                  (pitcher_model_layers)
                      +  pipeline fired-signals / convergence as features    (signals_*)
                      ▼
        [market]  de-vig sharp consensus · steam · CLV                       (sharp_tracker + odds/kalshi)
                      ▼
        [quant]   segment ROI-at-entry · bootstrap CI · BH-FDR · (+DSR/PBO)  (market_edge unified)
                      +  calibration: open/close Brier + price-bucket reliability  (already exported!)
                      ▼
        [decision] PASS/WATCH/PLAY/ENTER/HEDGE/EXIT  + "why this could be wrong"
                      ▼
        [paper]   ledger · positions · postmortem  →  back to vault 13-Bet-History
```

### 9.4 Research is *already half-instrumented* — use it

The committed exports show the calibration scaffold the research plan (§6) needs already runs:
- `open_vs_close`: **open Brier 0.251 vs close Brier 0.243** (n=491) — empirical proof the close is
  better-calibrated, i.e. *act at the open*. This is the data backbone for CLV research.
- `pm_calibration`: Kalshi **price-bucket → actual-win-rate** reliability table (the isotonic input).
- `market_edge` / `tradeable`: the live segment scan (e.g. `dog + steam up` ROI +47.9%, **n=56**).
  **n=56 is exactly the overfitting exposure flagged in §1.4** — this is the segment that most needs
  Deflated-Sharpe / PBO and out-of-sample re-validation before it earns any confidence.

**Net:** the merge does not start from zero on research — it inherits a pipeline feature store, a
documented logic spec, and a running calibration export. The unification work is to make the two
betting repos a single, faithful **consumer + decision layer** over that fuel.

> **Project boundary:** MLB MODEL (+ bet-evaluator, sharp-money-tracker, the mlbma pipeline, and the
> betting-brain vault) is a **separate project from SCL** (the Sports Capper League marketplace).
> None of SCL's conventions/CLAUDE.md apply here.

---

## 10. Data acquisition — new APIs & whether Scrapling helps

What's already wired: **The Odds API** (us+eu so Pinnacle is in the sharp blend), **Kalshi**
(ML/F5/K + candlesticks), and the **mlbma pipeline** feature store (OSI/FIP/bullpen/Savant
leaderboard/signals). The question is what *new* acquisition is worth adding, and where the
**Scrapling** scraping library earns its keep.

### 10.1 New APIs worth adding (ranked by value ÷ effort)

| Priority | API | Cost | Adds | Phase |
|---|---|---|---|---|
| **#1** | **MLB Stats API** (`statsapi.mlb.com`) | **Free, official, no key** | Confirmed **probable pitchers**, **posted lineups**, **scratches**, game status, venue/roof, postponements | **Now / Phase 2–3** |
| **#2** | **The Odds API — historical/intraday** tier | Paid ($) | Intraday line-movement history needed to backtest the **manufactured-arb workflow** ("would we have entered → did a hedge appear") | Phase 4 (research) |
| **#3** | **Polymarket** (Gamma / CLOB) | Free | 2nd prediction-market venue for **cross-venue arb** breadth | Phase 4 (arb only) |
| **#4** | **pybaseball / Baseball Savant** direct | Free | Pitch-level Statcast for deeper fatigue/biomech features (beyond the pipeline's team leaderboard) | Phase 5 |
| low | Weather API (Open-Meteo free) | Free | First-pitch-time wind/temp/roof refresh | only if pipeline `today_weather` is stale |
| ✗ | Sportradar / OddsJam / Unabated | $$$ | Marginal for a paper-trading research tool | not recommended |

**The #1 is load-bearing:** the decision-gate checks in §5.2 (*probable-pitcher-confirmed*,
*lineup-posted*) **require** this data, and it enables the catalyst alerts in PROFIT-PRIORITY
(pitcher scratched, star resting). It is free and official — add it first. Everything else *core*
is already API-covered, which is why no heavy new ingestion is needed for Phases 1–3.

#### 10.1a Verified against all projects (don't re-integrate what exists)

Grepped every repo under `Projects/` (code + deps, excluding node_modules):

- **The Odds API — ALREADY WIRED**, not new. Full client in `market_data.py` (both betting repos),
  `config.ODDS_API_BASE/KEY`, `import_odds.py`, `sharp_tracker.py`. (Also independently present in the
  separate `scl-marketplace` project.) → #2 above is an **upgrade to the existing client** (historical
  tier), not a new integration.
- **Kalshi — ALREADY WIRED**: `prediction_markets.py` → `KALSHI_BASE=api.elections.kalshi.com/trade-api/v2`.
- **MLB Stats API — no direct client**, but probables/lineups/**player IDs** already arrive via the
  pipeline CSVs (`board_analytics.py:145` consumes MLB Stats API IDs). The direct add buys **real-time**
  lineup/scratch confirmation the daily CSV can't give — still the #1 add, but framed as an enhancement.
- **Polymarket — absent** (only a roadmap mention + a code comment noting MLB coverage is sparse). New.
- **pybaseball — not a dependency** (neither `requirements.txt`; no import). Statcast/FanGraphs data
  arrives via the pipeline's `savant_team_leaderboard.csv` / `sp_standard`. New only if Phase 5 needs
  pitch-level pulls.
- **Weather — no direct API**; pipeline `today_weather.csv` covers it.

Both repos' deps are minimal (`pandas`, `requests`, `psycopg2-binary`, `tzdata`) — no ML/scraping/SDKs —
so a new MLB Stats API client is trivial (stdlib `urllib`, mirroring the Kalshi client).

### 10.2 Scrapling — would it make things easier?

[Scrapling](https://github.com/D4Vinci/Scrapling) is an adaptive, high-performance scraping library:
self-healing CSS/XPath selectors that relocate after page changes, anti-bot bypass (Cloudflare
Turnstile), Playwright dynamic rendering, ~1700× faster parsing than BeautifulSoup, and an optional
MCP server. **Honest verdict: useful for a narrow, secondary slice — not foundational.**

- **Where it does NOT help (use the API instead):** MLB Stats API, The Odds API, Kalshi, Polymarket,
  weather, Statcast. Scraping these would add fragility + ToS risk for zero benefit. Your own
  `PROFIT-PRIORITY.md` already says "use official APIs first" — that rule is correct; keep it.
- **Where it genuinely helps (no clean API exists, and the data is real context):**
  - **Public betting % / money splits / steam** (Action Network, Covers, VSIN) — Tier-2 "is the move
    real or just public?" filters.
  - **Lineup-scratch / injury-news catalysts** (Rotowire, RotoGrinders, beat-writer pages) — Tier-3/4.
  - **OddsPortal-style historical open/close** if you don't buy The Odds API historical tier.
  These targets are JS-heavy and bot-protected — exactly Scrapling's strength, and better than
  hand-rolling `requests`+BeautifulSoup.
- **Caveats (important for this project's constraints):**
  1. "Undetectable / anti-bot bypass" = **ToS and legal risk**. For a decision-support / paper-trading
     tool, scrape only **public, permitted** data; respect `robots.txt` + rate limits; **never** use it
     to evade sportsbook account protections or paywalls.
  2. Scraped inputs are **Tier-2/3 (filters/explainers), not core signals** — per §5.5 they must never
     *manufacture* confidence on their own. Treat as enrichment behind the §4 quarantine/parse-confidence
     contract.
  3. Maintenance: even self-healing selectors break; budget for it.

**Recommendation:**
- **Phase 1–3:** add **MLB Stats API** (free, required by the gates). No scraping yet — core is API-covered.
- **Phase 4:** add **The Odds API historical** (paid) + **Polymarket** (free); introduce **Scrapling
  *only* for the no-API context feeds** (betting %, splits, catalysts), ToS-respecting, behind the
  quarantine contract. (Its MCP server could also plug into Claude Code as a scraping tool if useful.)
- **Phase 5:** **pybaseball** direct if biomech/fatigue needs pitch-level Statcast.
