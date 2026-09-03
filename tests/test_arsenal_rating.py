"""Arsenal rating + vs-hand splits — engine maths, degradation, and the breakdown panels."""
from __future__ import annotations

import html

import pandas as pd
import pytest

from mlbmodel.baseball.arsenal_rating import (
    AXES,
    SHRINK_PA,
    WEIGHTS,
    ArsenalRatingEngine,
    norm_name,
)
from mlbmodel.report.matchup_ui import (
    _arsenal_engine_for,
    _hand_split_block,
    _hand_window_days,
    _ordinal,
    _pretty_date,
    matchup_context_html,
)
from mlbmodel.sources.build_hand_pitch_splits import (
    PA_EVENTS,
    accumulate,
    blank_bucket,
    rates,
)


class StubRepo:
    def __init__(self, frames: dict[str, pd.DataFrame | None]):
        self.frames = frames

    def load(self, name):
        frame = self.frames.get(name)
        return frame.copy() if frame is not None else None


# The engine refuses to rank fewer than MIN_TEAMS_FOR_RANK clubs, so the fixture is a full
# 30-club league: HOT at one end, COLD at the other, MID exactly on the league line, and 27
# fillers spread evenly between them.
LEAGUE_MIX = {"FF": dict(woba=0.330, iso=0.170, avg=0.250, bb_pct=10.0, k_pct=22.0),
              "SL": dict(woba=0.295, iso=0.160, avg=0.225, bb_pct=6.5, k_pct=27.0)}
# Signed offset applied at scale 1.0; K% moves the other way because strikeouts hurt.
HOT_OFFSET = dict(woba=0.050, iso=0.050, avg=0.045, bb_pct=2.0, k_pct=-4.0)


def _team_mix(scale: float) -> dict[str, dict[str, float]]:
    return {
        pitch: {axis: value + scale * HOT_OFFSET[axis] for axis, value in values.items()}
        for pitch, values in LEAGUE_MIX.items()
    }


def _mix_frame() -> pd.DataFrame:
    profiles = {"HOT": _team_mix(1.0), "MID": _team_mix(0.0), "COLD": _team_mix(-1.0)}
    for index in range(27):
        profiles[f"T{index:02d}"] = _team_mix(-0.9 + 1.8 * index / 26)
    rows = []
    for team, mix in list(profiles.items()) + [("LGE", LEAGUE_MIX)]:
        for pitch, values in mix.items():
            rows.append({"team": team, "pitch_type": pitch, "pitch_name": pitch,
                         "pa": 400000 if team == "LGE" else 4000, **values,
                         "window_start": "2026-05-03", "window_end": "2026-08-31"})
    return pd.DataFrame(rows)


def _arsenal_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"full_name": "Fastballer, Fred", "pitch_type": "FF", "pitch_pct": 70.0,
         "pitch_name": "4-Seam Fastball"},
        {"full_name": "Fastballer, Fred", "pitch_type": "SL", "pitch_pct": 30.0,
         "pitch_name": "Slider"},
        {"full_name": "Rare, Randy", "pitch_type": "FF", "pitch_pct": 2.0,
         "pitch_name": "4-Seam Fastball"},
    ])


def _hand_frame() -> pd.DataFrame:
    base = dict(games=27, pa=1000, ab=900, h=225, tb=380, bb=85, hbp=9, so=210, hr=28,
                obp=0.315, slg=0.422, hr_pct=2.8,
                window_start="2026-08-01", window_end="2026-08-31")
    return pd.DataFrame([
        {"team": "HOT", "pitcher_hand": "R", "k_pct": 18.0, "bb_pct": 11.0, "avg": 0.270,
         "iso": 0.180, "woba": 0.345, **base},
        {"team": "HOT", "pitcher_hand": "L", "k_pct": 24.0, "bb_pct": 7.0, "avg": 0.225,
         "iso": 0.130, "woba": 0.290, **base},
        {"team": "COLD", "pitcher_hand": "R", "k_pct": 26.0, "bb_pct": 6.5, "avg": 0.215,
         "iso": 0.110, "woba": 0.281, **base},
        {"team": "COLD", "pitcher_hand": "L", "k_pct": 27.5, "bb_pct": 6.0, "avg": 0.208,
         "iso": 0.105, "woba": 0.274, **base},
        {"team": "LGE", "pitcher_hand": "R", "k_pct": 21.3, "bb_pct": 9.2, "avg": 0.244,
         "iso": 0.149, "woba": 0.316, **base},
        {"team": "LGE", "pitcher_hand": "L", "k_pct": 22.8, "bb_pct": 8.6, "avg": 0.242,
         "iso": 0.151, "woba": 0.313, **base},
    ])


