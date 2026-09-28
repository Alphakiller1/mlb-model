"""DraftKings game lines from ESPN's public scoreboard, in the Odds API event shape.

The Odds API key can run dry mid-slate (2 credits left on 2026-09-28): the deploy
then skipped the game-line fetch, the market board went unpriced, and the build
failed. ESPN's scoreboard carries DraftKings' moneyline, run line and total at no
cost. Only a quote ESPN attributes to DraftKings is used, and it is emitted as an
Odds API event with a single ``draftkings`` bookmaker, so everything downstream
(quotes.build_board, the lean recorder) reads it unchanged.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
TIMEOUT = 30


def _get(url: str) -> dict:
    # ESPN answers a plain agent; a full browser string with an Accept header is refused.
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _num(value) -> float | None:
    try:
        return float(str(value).strip().lstrip("ouOU").replace("+", ""))
    except (TypeError, ValueError):
        return None


def _close(block: dict | None, side: str, key: str):
    side_block = (block or {}).get(side) or {}
    if (side_block.get("close") or {}).get(key) is not None:
        return side_block["close"][key]
    return (side_block.get("open") or {}).get(key)


def events(slate_date: str | None = None) -> list[dict]:
    """Odds-API-shaped events carrying DraftKings h2h, spreads and totals."""
    url = SCOREBOARD
    if slate_date:
        url += "?dates=" + slate_date.replace("-", "")
    data = _get(url)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: list[dict] = []
    for event in data.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        quote = next((o for o in comp.get("odds") or []
                      if str((o.get("provider") or {}).get("name") or "").lower() == "draftkings"), None)
        if not quote:
            continue
        teams = {c.get("homeAway"): (c.get("team") or {}).get("displayName") for c in comp.get("competitors") or []}
        home, away = teams.get("home"), teams.get("away")
        if not home or not away:
            continue
        markets = []
        home_ml = _num(_close(quote.get("moneyline"), "home", "odds"))
        away_ml = _num(_close(quote.get("moneyline"), "away", "odds"))
        if home_ml is not None and away_ml is not None:
            markets.append({"key": "h2h", "outcomes": [
                {"name": home, "price": int(home_ml)}, {"name": away, "price": int(away_ml)}]})
        spread = quote.get("pointSpread") or {}
        h_line, a_line = _num(_close(spread, "home", "line")), _num(_close(spread, "away", "line"))
        h_odds, a_odds = _num(_close(spread, "home", "odds")), _num(_close(spread, "away", "odds"))
        if None not in (h_line, a_line, h_odds, a_odds):
            markets.append({"key": "spreads", "outcomes": [
                {"name": home, "price": int(h_odds), "point": h_line},
                {"name": away, "price": int(a_odds), "point": a_line}]})
        total = quote.get("total") or {}
        over, under = _num(_close(total, "over", "line")), _num(_close(total, "under", "line"))
        o_odds, u_odds = _num(_close(total, "over", "odds")), _num(_close(total, "under", "odds"))
        if None not in (over, under, o_odds, u_odds):
            markets.append({"key": "totals", "outcomes": [
                {"name": "Over", "price": int(o_odds), "point": over},
                {"name": "Under", "price": int(u_odds), "point": under}]})
        if not markets:
            continue
        out.append({
            "id": f"espn:{event.get('id')}",
            "sport_key": "baseball_mlb",
            "commence_time": event.get("date"),
            "home_team": home,
            "away_team": away,
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "last_update": stamp, "markets": markets}],
        })
    return out
