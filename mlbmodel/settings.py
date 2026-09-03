"""Runtime settings owned by the unified MLB Model."""
from __future__ import annotations

import os
from pathlib import Path

from mlbmodel.genesis.logic_matrix import (
    CONVERGENCE_THRESHOLD,
    LINEAGE_VERSION,
    MODEL_SENSITIVITIES,
)

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    # utf-8-sig strips a leading BOM so Windows Notepad saves don't turn the
    # first key into "\ufeffODDS_API_KEY" (which silently leaves ODDS unset).
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

_DEPLOYMENT_DATA = ROOT / "deployment_data"


def default_data_dir() -> Path:
    """Prefer a directory that actually has a slate; local `data/` is often odds-only."""
    env = os.getenv("MLBMA_DATA_DIR")
    if env:
        return Path(env)
    primary = ROOT / "data"
    if (primary / "today_matchups.csv").exists():
        return primary
    if (_DEPLOYMENT_DATA / "today_matchups.csv").exists():
        return _DEPLOYMENT_DATA
    return primary


DATA_DIR = default_data_dir()
CACHE_DIR = Path(os.getenv("MLBMODEL_CACHE_DIR", DATA_DIR))

MODEL_VERSION = os.getenv("BET_MODEL_VERSION", "v3-genesis-202607")
METRIC_VERSION = os.getenv("MLBMA_METRIC_VERSION", LINEAGE_VERSION)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
# Dedicated write key (service_role / sb_secret_...). Required to INSERT model_leans — the
# anon/publishable read key can SELECT but RLS blocks writes. Falls back to SUPABASE_KEY.
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_SPORT_KEY = "baseball_mlb"
ODDS_REGIONS = os.getenv("ODDS_REGIONS", "us,eu")
ODDS_PROP_REGIONS = os.getenv("ODDS_PROP_REGIONS", "us")
ODDS_GAME_MARKETS = "h2h,spreads,totals"
# Floor below which we refuse to spend Odds API credits. The monthly quota is shared by the
# scheduled deploy and every manual refresh, so a nearly-drained key would otherwise get
# finished off by a local run and empty the live board. 0 disables the guard.
try:
    ODDS_API_MIN_REMAINING = int(os.getenv("ODDS_API_MIN_REMAINING", "0") or 0)
except ValueError:
    ODDS_API_MIN_REMAINING = 0
# First-5-innings markets are "additional markets": only the per-event odds endpoint returns
# them, so they cost ~1 extra API call PER GAME per fetch. That multiplies Odds API credit
# usage and can exhaust the quota (which would empty the WHOLE board), so live F5 pricing is
# OFF by default — set ODDS_F5_ENABLED=1 to turn it on when there's credit headroom. With it
# off, F5 still appears everywhere as a graded model market (just at model fair value).
ODDS_F5_MARKETS = os.getenv("ODDS_F5_MARKETS", "h2h_1st_5_innings,totals_1st_5_innings")
ODDS_F5_ENABLED = os.getenv("ODDS_F5_ENABLED", "0") not in {"0", "", "false", "False"}
SHARP_BOOKS = {"pinnacle", "betonlineag", "lowvig", "bookmaker", "circasports"}

MLBMA_SHEET_ID = (
    os.getenv("MLBMA_SHEET_ID")
    or "1D28pC1lqMbsCcTBP67WhJPzYHn2UdtveMEv6RsUSczk"
)
MLBMA_HUB_URL = (
    os.getenv("MLBMA_HUB_URL")
    or "https://mvxjcfriirguhjujurhf.supabase.co"
).rstrip("/")
MLBMA_HUB_KEY = (
    os.getenv("MLBMA_HUB_KEY")
    or "sb_publishable_o5EJOhmdxbUPLMHZGKpv1g_Jk8by5v2"
)

