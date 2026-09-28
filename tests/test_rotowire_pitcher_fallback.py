import csv

from mlbmodel.sources.build_today_matchups import build_rows
from mlbmodel.sources.live_context import parse_rotowire_pitchers
from mlbmodel.sources.sync_mlbma import merge_pipeline_slate


ROTOWIRE_HTML = """
<div class="lineup is-mlb">
  <div class="lineup__abbr">CWS</div><div class="lineup__abbr">HOU</div>
  <ul class="lineup__list is-visit">
    <li class="lineup__player-highlight">
      <div class="lineup__player-highlight-name">
        <a href="/baseball/player/erick-fedde-13346">Erick Fedde</a>
        <span class="lineup__throws">R</span>
      </div>
      <div class="lineup__player-highlight-stats"><div class="tag">PRIM</div></div>
    </li>
  </ul>
  <ul class="lineup__list is-home">
    <li class="lineup__player-highlight">
      <div class="lineup__player-highlight-name"><b>Undecided</b></div>
    </li>
  </ul>
</div>
<div class="lineup is-mlb">
  <div class="lineup__abbr">PHI</div><div class="lineup__abbr">ATL</div>
  <ul class="lineup__list is-visit">
    <li class="lineup__player-highlight">
      <div class="lineup__player-highlight-name">
        <a href="/baseball/player/cristopher-sanchez-16500">C. Sanchez</a>
        <span class="lineup__throws">L</span>
      </div>
    </li>
  </ul>
  <ul class="lineup__list is-home"></ul>
</div>
"""


def test_rotowire_parser_includes_primary_and_expands_abbreviated_name():
    parsed = parse_rotowire_pitchers(ROTOWIRE_HTML)

    fedde = parsed[("CHW", "HOU")][0]["away"]
    assert fedde == {
        "pitcher": "Erick Fedde",
        "hand": "R",
        "designation": "primary",
        "source": "Rotowire",
    }
    assert "home" not in parsed[("CHW", "HOU")][0]
    assert parsed[("PHI", "ATL")][0]["away"]["pitcher"] == "Cristopher Sanchez"


def test_build_rows_defaults_to_rotowire_when_mlb_probable_is_missing(tmp_path):
    with (tmp_path / "sp_profiles.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["pitcher_id", "pitcher_name", "pitcher_team", "pitcher_hand", "FIP", "HR9", "K_pct"],
        )
        writer.writeheader()
        writer.writerow({
            "pitcher_id": "607200", "pitcher_name": "Erick Fedde", "pitcher_team": "CHW",
            "pitcher_hand": "R", "FIP": "4.01", "HR9": "1.10", "K_pct": "20.2",
        })
    with (tmp_path / "team_profiles.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["team", "home_osi", "away_osi", "osi"])
        writer.writeheader()
        writer.writerows([
            {"team": "CHW", "away_osi": "48"},
            {"team": "HOU", "home_osi": "55"},
        ])

    games = [{
        "gamePk": 99,
        "gameNumber": 1,
        "gameDate": "2026-09-29T21:00:00Z",
        "teams": {
            "away": {"team": {"name": "Chicago White Sox"}},
            "home": {"team": {"name": "Houston Astros"}},
        },
    }]
    rotowire = parse_rotowire_pitchers(ROTOWIRE_HTML, {("CHW", "HOU")})

    row = build_rows(tmp_path, "2026-09-29", games, rotowire_pitchers=rotowire)[0]

    assert row["Away_SP"] == "Erick Fedde"
    assert row["Away_Hand"] == "R"
    assert row["Away_FIP"] == "4.01"
    assert row["Home_SP"] == "TBD"


def test_pipeline_tbd_does_not_replace_rotowire_fallback():
    schedule = [{"Away": "CHW", "Home": "HOU", "Away_SP": "Erick Fedde", "Home_SP": "TBD"}]
    pipeline = [{"Away": "CHW", "Home": "HOU", "Away_SP": "TBD", "Home_SP": "Undecided"}]

    merged, exact = merge_pipeline_slate(schedule, pipeline)

    assert exact is True
    assert merged[0]["Away_SP"] == "Erick Fedde"
    assert merged[0]["Home_SP"] == "TBD"