@pytest.fixture
def engine() -> ArsenalRatingEngine:
    return ArsenalRatingEngine(StubRepo({
        "team_pitch_type_splits.csv": _mix_frame(),
        "team_hand_splits.csv": _hand_frame(),
        "pitch_mix_pitcher.csv": _arsenal_frame(),
        "pitch_mix_pitcher_l14.csv": None,
    }))


# ── plate-appearance grammar (the scraper's contract with MLB's own totals) ────────────
def test_pa_whitelist_excludes_plays_that_do_not_end_a_plate_appearance():
    # These end a PLAY, not a PA. Counting them is what inflates PA against MLB's totals.
    for event in ("pickoff_1b", "caught_stealing_2b", "stolen_base_3b", "wild_pitch",
                  "passed_ball", "balk", "game_advisory", "pickoff_caught_stealing_2b"):
        assert event not in PA_EVENTS
    for event in ("single", "walk", "strikeout", "hit_by_pitch", "sac_fly",
                  "catcher_interf", "field_error", "grounded_into_double_play"):
        assert event in PA_EVENTS


def test_at_bats_exclude_walks_hbp_sacrifices_and_interference():
    bucket = blank_bucket()
    for event in ("single", "walk", "hit_by_pitch", "sac_fly", "sac_bunt",
                  "catcher_interf", "strikeout"):
        accumulate(bucket, event)
    assert bucket["pa"] == 7
    assert bucket["ab"] == 2  # single + strikeout only
    assert bucket["h"] == 1
    assert rates(bucket)["avg"] == pytest.approx(0.5)


def test_intentional_walks_leave_the_woba_numerator_but_not_the_walk_count():
    plain, intentional = blank_bucket(), blank_bucket()
    for bucket, event in ((plain, "walk"), (intentional, "intent_walk")):
        accumulate(bucket, event)
        accumulate(bucket, "field_out")
    assert plain["bb"] == intentional["bb"] == 1
    assert rates(plain)["bb_pct"] == rates(intentional)["bb_pct"]
    assert rates(plain)["woba"] > rates(intentional)["woba"] == 0.0


def test_iso_is_slugging_minus_average():
    bucket = blank_bucket()
    for event in ("home_run", "single", "field_out", "field_out"):
        accumulate(bucket, event)
    read = rates(bucket)
    assert read["iso"] == pytest.approx(read["slg"] - read["avg"])


# ── rating engine ─────────────────────────────────────────────────────────────────────
def test_norm_name_matches_both_roster_spellings():
    assert norm_name("Skubal, Tarik") == norm_name("Tarik Skubal") == "tarik skubal"


def test_composite_weights_cover_every_scored_axis_and_sum_to_one():
    assert set(WEIGHTS) == set(AXES)
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_rating_orders_clubs_by_measured_production(engine):
    hot = engine.rate("HOT", "Fred Fastballer")
    mid = engine.rate("MID", "Fred Fastballer")
    cold = engine.rate("COLD", "Fred Fastballer")
    assert hot.rating > mid.rating > cold.rating
    assert (hot.rank, cold.rank) == (1, 30)
    assert hot.teams_ranked == 30
    assert hot.verdict == "Lineup" and cold.verdict == "Pitcher"
    assert mid.verdict == "Neutral"
    assert 2.0 <= cold.rating < hot.rating <= 98.0


def test_axis_values_are_usage_weighted_across_the_arsenal(engine):
    read = engine.rate("MID", "Fred Fastballer")
    # MID sits exactly on the league line, so 70% FF + 30% SL must reproduce it.
    assert read.axes["woba"].team_value == pytest.approx(0.7 * 0.330 + 0.3 * 0.295, abs=1e-6)
    assert read.axes["woba"].league_value == pytest.approx(read.axes["woba"].team_value,
                                                           abs=1e-6)
    assert read.coverage_pct == pytest.approx(100.0)


def test_strikeouts_are_scored_from_the_offense_side(engine):
    """A low K% is GOOD for a lineup — the opposite of how the pitcher board reads it."""
    hot = engine.rate("HOT", "Fred Fastballer")
    cold = engine.rate("COLD", "Fred Fastballer")
    assert hot.axes["k_pct"].team_value < cold.axes["k_pct"].team_value
    assert hot.axes["k_pct"].score > cold.axes["k_pct"].score
    assert hot.axes["k_pct"].rank == 1


