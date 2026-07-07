"""Matchup report panels — banner, context splits, advantage, F5, pitcher decks."""
from __future__ import annotations

import html
import json
import urllib.request
from functools import lru_cache

from mlbmodel.report.html_fmt import (
    edge_grade,
    pct_chip_html,
    section_head,
    val_chip_html,
    val_grade_html,
)
from mlbmodel.report.pitch_mix_ui import pitch_mix_board_html

e = html.escape

_MKT_SHORT = {
    "Away runs / Total / ML": "Away runs · total · ML",
    "Home runs / Total / ML": "Home runs · total · ML",
    "Away runs / pitcher props": "Away runs · SP props",
    "Home runs / pitcher props": "Home runs · SP props",
    "Total · ML": "Total · ML",
    "Total · TT": "Total · team total",
    "K props · Total": "K props · total",
    "Late ML · Total": "Late innings · total",
    "Late ML · live": "Late innings · live",
    "ML · close games": "ML · close games",
}


def _short_factor(name: str) -> str:
    text = str(name or "")
    for prefix in ("season offense", "offense depth", "offense vs", "platoon metrics vs",
                   "lineup vs", "starter quality", "bullpen", "park", "weather", "umpire",
                   "travel", "injury", "home-field", "arsenal"):
        if prefix in text.lower():
            idx = text.lower().find(prefix)
            team = text[:3].strip() if len(text) > 4 else ""
            rest = text[idx:].split("(")[0].strip()
            if team and team.isupper():
                return f"{team} {rest}"
            return rest.capitalize()
    if " · " in text:
        return text.split(" · ", 1)[0]
    return text[:48] + ("…" if len(text) > 48 else "")


def _short_markets(markets: str) -> str:
    key = str(markets or "").strip()
    return _MKT_SHORT.get(key, key.replace(" / ", " · "))