# ── Season anchors — CALIBRATED, not assumed ────────────────────────────────
# Measured 2026-08-12 from 1,597 completed games in BettingBrain.game_outcomes.
# Prior values (2025 carry-over) shown for audit; re-run the calibration query in
# docs/CALIBRATION.md at season end rather than hand-editing these.
#
#   constant              prior    measured 2026
#   LEAGUE_RUNS_PER_TEAM   4.58       4.5297
#   HOME_BASE_WINP         0.540      0.5335
#   TOTAL_RUNS_SD          4.79       4.7549
#   TEAM_RUNS_SD           3.33       3.3066
#   MARGIN_SD              4.40       4.5969   <-- understated by 0.20
#   HFA_RUNS               0.15       0.1703
#
# MARGIN_SD was the material miss. It divides the expected margin when converting
# to a win probability, so understating it pushed every probability too far from
# 0.5 — i.e. the model was systematically OVERCONFIDENT, and manufactured edge
# against the market on exactly the games where it was most sure.
LEAGUE_RUNS_PER_TEAM = 4.5297
LEAGUE_FIP = 4.20          # NOT recalibrated — needs a pitcher-weighted aggregate
HOME_BASE_WINP = 0.5335
AWAY_BASE_WINP = 0.4665
TOTAL_RUNS_SD = 4.7549
TEAM_RUNS_SD = 3.3066
MARGIN_SD = 4.5969
HFA_RUNS = 0.1703
OSI_RUN_SENSITIVITY = MODEL_SENSITIVITIES["osi_run"]
SP_FIP_WEIGHT = MODEL_SENSITIVITIES["sp_fip_weight"]
REGRESSION_TO_MEAN = MODEL_SENSITIVITIES["regression_to_mean"]
# Measured 2026-08-13 across all 30 bullpens (7,934 appearances), appearance-weighted.
#
# This is NOT a league ERA — it is the mean of the exact composite the model builds from
# each pen (0.55*overall_FIP + 0.25*high_leverage_FIP + 0.20*venue_FIP), and it serves as
# BOTH the regression target in `bullpen_features` and the divisor in `staff_factor`. Those
# two must agree or the factor is biased by construction.
#
#   prior 4.05  ->  measured 3.5495
#
# At 4.05 every bullpen in the league graded ~12% better than "average", so `staff_factor`
# suppressed runs on every game: modelled totals averaged 7.79 against a market mean of
# 8.52. The starter anchor below was checked the same way and is sound (starts-weighted
# mean season_skill = 4.2235 across 306 starters, vs LEAGUE_FIP 4.20), so the bullpen
# denominator was the whole of the gap. Re-measure at season end; do not hand-edit.
LEAGUE_BULLPEN_ERA = 3.5495
BULLPEN_IR_SENSITIVITY = MODEL_SENSITIVITIES["bullpen_ir"]
OFF_FACTOR_CLIP = (0.55, 1.60)
PITCH_FACTOR_CLIP = (0.60, 1.70)
# Incremental team-total impact of the pitch-mix (arsenal-vs-lineup) response. Kept tight
# because this signal partially overlaps the lineup/platoon value already applied, and it is
# additionally regressed toward the mean before use.
ARSENAL_FACTOR_CLIP = (0.95, 1.05)
IMPLAUSIBLE_EDGE = 0.15
# Incremental MLBMA metric layers (regressed; applied after primary OSI step)
METRIC_RUN_SENSITIVITY = MODEL_SENSITIVITIES["metric_run"]
PALS_BLEND_WEIGHT = MODEL_SENSITIVITIES["pals_blend"]
PROJ_OSI_BLEND_WEIGHT = MODEL_SENSITIVITIES["proj_osi_blend"]
OFF_DEPTH_CLIP = MODEL_SENSITIVITIES["off_depth_clip"]
ALLOWED_METRIC_SENSITIVITY = MODEL_SENSITIVITIES["allowed_metric"]
TREND_RUN_SENSITIVITY = MODEL_SENSITIVITIES["trend_run"]
TREND_PEN_SENSITIVITY = MODEL_SENSITIVITIES["trend_pen"]
TREND_INTERACTION_SENSITIVITY = MODEL_SENSITIVITIES["trend_interaction"]
TREND_PARK_SENSITIVITY = MODEL_SENSITIVITIES["trend_park"]
TREND_FACTOR_CLIP = MODEL_SENSITIVITIES["trend_clip"]
LEAGUE_TEAM_ERA = 4.30
DEFENSE_FACTOR_CLIP = (0.96, 1.04)
SIGNAL_EDGE_SCALE = MODEL_SENSITIVITIES["signal_edge_scale"]
SIGNAL_EDGE_CAP = MODEL_SENSITIVITIES["signal_edge_cap"]
SIGNAL_HIGH_CONVERGENCE = CONVERGENCE_THRESHOLD