def test_walks_axis_is_shrunk_entirely_to_the_prior(engine):
    """SHRINK_PA['bb_pct'] is None because the between-cell spread measured as pure sampling
    noise; the axis must therefore report the club's own level, never a pitch-specific one."""
    assert SHRINK_PA["bb_pct"] is None
    read = engine.rate("HOT", "Fred Fastballer")
    frame = _mix_frame()
    club = frame[frame.team == "HOT"]
    league = frame[frame.team == "LGE"]
    club_edge = (
        (club.bb_pct * club.pa).sum() / club.pa.sum()
        - (league.bb_pct * league.pa).sum() / league.pa.sum()
    )
    assert read.axes["bb_pct"].team_value == pytest.approx(
        read.axes["bb_pct"].league_value + club_edge, abs=1e-6
    )


def test_thin_arsenal_coverage_yields_no_rating(engine):
    # Randy throws one pitch at 2% usage — below MIN_USAGE_PCT, so nothing resolves.
    assert engine.rate("HOT", "Randy Rare") is None
    assert engine.rate("HOT", "Nobody At All") is None
    assert engine.rate("NOPE", "Fred Fastballer") is None


def test_engine_reports_not_ok_without_the_splits_file():
    engine = ArsenalRatingEngine(StubRepo({}))
    assert engine.ok is False
    assert engine.rate("HOT", "Fred Fastballer") is None


def test_hand_split_lookup_is_case_insensitive_and_league_aware(engine):
    assert engine.hand_split("hot", "r")["k_pct"] == pytest.approx(18.0)
    assert engine.league_hand_split("L")["k_pct"] == pytest.approx(22.8)
    assert engine.hand_split("HOT", "S") is None


# ── report panels ─────────────────────────────────────────────────────────────────────
def test_hand_split_block_marks_the_hand_being_faced(engine):
    block = _hand_split_block(engine, "HOT", "Lefty Lou", "L", html.escape)
    assert "facing Lefty Lou (LHP)" in block
    assert "matchup-hand-row--facing" in block
    # Both hands and the league line, so a platoon read is not mistaken for a level read.
    assert "vs LHP" in block and "vs RHP" in block and "MLB vs LHP" in block
    # Per-hand denominators, not a single ambiguous game count.
    assert "1,000 PA vs RHP" in block and "1,000 PA vs LHP" in block
    assert "Aug 1 – Aug 31" in block


def test_hand_split_block_degrades_without_an_engine():
    assert "unavailable" in _hand_split_block(None, "HOT", "Someone", "R", html.escape)


def test_hand_window_days_is_read_from_the_data(engine):
    assert _hand_window_days(engine) == 30
    assert _hand_window_days(None) == 30


def test_pretty_date_has_no_platform_specific_padding_flag():
    assert _pretty_date("2026-08-01") == "Aug 1"
    assert _pretty_date("2026-12-25") == "Dec 25"
    assert _pretty_date("not a date") == "not a date"


def test_ordinal_handles_the_teens():
    assert [_ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 30)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "30th"]


def test_breakdown_renders_both_new_sections():
    gd = type("GD", (), {
        "away": "HOT", "home": "COLD",
        "away_sp": "Fred Fastballer", "home_sp": "Fred Fastballer",
        "away_hand": "R", "home_hand": "L",
        "away_pen_factor": 1.0, "home_pen_factor": 1.0,
        "away_bullpen_features": {}, "home_bullpen_features": {},
    })()
    repo = StubRepo({
        "team_pitch_type_splits.csv": _mix_frame(),
        "team_hand_splits.csv": _hand_frame(),
        "pitch_mix_pitcher.csv": _arsenal_frame(),
    })
    panel = matchup_context_html({"pitchers": []}, gd, repo, html.escape)
    assert "Offense vs hand · L30" in panel
    assert "Arsenal rating" in panel
    assert "Run creation" in panel and "Power" in panel and "Walks" in panel
    # The away lane bats against the HOME starter, and vice versa.
    assert panel.index("Offense vs hand") < panel.index("Arsenal rating")
    assert "Edge lineup" in panel and "Edge arsenal" in panel


def test_breakdown_survives_a_repository_with_no_split_files():
    gd = type("GD", (), {
        "away": "NYY", "home": "BOS", "away_sp": "Cole", "home_sp": "Bello",
        "away_hand": "R", "home_hand": "R",
        "away_pen_factor": 1.0, "home_pen_factor": 1.0,
        "away_bullpen_features": {}, "home_bullpen_features": {},
    })()
    panel = matchup_context_html({"pitchers": []}, gd, StubRepo({}), html.escape)
    assert "Matchup breakdown" in panel
    assert "Recent hand splits unavailable" in panel
    assert "No arsenal read" in panel


def test_engine_is_built_once_per_repository():
    repo = StubRepo({
        "team_pitch_type_splits.csv": _mix_frame(),
        "team_hand_splits.csv": _hand_frame(),
        "pitch_mix_pitcher.csv": _arsenal_frame(),
    })
    assert _arsenal_engine_for(repo) is _arsenal_engine_for(repo)
