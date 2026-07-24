"""Runtime settings owned by the unified MLB Model."""
from __future__ import annotations

import os
from pathlib import Path

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

from mlbmodel.genesis.logic_matrix import (
    CONVERGENCE_THRESHOLD,
    LINEAGE_VERSION,
    MODEL_SENSITIVITIES,
)

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

LEAGUE_RUNS_PER_TEAM = 4.58
LEAGUE_FIP = 4.20
HOME_BASE_WINP = 0.540
AWAY_BASE_WINP = 0.460
TOTAL_RUNS_SD = 4.79
TEAM_RUNS_SD = 3.33
MARGIN_SD = 4.40
HFA_RUNS = 0.15
OSI_RUN_SENSITIVITY = MODEL_SENSITIVITIES["osi_run"]
SP_FIP_WEIGHT = MODEL_SENSITIVITIES["sp_fip_weight"]
REGRESSION_TO_MEAN = MODEL_SENSITIVITIES["regression_to_mean"]
LEAGUE_BULLPEN_ERA = 4.05
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

PARK_FACTORS = {
    "COL": 1.38, "BOS": 1.12, "CIN": 1.10, "TEX": 1.08, "PHI": 1.07,
    "NYY": 1.06, "CHC": 1.05, "MIL": 1.04, "ATL": 1.03, "HOU": 1.02,
    "LAD": 1.01, "NYM": 1.00, "STL": 1.00, "MIN": 0.99, "DET": 0.99,
    "TOR": 0.98, "BAL": 0.98, "ARI": 0.97, "SFG": 0.97, "SEA": 0.96,
    "CLE": 0.96, "PIT": 0.95, "WSN": 0.95, "KCR": 0.95, "MIA": 0.94,
    "TBR": 0.94, "LAA": 0.93, "SDP": 0.92, "CHW": 0.91, "ATH": 0.90,
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