# ── Park factors — MEASURED and shrunk, not assumed ─────────────────────────
# Each park's factor is its home total divided by the same club's road total (which
# controls for the team's own scoring level), shrunk toward 1.0 with a 180-game prior.
#
# The prior weight was chosen by holdout, not taste. Fitting on the first 70% of 2026 by
# date and scoring the rest:
#
#   no park factor at all          RMSE 4.4209
#   previous hardcoded table       RMSE 4.4355   <-- WORSE than applying nothing
#   measured, shrunk (prior 180)   RMSE 4.4146
#
# The previous table was not merely imprecise, it was anti-predictive: it correlated 0.200
# with measured 2026 park behaviour and got several parks backwards (PIT listed 0.95 and
# measured 1.24; TEX listed 1.08 and measured 0.87; LAD listed 1.01 and measured 0.84).
#
# Each park is now shrunk by its OWN reliability (empirical Bayes) rather than by one
# global prior, which is both better on holdout (4.4129 vs 4.4146, same train/test split)
# and better behaved for the outliers.
#
# The measurement that matters most here is the between-park variance: tau^2 = 0.0014,
# about 3.7% in log space. The RAW 2026 spread runs from COL 1.167 to LAD 0.835, but once
# the sampling noise of ~60 home games is removed, almost all of that spread is noise —
# which is why every park lands within 0.96–1.05 no matter which shrinkage method is used.
#
# KNOWN LIMITATION, and do not "fix" it by inflating these numbers: Coors is a genuine
# ~1.30 park over multi-season samples, and one season cannot recover that. The cost is
# visible against the market — on 2026-08-31 the model priced BAL@COL at 8.80 against a
# market total of 11.00, the single largest disagreement on the slate. The market is
# pricing decades of park history that this table does not have. The real fix is a
# multi-season park source, NOT a bigger single-season estimate. Re-measure with
# scripts/fit_park_factors.py rather than hand-editing.
PARK_FACTORS = {
    "PIT": 1.053, "ATH": 1.047, "COL": 1.043, "KCR": 1.023, "NYY": 1.022,
    "ATL": 1.019, "WSN": 1.016, "SFG": 1.012, "PHI": 1.011, "CIN": 1.006,
    "NYM": 1.004, "ARI": 1.003, "HOU": 1.003, "CLE": 1.003, "BOS": 0.996,
    "TOR": 0.996, "DET": 0.994, "SEA": 0.993, "MIL": 0.992, "STL": 0.990,
    "MIA": 0.988, "CHC": 0.984, "TBR": 0.982, "CHW": 0.982, "MIN": 0.969,
    "LAA": 0.966, "TEX": 0.966, "SDP": 0.966, "BAL": 0.965, "LAD": 0.963,
}

TEAM_NAME_TO_ABBR = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
    "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Athletics": "ATH", "Oakland Athletics": "ATH",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDP",
    "San Francisco Giants": "SFG", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TBR", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}


def team_abbr(name: str) -> str:
    value = str(name).strip()
    if value.upper() in PARK_FACTORS:
        return value.upper()
    return TEAM_NAME_TO_ABBR.get(value, value.upper()[:3])


def supabase_read_key() -> str:
    return SUPABASE_PUBLISHABLE_KEY or SUPABASE_KEY


def supabase_write_key() -> str:
    """Key used for warehouse writes (model_leans). Prefers the dedicated service key."""
    return SUPABASE_SECRET_KEY or SUPABASE_KEY