def league_avg_html(value, *, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return '<span class="league-avg">—</span>'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return '<span class="league-avg">—</span>'
    return f'<span class="league-avg">{number:.{digits}f}{suffix}</span>'


def impact_runs_html(runs: float | None) -> str:
    if runs is None:
        return '<span class="c-na">—</span>'
    cls = edge_grade(runs / 2.5)
    return f'<b class="{cls}">{runs:+.2f}</b>'


@lru_cache(maxsize=512)
def _inn1_runs_allowed(game_pk: int, pitcher_is_home: bool) -> int | None:
    try:
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        request = urllib.request.Request(url, headers={"User-Agent": "mlb-model/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            feed = json.loads(response.read().decode())
        innings = feed.get("liveData", {}).get("linescore", {}).get("innings", [])
        opp_side = "away" if pitcher_is_home else "home"
        for inn in innings:
            if inn.get("num") == 1:
                return int(inn.get(opp_side, {}).get("runs", 0) or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def _norm_name(name: str) -> str:
    import re
    return " ".join(re.sub(r"[^a-z ]", "", str(name or "").lower()).split())


def _sp_metric_split(repo, pitcher_name: str, dimension: str) -> dict[str, dict]:
    frame = repo.load("sp_metric_splits.csv")
    if frame is None or frame.empty:
        return {}
    sub = frame[
        (frame["pitcher_name"].astype(str).map(_norm_name) == _norm_name(pitcher_name))
        & (frame["split_dimension"].astype(str) == dimension)
    ]
    out: dict[str, dict] = {}
    for _, row in sub.iterrows():
        key = str(row.get("split_value") or "").strip()
        if key:
            out[key] = row.to_dict()
    return out


def _team_row(repo, team: str) -> dict:
    frame = repo.load("team_profiles.csv")
    if frame is None or "team" not in frame.columns:
        return {}
    sub = frame[frame["team"].astype(str).str.upper() == team.upper()]
    return sub.iloc[0].to_dict() if not sub.empty else {}


def _l10_record(repo, team: str, hand: str | None = None) -> str:
    frame = repo.load("game_results.csv")
    if frame is None or frame.empty:
        return "—"
    sub = frame[frame["team"].astype(str).str.upper() == team.upper()].copy()
    if sub.empty:
        return "—"
    sub = sub.sort_values("game_date", ascending=False).head(10)
    wins = int((sub["result"] == "W").sum())
    losses = int((sub["result"] == "L").sum())
    ties = int((sub["result"] == "T").sum())
    if hand:
        l10 = repo.load("team_l10_sp_hand.csv")
        if l10 is not None and not l10.empty:
            hand_row = l10[
                (l10["team"].astype(str).str.upper() == team.upper())
                & (l10["opp_starter_hand"].astype(str).str.upper() == hand.upper())
            ]
            if not hand_row.empty:
                w = int(hand_row.iloc[0].get("wins") or wins)
                g = int(hand_row.iloc[0].get("games") or 10)
                losses = max(0, g - w)
                wins = w
    if ties:
        return f"{wins}-{losses}-{ties}"
    return f"{wins}-{losses}"


def _sp_last5_inn1(repo, pitcher_name: str) -> list[dict]:
    frame = repo.load("sp_game_log.csv")
    if frame is None or frame.empty:
        return []
    sub = frame[
        frame["pitcher_name"].astype(str).map(_norm_name) == _norm_name(pitcher_name)
    ].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("date", ascending=False).head(5)
    rows = []
    for _, row in sub.iterrows():
        game_pk = row.get("game_pk")
        is_home = str(row.get("home_away") or "").lower() == "home"
        inn1 = None
        if game_pk is not None:
            try:
                inn1 = _inn1_runs_allowed(int(game_pk), is_home)
            except (TypeError, ValueError):
                inn1 = None
        rows.append({
            "date": str(row.get("date") or "")[:10],
            "opp": str(row.get("opponent_team") or ""),
            "inn1_er": inn1,
            "er": row.get("ER"),
        })
    return rows


def _weather_wind_label(weather: dict) -> str:
    if weather.get("status") == "dome":
        return "Dome · no wind"
    temp = weather.get("temp_f") or weather.get("temperature_f")
    wind = weather.get("wind_out_mph")
    if temp is None:
        return "Weather pending"
    direction = "out" if (wind or 0) >= 0 else "in"
    rain = weather.get("precipitation_probability_pct")
    rain_bit = f" · rain {float(rain or 0):.0f}%" if rain is not None else ""
    return f"{float(temp):.0f}°F · wind {direction} {abs(float(wind or 0)):.0f} mph{rain_bit}"


def matchup_banner_html(r: dict, esc) -> str:
    """Teams · weather/wind · full-game + F5 projection · score."""
    from mlbmodel.report.matchup import _f5_projection, _logo, _headshot

    gd, prob = r["gd"], r["probs"]
    ex = r.get("extras") or {}
    context = gd.live_context or {}
    weather = context.get("weather") or {}
    favored = gd.home if prob.exp_margin > 0 else gd.away
    lean_margin = abs(prob.exp_margin)
    lean_cls = edge_grade(lean_margin / 100) if lean_margin >= 0.25 else "c-mid"
    start = str(ex.get("start") or gd.start_time or "").strip()
    f5_proj = _f5_projection(r.get("pitchers"), gd.away, gd.home)
    if f5_proj:
        f5_away = f5_proj["home_f5"]["mean"]
        f5_home = f5_proj["away_f5"]["mean"]
        f5_total = f5_proj["total_mean"]
    else:
        f5_away = prob.exp_away_runs * 0.54
        f5_home = prob.exp_home_runs * 0.54
        f5_total = prob.exp_total * 0.54
    away_id, home_id = ex.get("a_id"), ex.get("h_id")

    return f"""<div class="matchup-banner matchup-banner--v2">
  <div class=matchup-banner__teams>
    <div class="matchup-banner__team matchup-banner__team--away">
      {_logo(gd.away, "tlogo lg")}
      <div class=matchup-banner__team-copy>
        <span class=matchup-banner__abbr>{esc(gd.away)}</span>
        <span class=mut>{esc(gd.away_sp)}</span>
      </div>
    </div>
    <div class=matchup-banner__center>
      <span class=matchup-banner__label>Projected score</span>
      <div class=matchup-banner__score>
        <span class=matchup-banner__runs>{prob.exp_away_runs:.1f}</span>
        <span class=matchup-banner__dash>–</span>
        <span class=matchup-banner__runs>{prob.exp_home_runs:.1f}</span>
      </div>
      <div class=matchup-banner__meta>
        {val_chip_html(prob.exp_total, "game_total", digits=1, suffix=" FG total")}
        <span class=mut>·</span>
        <span>Lean <b class="{lean_cls}">{esc(favored)} {lean_margin:+.1f}</b></span>
      </div>
    </div>
    <div class="matchup-banner__team matchup-banner__team--home">
      <div class=matchup-banner__team-copy>
        <span class=matchup-banner__abbr>{esc(gd.home)}</span>
        <span class=mut>{esc(gd.home_sp)}</span>
      </div>
      {_logo(gd.home, "tlogo lg")}
    </div>
  </div>
  <div class=matchup-banner__proj-row>
    <div class=matchup-proj-card>
      <span class=k>Full game</span>
      <span class=v>{prob.exp_away_runs:.1f} – {prob.exp_home_runs:.1f}</span>
      <span class=mut>{val_chip_html(prob.exp_total, "game_total", digits=1, suffix=" total")}</span>
    </div>
    <div class=matchup-proj-card>
      <span class=k>First 5</span>
      <span class=v>{f5_away:.1f} – {f5_home:.1f}</span>
      <span class=mut>{val_chip_html(f5_total, "game_total", digits=1, suffix=" F5 total")}</span>
    </div>
    <div class=matchup-proj-card>
      <span class=k>Weather · wind</span>
      <span class=v>{esc(_weather_wind_label(weather))}</span>
      {f'<span class=mut>{esc(start)}</span>' if start else ''}
    </div>
  </div>
  <div class=matchup-banner__pitchers>
    <div class=matchup-banner__sp>
      {_headshot(away_id)}<b>{esc(gd.away_sp)}</b>
      {val_chip_html(gd.away_k, "kpct", digits=1, suffix="% K") if gd.away_k else ""}
    </div>
    <div class=matchup-banner__vs>VS</div>
    <div class=matchup-banner__sp>
      <b>{esc(gd.home_sp)}</b>{_headshot(home_id)}
      {val_chip_html(gd.home_k, "kpct", digits=1, suffix="% K") if gd.home_k else ""}
    </div>
  </div>
</div>"""


def _split_table(headers: str, rows: str, *, empty_cols: int = 4) -> str:
    body = rows or f'<tr><td class=mut colspan={empty_cols}>No split data.</td></tr>'
    return (
        f'<div class=table-scroll><table class=matchup-split-table>'
        f'<tr>{headers}</tr>{body}</table></div>'
    )


def _metric_cells(value, context: str, *, invert: bool | None = None, digits: int = 1, suffix: str = ""):
    return val_grade_html(value, context, invert=invert, digits=digits, suffix=suffix, bold=True)


def matchup_context_html(r, gd, repo, esc) -> str:
    away_prof = _team_row(repo, gd.away)
    home_prof = _team_row(repo, gd.home)
    away_sp_hand = _sp_metric_split(repo, gd.away_sp, "hand")
    home_sp_hand = _sp_metric_split(repo, gd.home_sp, "hand")
    away_sp_loc = _sp_metric_split(repo, gd.away_sp, "location")
    home_sp_loc = _sp_metric_split(repo, gd.home_sp, "location")

    def pitcher_rl_rows(name, splits):
        rows = ""
        for label, key, ctx, inv in (
            ("vs LHB", "L", "fip", True),
            ("vs RHB", "R", "fip", True),
        ):
            row = splits.get(key, {})
            rows += (
                f'<tr><td><b>{esc(name)}</b><span class=mut> {label}</span></td>'
                f'<td>{_metric_cells(row.get("FIP"), "fip", invert=True)}</td>'
                f'<td>{_metric_cells(row.get("K_pct"), "kpct", digits=1, suffix="%")}</td>'
                f'<td>{_metric_cells(row.get("HR9"), "hr9", invert=True)}</td>'
                f'<td>{_metric_cells(row.get("OPS"), "woba", invert=True, digits=3)}</td></tr>'
            )
        return rows

    def pitcher_ha_rows(name, splits):
        rows = ""
        for label, key in (("Away", "away"), ("Home", "home")):
            row = splits.get(key, {})
            rows += (
                f'<tr><td><b>{esc(name)}</b><span class=mut> {label}</span></td>'
                f'<td>{_metric_cells(row.get("FIP"), "fip", invert=True)}</td>'
                f'<td>{_metric_cells(row.get("ERA"), "era", invert=True)}</td>'
                f'<td>{_metric_cells(row.get("K_pct"), "kpct", digits=1, suffix="%")}</td>'
                f'<td>{_metric_cells(row.get("F5_ERA"), "era", invert=True)}</td></tr>'
            )
        return rows

    def lineup_rl_row(team, prof):
        return (
            f'<tr><td><b>{esc(team)}</b></td>'
            f'<td>{_metric_cells(prof.get("osi_vs_lhp"), "osi", digits=0)}</td>'
            f'<td>{_metric_cells(prof.get("osi_vs_rhp"), "osi", digits=0)}</td>'
            f'<td>{_metric_cells(prof.get("abq_vs_lhp"), "abq", digits=0)}</td>'
            f'<td>{_metric_cells(prof.get("abq_vs_rhp"), "abq", digits=0)}</td></tr>'
        )

    def lineup_ha_row(team, prof):
        away = team == str(prof.get("team") or "").upper()
        if away:
            osi, woba, wrc = prof.get("away_osi"), prof.get("away_woba"), prof.get("away_wrc")
        else:
            osi, woba, wrc = prof.get("home_osi"), prof.get("home_woba"), prof.get("home_wrc")
        return (
            f'<tr><td><b>{esc(team)}</b><span class=mut> {"road" if away else "home"}</span></td>'
            f'<td>{_metric_cells(osi, "osi", digits=0)}</td>'
            f'<td>{_metric_cells(woba, "woba", digits=3)}</td>'
            f'<td>{_metric_cells(wrc, "wrc", digits=0)}</td></tr>'
        )

    bullpen_rows = (
        f'<tr><td><b>{esc(gd.away)}</b></td>'
        f'<td>{_metric_cells(gd.away_pen_factor, "park", invert=True, digits=3)}</td>'
        f'<td>{_metric_cells(away_prof.get("bullpen_high_lev_era"), "era", invert=True)}</td>'
        f'<td class=mut>{gd.away_bullpen_features.get("pitches_1d", "—")} pitches yesterday</td></tr>'
        f'<tr><td><b>{esc(gd.home)}</b></td>'
        f'<td>{_metric_cells(gd.home_pen_factor, "park", invert=True, digits=3)}</td>'
        f'<td>{_metric_cells(home_prof.get("bullpen_high_lev_era"), "era", invert=True)}</td>'
        f'<td class=mut>{gd.home_bullpen_features.get("pitches_1d", "—")} pitches yesterday</td></tr>'
    )

    pitchers = {row.get("team"): row for row in r.get("pitchers", []) if row.get("team")}
    away_mix = pitch_mix_board_html((pitchers.get(gd.away) or {}).get("pitch_matchup") or {}, compact=True)
    home_mix = pitch_mix_board_html((pitchers.get(gd.home) or {}).get("pitch_matchup") or {}, compact=True)
    pitch_mix_block = (
        f'<div class=matchup-pitchmix-duo>'
        f'<div><div class=ca-subhead>{esc(gd.away_sp)} vs {esc(gd.home)} lineup</div>{away_mix}</div>'
        f'<div><div class=ca-subhead>{esc(gd.home_sp)} vs {esc(gd.away)} lineup</div>{home_mix}</div>'
        f'</div>'
    )

    return f"""<div class=ca-board>{section_head("Matchup context", icon="matchups")}<div class=body>
  <div class=matchup-context-stack>
    <div class=matchup-context-block>
      <div class=ca-subhead>Pitcher R/L splits</div>
      {_split_table("<th>Pitcher</th><th>FIP</th><th>K%</th><th>HR/9</th><th>OPS allowed</th>",
                    pitcher_rl_rows(gd.away_sp, away_sp_hand) + pitcher_rl_rows(gd.home_sp, home_sp_hand), empty_cols=5)}
    </div>
    <div class=matchup-context-block>
      <div class=ca-subhead>Pitcher H/A splits</div>
      {_split_table("<th>Pitcher</th><th>FIP</th><th>ERA</th><th>K%</th><th>F5 ERA</th>",
                    pitcher_ha_rows(gd.away_sp, away_sp_loc) + pitcher_ha_rows(gd.home_sp, home_sp_loc), empty_cols=5)}
    </div>
    <div class=matchup-context-block>
      <div class=ca-subhead>Lineup R/L splits</div>
      {_split_table("<th>Team</th><th>OSI vs LHP</th><th>OSI vs RHP</th><th>ABQ vs LHP</th><th>ABQ vs RHP</th>",
                    lineup_rl_row(gd.away, away_prof) + lineup_rl_row(gd.home, home_prof), empty_cols=5)}
    </div>
    <div class=matchup-context-block>
      <div class=ca-subhead>Lineup H/A splits</div>
      {_split_table("<th>Team</th><th>OSI</th><th>wOBA</th><th>wRC+</th>",
                    lineup_ha_row(gd.away, away_prof) + lineup_ha_row(gd.home, home_prof), empty_cols=4)}
    </div>
    <div class=matchup-context-block>
      <div class=ca-subhead>Bullpen implications</div>
      {_split_table("<th>Team</th><th>Run factor</th><th>High-lev ERA</th><th>Workload</th>", bullpen_rows, empty_cols=4)}
    </div>
    <div class=matchup-context-block matchup-context-block--wide>
      <div class=ca-subhead>Pitch mix vs opposing lineup</div>
      {pitch_mix_block}
    </div>
  </div>
</div></div>"""


def advantage_panel_html(gd, advantage_rows, esc) -> str:
    if not advantage_rows:
        return ""

    def adv_row(a):
        unit, lb = a.get("unit", ""), a.get("lower_better")
        av = val_grade_html(a.get("a_val"), _adv_ctx(a["cat"]), invert=lb, digits=_adv_digits(a, unit), suffix=unit)
        hv = val_grade_html(a.get("h_val"), _adv_ctx(a["cat"]), invert=lb, digits=_adv_digits(a, unit), suffix=unit)
        base = league_avg_html(a.get("base"), digits=_adv_digits(a, unit), suffix=unit)
        edge = esc(str(a.get("edge") or "—"))
        if edge not in ("—", "even"):
            edge = f'<b class="side">{edge}</b>'
        return (
            f'<tr><td><b>{esc(a["cat"])}</b></td>'
            f'<td class=side>{av}</td><td>{hv}</td>'
            f'<td>{base}</td><td>{edge}</td></tr>'
        )

    rows = "".join(adv_row(a) for a in advantage_rows)
    return (
        f'<div class=ca-board>{section_head("Matchup advantage", icon="matchups")}<div class=body>'
        f'<div class=table-scroll><table class=matchup-adv-table>'
        f'<tr><th>Category</th><th>{esc(gd.away)}</th><th>{esc(gd.home)}</th>'
        f'<th>League avg</th><th>Edge</th></tr>{rows}</table></div></div></div>'
    )


def _adv_ctx(cat: str) -> str:
    from mlbmodel.report.matchup import _adv_metric_context
    return _adv_metric_context(cat)


def _adv_digits(a, unit: str) -> int:
    if unit == "%":
        return 1
    if "wOBA" in a.get("cat", ""):
        return 3
    return 2


def run_impacts_html(factors: list[dict], esc) -> str:
    rows = "".join(
        f'<tr><td><b>{esc(_short_factor(f["name"]))}</b>'
        f'<span class=mut> · {esc(f["side"])}</span></td>'
        f'<td class=num>{impact_runs_html(f.get("runs"))}</td>'
        f'<td>{esc(_short_markets(f.get("market", "")))}</td></tr>'
        for f in factors[:8]
    ) or '<tr><td class=mut colspan=3>No modeled run drivers.</td></tr>'
    return (
        f'<div class=ca-board>{section_head("Biggest run impacts", icon="matchups")}<div class=body>'
        f'<div class=table-scroll><table><tr><th>Factor</th><th>Impact</th><th>Affects</th></tr>'
        f'{rows}</table></div></div></div>'
    )


def f5_section_html(r, gd, repo, esc) -> str:
    from mlbmodel.report.matchup import _f5_projection

    proj = _f5_projection(r.get("pitchers"), gd.away, gd.home)
    if proj is None:
        return ""

    away_inn1 = _sp_last5_inn1(repo, gd.away_sp)
    home_inn1 = _sp_last5_inn1(repo, gd.home_sp)

    def inn1_strip(team, sp_name, starts, runs_mean):
        cells = []
        for row in starts:
            val = row.get("inn1_er")
            cell = val_grade_html(val, "game_total", digits=0) if val is not None else '<span class=c-na>—</span>'
            cells.append(
                f'<span class=f5-inn1-chip title="{esc(row.get("date", ""))} vs {esc(row.get("opp", ""))}">'
                f'{cell}</span>'
            )
        if not cells:
            cells = ['<span class=mut>—</span>']
        hand = gd.home_hand if team == gd.away else gd.away_hand
        rec = _l10_record(repo, team, hand)
        return (
            f'<div class=f5-team-col><div class=f5-team-head><b>{esc(team)}</b>'
            f'<span class=mut>L10 {esc(_l10_record(repo, team))}</span>'
            f'<span class=mut>vs {esc(hand)}HP {esc(rec)}</span></div>'
            f'<div class=f5-run-line>{runs_mean:.2f} runs</div>'
            f'<div class=f5-sp-line><span class=mut>{esc(sp_name)}</span>'
            f'<span class=mut>1st-inn ER · last 5</span></div>'
            f'<div class=f5-inn1-row>{"".join(cells)}</div></div>'
        )

    away_runs = proj["home_f5"]["mean"]
    home_runs = proj["away_f5"]["mean"]
    return f"""<div class=ca-board>{section_head("First 5 innings", icon="markets")}<div class=body>
  <div class=f5-proj-grid>
    {inn1_strip(gd.away, gd.away_sp, away_inn1, away_runs)}
    <div class=f5-mid-col>
      <span class=k>F5 total</span>
      <span class=v>{val_chip_html(proj["total_mean"], "game_total", digits=2)}</span>
      <span class=mut>{away_runs:.2f} + {home_runs:.2f}</span>
    </div>
    {inn1_strip(gd.home, gd.home_sp, home_inn1, home_runs)}
  </div>
</div></div>"""


def pitcher_deck_html(r, gd, repo, esc) -> str:
    pitchers = {row.get("team"): row for row in r.get("pitchers", []) if row.get("team")}

    def deck(team, opponent, hand_faced):
        row = pitchers.get(team) or {}
        projections = row.get("projections") or {}
        if not projections:
            return (
                f'<div class=pitcher-deck-card><div class=ca-subhead>{esc(team)} SP</div>'
                f'<div class=empty>No projection.</div></div>'
            )
        l10 = repo.load("team_l10_sp_hand.csv")
        team_ops = "—"
        if l10 is not None and not l10.empty:
            sub = l10[
                (l10["team"].astype(str).str.upper() == opponent.upper())
                & (l10["opp_starter_hand"].astype(str).str.upper() == str(hand_faced).upper())
            ]
            if not sub.empty:
                ops = sub.iloc[0].get("ops")
                woba = sub.iloc[0].get("woba")
                if ops is not None:
                    team_ops = f'OPS {float(ops):.3f} · wOBA {float(woba):.3f}'

        stat_cards = []
        for key, label, ctx in (
            ("K", "Strikeouts", "kpct"),
            ("ER", "Earned runs", "game_total"),
            ("Outs", "Outs", "rate"),
            ("H", "Hits", "rate"),
            ("Fantasy", "DK pts", "osi"),
        ):
            dist = projections.get(key) or {}
            mean = dist.get("mean")
            if mean is None:
                continue
            inv = key in {"ER", "H"}
            stat_cards.append(
                f'<div class=pitcher-stat-card>'
                f'<span class=k>{label}</span>'
                f'<span class=v>{val_grade_html(mean, ctx, invert=inv, digits=1)}</span>'
                f'<span class=mut>{dist.get("p10", "—"):.0f}–{dist.get("p90", "—"):.0f}</span></div>'
            )
        pitch_mix = pitch_mix_board_html(row.get("pitch_matchup") or {}, compact=False)
        state = str(row.get("state") or "")
        state_cls = "neg" if state == "REGRESSION" else ("pos" if state == "PROGRESSION" else "mut")
        return f"""<div class=pitcher-deck-card>
  <div class=pitcher-deck-head>
    <b>{esc(str(row.get("pitcher") or team))}</b>
    <span class=mut>vs {esc(opponent)}</span>
    <span class="pill {state_cls}">{esc(state)}</span>
  </div>
  <div class=pitcher-stat-grid>{"".join(stat_cards)}</div>
  <div class=pitcher-opp-ops><span class=mut>Opp vs {esc(hand_faced)}HP</span> {esc(team_ops)}</div>
  {pitch_mix}
</div>"""

    return (
        f'<div class=ca-board>{section_head("Pitcher projection & breakdowns", icon="props")}<div class=body>'
        f'<div class=pitcher-deck-grid>'
        f'{deck(gd.away, gd.home, gd.home_hand)}'
        f'{deck(gd.home, gd.away, gd.away_hand)}'
        f'</div></div></div>'
    )
