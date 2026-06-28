# Dominant Situational Trends

A situational-edge engine that surfaces the highest-signal, context-matched trends for an
upcoming MLB game and emits **(1)** structured per-trend records, **(2)** a 0–100 per-team
**Situational Edge Score**, **(3)** a flat **feature row for the predictive model**, and
**(4)** a human-readable narrative.

It is grounded *only* in the materialized MLBMA tables — every number is real and every trend
reports an honest `sample_size` and `data_backed` flag. No fabricated historical records.

## What it detects today (data-backed)

| Detector | Source table | Signal |
|---|---|---|
| `bullpen_fatigue` | `reliever_log` | recent relief pitch load / high-leverage appearances vs the league (z-scored), inherited-runner conversion |
| `form_vs_hand` | `team_l10_sp_hand` | last-10 offense (wRC+, OPS, QS-against%) vs the opposing starter's **handedness**, deviation from the league split |
| `starter_quality` | `sp_profiles` × `team_l10_sp_hand` | **interaction**: opposing starter xFIP gap × the lineup's recent form vs that hand |
| `park` | `park_factor` | game-total run environment (both lineups) |

Adding a detector = one function `(\ctx, sit) -> Trend | None` appended to
`detectors.DETECTORS`. Candidates with data already present: bullpen quality vs platoon
(`bullpen_unit` vs LHH/RHH), Statcast contact-quality splits (`batter_splits_*` Barrel%/
HardHit%/xwOBA), pitch-arsenal overlap (`pitch_mix_*`).

### Honest limits
The full "1-8 in these 9 matching games, avg 2.67 runs" historical matching needs a complete
multi-season game log with situational joins; the current `game_results` spine is thin, so
detectors report records only where a real log backs them (e.g. `form_vs_hand` W-L). The
architecture is ready to consume a fuller game log when the pipeline produces one.

## Usage

```bash
# whole slate -> structured JSON + narrative
python -m mlbmodel.trends.cli --data-dir DATA --out trends.json --narrative
# one game
python -m mlbmodel.trends.cli --data-dir DATA --game NYY@BOS --narrative
```

```python
from mlbmodel.baseball.repository import DataRepository
from mlbmodel.trends import build_situational_report, trend_features_for_game

repo = DataRepository(DATA)
edge = build_situational_report(repo, "NYY", "BOS")
print(edge.away_edge_score, edge.home_edge_score, edge.edge_lean)   # 11.0 40.0 BOS
for line in edge.narrative: print(line)

feats = trend_features_for_game(repo, "NYY", "BOS")   # flat dict for the model
```

## Structured output (per trend)

```json
{
  "trend_id": "WSN_bullpen_fatigue",
  "team": "WSN", "side": "away", "category": "bullpen_fatigue",
  "trend_description": "WSN's bullpen has thrown 84 pitches across 7 relief appearances ...",
  "situation_key": "WSN|bullpen_fatigue|w3",
  "direction": "run_boost",
  "sample_size": 7, "effect_size": 1.31, "z_score": 1.31,
  "significance": "moderate", "confidence": "medium",
  "historical_record": null, "avg_runs_scored": null, "avg_runs_allowed": null,
  "key_rate_diffs": {"recent_relief_pitches_z": 1.31, "high_lev_apps": 3, "inherited_scored_pct": 50.0},
  "mechanistic_explanation": "Heavy recent relief load thins the high-leverage corps ...",
  "betting_implications": ["BAL team total OVER (late-inning leak risk)", "..."],
  "suggested_model_feature": {"WSN_bullpen_recent_load_z": 1.31},
  "data_backed": true, "relevance": 0.9, "trend_score": 0.78
}
```

## Integrating with the main model (XGBoost / ensemble / NN)

`trend_features_for_game` returns a flat, stably-named row to **join on `game_pk` / team**
and concatenate onto your existing feature matrix:

```
situational_edge_away, situational_edge_home, situational_edge_diff
{TEAM}_l10_wrcplus_vs_{R|L}hp_z      # offense form vs the hand it faces
{TEAM}_bullpen_recent_load_z         # bullpen fatigue
{TEAM}_starter_quality_x_form        # signed starter-quality × form interaction
{away|home}_offense_trend_signal     # aggregate run-direction signal
{away|home}_bullpen_fatigue_signal
away_off_vs_home_pen_interaction     # cross interaction (your bats × their tired pen)
home_off_vs_away_pen_interaction
park_total_signal                    # game-total lean
```

Recommended use:
- **XGBoost / GBM:** append the row directly. The `*_z` and `*_interaction` terms are already
  centered/standardized, so no extra scaling; let the trees find thresholds. Start by adding
  to the **totals** and **team-total** models (where these signals are strongest), then F5/ML.
- **Ensemble:** use `situational_edge_diff` and `park_total_signal` as a thin meta-model layer
  on top of the base run-expectancy projection, or as a monotone prior nudging team totals.
- **NN:** feed the flat row as additional dense inputs; the interaction features give the net
  a head start vs. learning the bullpen×offense crossing from scratch.
- **Dynamic weighting:** `situation_key` + `trend_score` let the model down-weight low-sample
  or low-relevance trends at inference instead of hard-filtering.

Guardrails baked in (anti-overfitting): magnitude **and** sample gating before a trend is
surfaced, `significance`/`confidence` flags, recency-weighted sources (L10 / last-3-game
bullpen load), and `data_backed` so structural signals never masquerade as matched history.
Validate added features on out-of-sample slates and watch calibration (Brier/log-loss) before
trusting them in staking.
```
