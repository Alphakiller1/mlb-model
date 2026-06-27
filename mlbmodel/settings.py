"""Runtime settings owned by the unified MLB Model."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

DATA_DIR = Path(os.getenv("MLBMA_DATA_DIR", ROOT / "data"))
CACHE_DIR = Path(os.getenv("MLBMODEL_CACHE_DIR", ROOT / "data"))

MODEL_VERSION = os.getenv("BET_MODEL_VERSION", "v2-unified-expected-runs")
METRIC_VERSION = os.getenv("MLBMA_METRIC_VERSION", "2026.06")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_SPORT_KEY = "baseball_mlb"
ODDS_REGIONS = os.getenv("ODDS_REGIONS", "us,eu")
ODDS_GAME_MARKETS = "h2h,spreads,totals"
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
OSI_RUN_SENSITIVITY = 0.9
SP_FIP_WEIGHT = 0.70
REGRESSION_TO_MEAN = 0.25
LEAGUE_BULLPEN_ERA = 4.05
BULLPEN_IR_SENSITIVITY = 0.004
OFF_FACTOR_CLIP = (0.55, 1.60)
PITCH_FACTOR_CLIP = (0.60, 1.70)
IMPLAUSIBLE_EDGE = 0.15

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
