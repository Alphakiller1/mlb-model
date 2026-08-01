"""Matchup report panels — banner, context splits, advantage, F5, pitcher decks."""
from __future__ import annotations

import html
import json
import urllib.request
from functools import lru_cache

from mlbmodel.report.html_fmt import (
    edge_grade,
    prob_chip_html,
    run_impact_grade,
    section_head,
    val_chip_html,
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


def _adv_value_chip(value, context: str, *, invert: bool | None, digits: int, suffix: str = "") -> str:
    if value is None:
        return '<span class="c-na">—</span>'
    return val_chip_html(value, context, invert=invert, digits=digits, suffix=suffix)


def _adv_edge_html(row: dict, away: str, home: str, esc) -> str:
    edge = str(row.get("edge") or "—")
    if edge == "—":
        return '<span class="c-na">—</span>'
    if edge == "even":
        return '<span class="pill mut">Even</span>'
    ap = row.get("a_pct")
    hp = row.get("h_pct")
    if isinstance(ap, (int, float)) and isinstance(hp, (int, float)):
        gap = abs(float(ap) - float(hp))
        score = min(100.0, 50.0 + gap * 0.45)
        return val_chip_html(score, "osi", digits=0, display_text=esc(edge))
    return f'<span class="pill pos">{esc(edge)}</span>'


def impact_runs_html(runs: float | None) -> str:
    if runs is None:
        return '<span class="c-na">—</span>'
    try:
        value = float(runs)
    except (TypeError, ValueError):
        return '<span class="c-na">—</span>'
    cls = run_impact_grade(value)
    return f'<span class="chip {cls}">{value:+.2f} R</span>'


@lru_cache(maxsize=512)
def _f5_runs_allowed(game_pk: int, pitcher_is_home: bool) -> int | None:
    """Runs the pitcher's team allowed through the first 5 innings (F5) of a start.

    Summed from the game's linescore innings 1-5 (opponent's side). This is runs, not strictly
    earned runs, and it is the pitching team's total through 5 (relievers included if the starter
    left before the 5th) — a standard F5 recent-form read, not a 1st-inning-only figure.
    """
    try:
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        request = urllib.request.Request(url, headers={"User-Agent": "mlb-model/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            feed = json.loads(response.read().decode())
        innings = feed.get("liveData", {}).get("linescore", {}).get("innings", [])
        opp_side = "away" if pitcher_is_home else "home"
        total, found = 0, False
        for inn in innings:
            num = inn.get("num")
            if isinstance(num, int) and 1 <= num <= 5:
                total += int(inn.get(opp_side, {}).get("runs", 0) or 0)
                found = True
        return total if found else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _norm_name(name: str) -> str:
    import re
    return " ".join(re.sub(r"[^a-z ]", "", str(name or "").lower()).split())


def _sp_metric_split(repo, pitcher_name: str, dimension: str) -> dict[str, dict]:
    if not pitcher_name or str(pitcher_name).strip().upper() == "TBD":
        return {}
    frame = repo.load("sp_metric_splits.csv")
    if frame is None or frame.empty:
        return {}
    dim = "batter_hand" if dimension in {"hand", "batter_hand"} else dimension
    sub = frame[
        (frame["pitcher_name"].astype(str).map(_norm_name) == _norm_name(pitcher_name))
        & (frame["split_dimension"].astype(str) == dim)
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
    # game_results.csv dates the game in a `date` column (MLBMA schema); tolerate the
    # legacy `game_date` name too, and don't hard-fail if neither is present.
    date_col = next((c for c in ("date", "game_date") if c in sub.columns), None)
    if date_col:
        sub = sub.sort_values(date_col, ascending=False).head(10)
    else:
        sub = sub.head(10)
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
        f5 = None
        if game_pk is not None:
            try:
                f5 = _f5_runs_allowed(int(game_pk), is_home)
            except (TypeError, ValueError):
                f5 = None
        rows.append({
            "date": str(row.get("date") or "")[:10],
            "opp": str(row.get("opponent_team") or ""),
            "f5_er": f5,
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


def _sym_cell(value_html: str, *, side: str, win: bool = False) -> str:
    cls = f"sym-metric-cell sym-metric-cell--{side}"
    if win:
        cls += " sym-metric-cell--win"
    return f'<div class="{cls}">{value_html}</div>'


def _sym_row(label: str, away_html: str, home_html: str, *, away_win: bool = False, home_win: bool = False) -> str:
    return (
        f'<div class=sym-metric-row>'
        f'{_sym_cell(away_html, side="away", win=away_win)}'
        f'<div class=sym-metric-label>{label}</div>'
        f'{_sym_cell(home_html, side="home", win=home_win)}'
        f'</div>'
    )


def sym_projection_board_html(r: dict, esc, *, compact: bool = False) -> str:
    """Canonical mirrored desk board: Away | axis | Home (+ factors when not compact)."""
    from mlbmodel.baseball.model import fair_price
    from mlbmodel.report.html_fmt import display as _display
    from mlbmodel.report.matchup import _logo

    gd, prob = r["gd"], r["probs"]
    ex = r.get("extras") or {}
    context = getattr(gd, "live_context", None) or {}
    weather = context.get("weather") or {}
    away_win_p = float(getattr(prob, "p_away_win", 0) or 0)
    home_win_p = float(getattr(prob, "p_home_win", 0) or 0)
    away_runs = float(getattr(prob, "exp_away_runs", 0) or 0)
    home_runs = float(getattr(prob, "exp_home_runs", 0) or 0)
    fair_away = fair_price(away_win_p) if away_win_p > 0 else None
    fair_home = fair_price(home_win_p) if home_win_p > 0 else None
    tot = away_runs + home_runs
    start = str(ex.get("start") or getattr(gd, "start_time", "") or "").strip() or "TBD"
    park = str(ex.get("park") or getattr(gd, "park_name", "") or context.get("venue") or "Park")
    park_factor = ex.get("park_factor") or getattr(gd, "park_factor", None)
    park_txt = f"{esc(str(park)[:28])}" + (
        f" · {float(park_factor):.2f}" if isinstance(park_factor, (int, float)) else ""
    )
    wx = str(weather.get("summary") or weather.get("condition") or "Wx TBD")

    def _fip(v):
        return _display(v, digits=2) if v is not None else "—"

    def _kpct(v):
        return val_chip_html(v, "kpct", digits=1, suffix="%") if v is not None else '<span class="c-na">—</span>'

    def _sp_block(name, hand, fip, k):
        nm = esc(str(name or "TBD"))
        hd = esc(str(hand or ""))
        return (
            f'<span class=sym-metric-board__sp><b>{nm}</b>'
            f'{(" · " + hd) if hd else ""}<br>'
            f'<span class=mono>FIP {_fip(fip)} · K% {_display(k, digits=1) if k is not None else "—"}</span></span>'
        )

    win_bar = ""
    if away_win_p > 0 or home_win_p > 0:
        a_pct = max(0.0, min(100.0, away_win_p * 100))
        h_pct = max(0.0, min(100.0, home_win_p * 100))
        win_bar = (
            f'<div class=sym-metric-bar aria-hidden=true>'
            f'<div class="sym-metric-bar__track sym-metric-bar__track--away">'
            f'<i style="width:{a_pct:.1f}%"></i></div>'
            f'<div class=sym-metric-label>Balance</div>'
            f'<div class="sym-metric-bar__track sym-metric-bar__track--home">'
            f'<i style="width:{h_pct:.1f}%"></i></div></div>'
        )

    a_osi = getattr(gd, "away_osi", None)
    h_osi = getattr(gd, "home_osi", None)
    rows = [
        _sym_row(
            "Win %",
            prob_chip_html(away_win_p, digits=1) if away_win_p else '<span class="c-na">—</span>',
            prob_chip_html(home_win_p, digits=1) if home_win_p else '<span class="c-na">—</span>',
            away_win=away_win_p > home_win_p,
            home_win=home_win_p > away_win_p,
        ),
        win_bar,
        _sym_row(
            "Proj R",
            val_chip_html(away_runs, "team_runs", digits=1),
            val_chip_html(home_runs, "team_runs", digits=1),
            away_win=away_runs > home_runs,
            home_win=home_runs > away_runs,
        ),
        _sym_row(
            "Fair ML",
            f'<span class=mono>{fair_away:+d}</span>' if fair_away is not None else '<span class="c-na">—</span>',
            f'<span class=mono>{fair_home:+d}</span>' if fair_home is not None else '<span class="c-na">—</span>',
        ),
        _sym_row(
            "SP FIP",
            f'<span class=mono>{_fip(getattr(gd, "away_fip", None))}</span>',
            f'<span class=mono>{_fip(getattr(gd, "home_fip", None))}</span>',
            away_win=(
                getattr(gd, "away_fip", None) is not None
                and getattr(gd, "home_fip", None) is not None
                and gd.away_fip < gd.home_fip
            ),
            home_win=(
                getattr(gd, "away_fip", None) is not None
                and getattr(gd, "home_fip", None) is not None
                and gd.home_fip < gd.away_fip
            ),
        ),
    ]
    if not compact:
        rows.extend([
            _sym_row(
                "SP K%",
                _kpct(getattr(gd, "away_k", None)),
                _kpct(getattr(gd, "home_k", None)),
                away_win=(
                    getattr(gd, "away_k", None) is not None
                    and getattr(gd, "home_k", None) is not None
                    and gd.away_k > gd.home_k
                ),
                home_win=(
                    getattr(gd, "away_k", None) is not None
                    and getattr(gd, "home_k", None) is not None
                    and gd.home_k > gd.away_k
                ),
            ),
            _sym_row(
                "OSI",
                val_chip_html(a_osi, "osi", digits=1) if a_osi is not None else '<span class="c-na">—</span>',
                val_chip_html(h_osi, "osi", digits=1) if h_osi is not None else '<span class="c-na">—</span>',
                away_win=a_osi is not None and h_osi is not None and a_osi > h_osi,
                home_win=a_osi is not None and h_osi is not None and h_osi > a_osi,
            ),
            _sym_row(
                "Model / mkt tot",
                f'<span class=mono>{tot:.1f}</span>',
                f'<span class=mono>{_display(ex.get("mkt_total"), digits=1) if ex.get("mkt_total") is not None else "—"}</span>',
            ),
        ])

    factors = ""
    if not compact:
        away_edges, home_edges = [], []
        for a in (r.get("advantage") or [])[:6]:
            side = a.get("edge")
            label = str(a.get("cat") or "").strip()
            if not label:
                continue
            if side == gd.away:
                away_edges.append(label)
            elif side == gd.home:
                home_edges.append(label)
        for f in (r.get("factors") or [])[:8]:
            side = str(f.get("side") or "")
            label = _short_factor(str(f.get("name") or ""))
            if side == gd.away and label not in away_edges:
                away_edges.append(label)
            elif side == gd.home and label not in home_edges:
                home_edges.append(label)
        away_edges = away_edges[:3] or ["—"]
        home_edges = home_edges[:3] or ["—"]
        factors = (
            '<div class=sym-factors>'
            f'<div><div class=sym-factors__title>{esc(gd.away)} edges</div><ul>'
            + "".join(f"<li><b>{esc(x)}</b></li>" for x in away_edges)
            + f'</ul></div><div><div class=sym-factors__title>{esc(gd.home)} edges</div><ul>'
            + "".join(f"<li><b>{esc(x)}</b></li>" for x in home_edges)
            + "</ul></div></div>"
        )

    return f"""<section class="sym-metric-board" aria-label="Symmetric matchup board">
  <div class=sym-metric-board__head>
    <div class="sym-metric-board__team sym-metric-board__team--away">
      <div>
        <div class=mut style="letter-spacing:.14em;text-transform:uppercase;font-size:10px;margin-bottom:4px">Away</div>
        <b>{esc(gd.away)}</b>
        {_sp_block(getattr(gd, "away_sp", None), getattr(gd, "away_hand", ""), getattr(gd, "away_fip", None), getattr(gd, "away_k", None))}
      </div>
      {_logo(gd.away, "tlogo")}
    </div>
    <div class=sym-metric-board__axis>
      <span>VS</span>
      <div class=sym-metric-board__axis-meta>{esc(start)}<br>{park_txt}<br>{esc(wx)}</div>
    </div>
    <div class="sym-metric-board__team sym-metric-board__team--home">
      {_logo(gd.home, "tlogo")}
      <div>
        <div class=mut style="letter-spacing:.14em;text-transform:uppercase;font-size:10px;margin-bottom:4px">Home</div>
        <b>{esc(gd.home)}</b>
        {_sp_block(getattr(gd, "home_sp", None), getattr(gd, "home_hand", ""), getattr(gd, "home_fip", None), getattr(gd, "home_k", None))}
      </div>
    </div>
  </div>
  <div class=sym-metric-board__rows>{"".join(rows)}</div>
  {factors}
</section>"""


def matchup_banner_html(r: dict, esc) -> str:
    """Symmetric banner: team + SP columns flanking a single FG projection; F5 + weather below."""
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
    away_fav = " matchup-banner__side--favored" if favored == gd.away else ""
    home_fav = " matchup-banner__side--favored" if favored == gd.home else ""
    away_k = (
        val_chip_html(gd.away_k, "kpct", digits=1, suffix="% K")
        if gd.away_k else ""
    )
    home_k = (
        val_chip_html(gd.home_k, "kpct", digits=1, suffix="% K")
        if gd.home_k else ""
    )

    return f"""<div class="matchup-banner matchup-banner--v2">
  <div class=matchup-banner__hero>
    <div class="matchup-banner__side matchup-banner__side--away{away_fav}">
      {_logo(gd.away, "tlogo lg")}
      <div class=matchup-banner__side-body>
        <span class=matchup-banner__abbr>{esc(gd.away)}</span>
        <div class=matchup-banner__sp-line>{_headshot(away_id)}<span class=mut>{esc(gd.away_sp)}</span></div>
        {away_k}
      </div>
    </div>
    <div class=matchup-banner__center>
      <span class=matchup-banner__label>Projected score</span>
      <div class=matchup-banner__score>
        <span class=matchup-banner__runs>{val_chip_html(prob.exp_away_runs, "team_runs", digits=1)}</span>
        <span class=matchup-banner__dash>–</span>
        <span class=matchup-banner__runs>{val_chip_html(prob.exp_home_runs, "team_runs", digits=1)}</span>
      </div>
      <div class=matchup-banner__meta>
        {val_chip_html(prob.exp_total, "game_total", digits=1, suffix=" total")}
        <span class=mut>·</span>
        <span>Lean <b class="{lean_cls}">{esc(favored)} {lean_margin:+.1f}</b></span>
      </div>
    </div>
    <div class="matchup-banner__side matchup-banner__side--home{home_fav}">
      <div class=matchup-banner__side-body>
        <span class=matchup-banner__abbr>{esc(gd.home)}</span>
        <div class=matchup-banner__sp-line><span class=mut>{esc(gd.home_sp)}</span>{_headshot(home_id)}</div>
        {home_k}
      </div>
      {_logo(gd.home, "tlogo lg")}
    </div>
  </div>
  <div class="matchup-banner__proj-row matchup-banner__proj-row--duo">
    <div class=matchup-proj-card>
      <span class=k>First 5</span>
      <span class=v>{val_chip_html(f5_away, "team_runs", digits=1)} – {val_chip_html(f5_home, "team_runs", digits=1)}</span>
      <span class=mut>{val_chip_html(f5_total, "game_total", digits=1, suffix=" F5 total")}</span>
    </div>
    <div class=matchup-proj-card>
      <span class=k>Weather · wind</span>
      <span class=v>{esc(_weather_wind_label(weather))}</span>
      {f'<span class=mut>{esc(start)}</span>' if start else ''}
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
    return val_chip_html(value, context, invert=invert, digits=digits, suffix=suffix)


def _pitcher_rl_rows(splits) -> str:
    rows = ""
    for label, key in (("vs LHB", "LHH"), ("vs RHB", "RHH")):
        row = splits.get(key, {})
        rows += (
            f'<tr><td class=mut>{label}</td>'
            f'<td>{_metric_cells(row.get("FIP"), "fip", invert=True)}</td>'
            f'<td>{_metric_cells(row.get("K_pct"), "kpct", digits=1, suffix="%")}</td>'
            f'<td>{_metric_cells(row.get("HR9"), "hr9", invert=True)}</td>'
            f'<td>{_metric_cells(row.get("OPS"), "woba", invert=True, digits=3)}</td></tr>'
        )
    return rows


def _pitcher_ha_rows(splits) -> str:
    rows = ""
    for label, key in (("Away", "away"), ("Home", "home")):
        row = splits.get(key, {})
        rows += (
            f'<tr><td class=mut>{label}</td>'
            f'<td>{_metric_cells(row.get("FIP"), "fip", invert=True)}</td>'
            f'<td>{_metric_cells(row.get("ERA"), "era", invert=True)}</td>'
            f'<td>{_metric_cells(row.get("K_pct"), "kpct", digits=1, suffix="%")}</td>'
            f'<td>{_metric_cells(row.get("F5_ERA"), "era", invert=True)}</td></tr>'
        )
    return rows


def _lineup_rl_rows(prof) -> str:
    return (
        f'<tr><td class=mut>vs LHP</td>'
        f'<td>{_metric_cells(prof.get("osi_vs_lhp"), "osi", digits=0)}</td>'
        f'<td>{_metric_cells(prof.get("abq_vs_lhp"), "abq", digits=0)}</td></tr>'
        f'<tr><td class=mut>vs RHP</td>'
        f'<td>{_metric_cells(prof.get("osi_vs_rhp"), "osi", digits=0)}</td>'
        f'<td>{_metric_cells(prof.get("abq_vs_rhp"), "abq", digits=0)}</td></tr>'
    )


def _lineup_ha_rows(prof) -> str:
    return (
        f'<tr><td class=mut>Road</td>'
        f'<td>{_metric_cells(prof.get("away_osi"), "osi", digits=0)}</td>'
        f'<td>{_metric_cells(prof.get("away_woba"), "woba", digits=3)}</td>'
        f'<td>{_metric_cells(prof.get("away_wrc"), "wrc", digits=0)}</td></tr>'
        f'<tr><td class=mut>Home</td>'
        f'<td>{_metric_cells(prof.get("home_osi"), "osi", digits=0)}</td>'
        f'<td>{_metric_cells(prof.get("home_woba"), "woba", digits=3)}</td>'
        f'<td>{_metric_cells(prof.get("home_wrc"), "wrc", digits=0)}</td></tr>'
    )


def _bullpen_block(prof: dict, pen_factor, pen_features: dict, esc) -> str:
    workload = pen_features.get("pitches_1d", "—")
    return (
        f'<div class=matchup-bullpen-strip>'
        f'<div><span class=k>Run factor</span>{_metric_cells(pen_factor, "park", invert=True, digits=3)}</div>'
        f'<div><span class=k>High-lev ERA</span>{_metric_cells(prof.get("bullpen_high_lev_era"), "era", invert=True)}</div>'
        f'<div><span class=k>Workload</span><span class=mut>{esc(str(workload))} pitches yesterday</span></div>'
        f'</div>'
    )


def _posted_lineup_block(features: dict, source, esc) -> str:
    status = str(features.get("status") or "unavailable")
    if status not in {"confirmed", "projected"}:
        return '<div class=matchup-bullpen-strip><div><span class=k>Status</span><span class=mut>Not posted yet</span></div></div>'
    pill = "pos" if status == "confirmed" else "warnc"
    projected = features.get("projected_osi")
    baseline = features.get("team_baseline_osi")
    matched = features.get("matched_batters") or 0
    factor = features.get("factor")
    factor_html = (
        _metric_cells(factor, "park", digits=3) if factor is not None else "—"
    )
    return (
        f'<div class=matchup-bullpen-strip>'
        f'<div><span class=k>Status</span><span class="pill {pill}">{esc(status)}</span></div>'
        f'<div><span class=k>Order OSI</span>'
        f'{_metric_cells(projected, "osi", digits=0) if projected is not None else "<span class=c-na>—</span>"}'
        f'<span class=mut> vs {esc(str(baseline if baseline is not None else "—"))} team base</span></div>'
        f'<div><span class=k>Run factor</span>{factor_html}'
        f'<span class=mut> · {matched}/9 matched{" · " + esc(str(source)) if source else ""}</span></div>'
        f'</div>'
    )


def _breakdown_team_head(team: str, sp_name: str, side: str, esc) -> str:
    from mlbmodel.report.matchup import _logo

    logo = _logo(team, "tlogo sm")
    meta = f'<div class=matchup-team-col__meta><b>{esc(team)}</b><span class=mut>{esc(sp_name)}</span></div>'
    if side == "home":
        return f'<div class="matchup-team-col__head matchup-team-col__head--{side}">{meta}{logo}</div>'
    return f'<div class="matchup-team-col__head matchup-team-col__head--{side}">{logo}{meta}</div>'


def _breakdown_section_row(label: str, away_body: str, home_body: str) -> str:
    return f"""<div class="matchup-breakdown__row matchup-breakdown__row--section">
  <div class=matchup-breakdown__section-label>{label}</div>
  <div class="matchup-breakdown__lane matchup-breakdown__lane--away"><div class=matchup-breakdown__block>{away_body}</div></div>
  <div class=matchup-breakdown__spine aria-hidden=true></div>
  <div class="matchup-breakdown__lane matchup-breakdown__lane--home"><div class=matchup-breakdown__block>{home_body}</div></div>
</div>"""


def matchup_context_html(r, gd, repo, esc) -> str:
    away_prof = _team_row(repo, gd.away)
    home_prof = _team_row(repo, gd.home)
    away_sp_hand = _sp_metric_split(repo, gd.away_sp, "hand")
    home_sp_hand = _sp_metric_split(repo, gd.home_sp, "hand")
    away_sp_loc = _sp_metric_split(repo, gd.away_sp, "location")
    home_sp_loc = _sp_metric_split(repo, gd.home_sp, "location")

    live_lineups = (getattr(gd, "live_context", None) or {}).get("lineups") or {}
    pitchers = {row.get("team"): row for row in r.get("pitchers", []) if row.get("team")}
    away_mix = pitch_mix_board_html(
        (pitchers.get(gd.away) or {}).get("pitch_matchup") or {},
        compact=True,
        show_title=False,
        show_legend=False,
    )
    home_mix = pitch_mix_board_html(
        (pitchers.get(gd.home) or {}).get("pitch_matchup") or {},
        compact=True,
        show_title=False,
        show_legend=False,
    )

    pitcher_rl_hdr = "<th>Split</th><th>FIP</th><th>K%</th><th>HR/9</th><th>OPS</th>"
    pitcher_ha_hdr = "<th>Split</th><th>FIP</th><th>ERA</th><th>K%</th><th>F5 ERA</th>"
    lineup_rl_hdr = "<th>Split</th><th>OSI</th><th>ABQ</th>"
    lineup_ha_hdr = "<th>Split</th><th>OSI</th><th>wOBA</th><th>wRC+</th>"

    head_row = f"""<div class="matchup-breakdown__row matchup-breakdown__row--head">
  <div class="matchup-breakdown__lane matchup-breakdown__lane--away">{_breakdown_team_head(gd.away, gd.away_sp, "away", esc)}</div>
  <div class=matchup-breakdown__spine matchup-breakdown__spine--vs><span>@</span></div>
  <div class="matchup-breakdown__lane matchup-breakdown__lane--home">{_breakdown_team_head(gd.home, gd.home_sp, "home", esc)}</div>
</div>"""

    rows = [
        head_row,
        _breakdown_section_row(
            "Pitcher R/L",
            _split_table(pitcher_rl_hdr, _pitcher_rl_rows(away_sp_hand), empty_cols=5),
            _split_table(pitcher_rl_hdr, _pitcher_rl_rows(home_sp_hand), empty_cols=5),
        ),
        _breakdown_section_row(
            "Pitcher H/A",
            _split_table(pitcher_ha_hdr, _pitcher_ha_rows(away_sp_loc), empty_cols=5),
            _split_table(pitcher_ha_hdr, _pitcher_ha_rows(home_sp_loc), empty_cols=5),
        ),
        _breakdown_section_row(
            "Lineup R/L",
            _split_table(lineup_rl_hdr, _lineup_rl_rows(away_prof), empty_cols=3),
            _split_table(lineup_rl_hdr, _lineup_rl_rows(home_prof), empty_cols=3),
        ),
        _breakdown_section_row(
            "Lineup H/A",
            _split_table(lineup_ha_hdr, _lineup_ha_rows(away_prof), empty_cols=4),
            _split_table(lineup_ha_hdr, _lineup_ha_rows(home_prof), empty_cols=4),
        ),
        _breakdown_section_row(
            "Posted lineup",
            _posted_lineup_block(
                getattr(gd, "away_lineup_features", None) or {},
                ((live_lineups.get("away") or {}) or {}).get("source"),
                esc,
            ),
            _posted_lineup_block(
                getattr(gd, "home_lineup_features", None) or {},
                ((live_lineups.get("home") or {}) or {}).get("source"),
                esc,
            ),
        ),
        _breakdown_section_row(
            "Bullpen",
            _bullpen_block(away_prof, gd.away_pen_factor, gd.away_bullpen_features, esc),
            _bullpen_block(home_prof, gd.home_pen_factor, gd.home_bullpen_features, esc),
        ),
        _breakdown_section_row(
            "Pitch mix vs lineup",
            f'<div class=matchup-breakdown__mix-tag>vs {esc(gd.home)}</div>{away_mix}',
            f'<div class=matchup-breakdown__mix-tag>vs {esc(gd.away)}</div>{home_mix}',
        ),
    ]

    return f"""<div class=ca-board>{section_head("Matchup breakdown", icon="matchups")}<div class=body>
  <div class=matchup-breakdown-sym>
    {"".join(rows)}
    <p class="pitch-mix-legend pitch-mix-legend--sym">Δ K% = whiff/chase edge · Δ runs = contact shift (green = fewer runs allowed)</p>
  </div>
</div></div>"""


def advantage_panel_html(gd, advantage_rows, esc) -> str:
    if not advantage_rows:
        return ""

    away = str(gd.away or "")
    home = str(gd.home or "")

    def adv_row(a):
        unit, lb = a.get("unit", ""), a.get("lower_better")
        ctx = _adv_ctx(a["cat"])
        digits = _adv_digits(a, unit)
        av = _adv_value_chip(a.get("a_val"), ctx, invert=lb, digits=digits, suffix=unit)
        hv = _adv_value_chip(a.get("h_val"), ctx, invert=lb, digits=digits, suffix=unit)
        base = league_avg_html(a.get("base"), digits=digits, suffix=unit)
        edge = _adv_edge_html(a, away, home, esc)
        away_win = a.get("edge") == away
        home_win = a.get("edge") == home
        label = (
            f'<b>{esc(a["cat"])}</b>'
            f'<span class=sym-metric-label__meta>{base} · {edge}</span>'
        )
        return _sym_row(label, av, hv, away_win=away_win, home_win=home_win)

    rows = "".join(adv_row(a) for a in advantage_rows)
    return (
        f'<div class=ca-board>{section_head("Matchup advantage", icon="matchups")}<div class=body>'
        f'<div class="sym-metric-board sym-metric-board--adv">'
        f'<div class=sym-metric-board__head>'
        f'<div class="sym-metric-board__team sym-metric-board__team--away"><b>{esc(away)}</b></div>'
        f'<div class=sym-metric-board__axis><span>Edge</span></div>'
        f'<div class="sym-metric-board__team sym-metric-board__team--home"><b>{esc(home)}</b></div>'
        f'</div>'
        f'<div class=sym-metric-board__rows>{rows}</div></div></div></div>'
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
        f'<div class=table-scroll><table class=run-impact-table><tr><th>Factor</th><th>Impact</th><th>Affects</th></tr>'
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
            val = row.get("f5_er")
            cell = val_chip_html(val, "prop_er", digits=0) if val is not None else '<span class=c-na>—</span>'
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
            f'<div class=f5-run-line>{val_chip_html(runs_mean, "team_runs", digits=2, suffix=" runs")}</div>'
            f'<div class=f5-sp-line><span class=mut>{esc(sp_name)}</span>'
            f'<span class=mut>R thru 5 · last 5</span></div>'
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
                    team_ops = (
                        f'OPS {val_chip_html(float(ops), "ops", digits=3)} '
                        f'· wOBA {val_chip_html(float(woba), "woba", digits=3)}'
                    )

        stat_cards = []
        prop_ctx = {
            "K": "prop_k",
            "ER": "prop_er",
            "Outs": "prop_outs",
            "H": "prop_h",
            "Fantasy": "fantasy_dk",
        }
        for key, label in (
            ("K", "Strikeouts"),
            ("ER", "Earned runs"),
            ("Outs", "Outs"),
            ("H", "Hits"),
            ("Fantasy", "DK pts"),
        ):
            dist = projections.get(key) or {}
            mean = dist.get("mean")
            if mean is None:
                continue
            ctx = prop_ctx[key]
            stat_cards.append(
                f'<div class=pitcher-stat-card>'
                f'<span class=k>{label}</span>'
                f'<span class=v>{val_chip_html(mean, ctx, digits=1)}</span>'
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
