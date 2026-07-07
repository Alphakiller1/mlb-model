"""Prop, fantasy, and market trend detectors — extend situational trends beyond game results."""
from __future__ import annotations

from mlbmodel.trends.types import NEUTRAL, RUN_BOOST, RUN_SUPPRESSION, Trend

# Rough starter priors for z-scoring projection deltas.
_PRIORS = {
    "K": (5.6, 1.8),
    "ER": (2.8, 1.2),
    "Outs": (16.5, 2.5),
    "H": (5.4, 1.6),
    "Fantasy": (18.0, 6.0),
    "PP_Fantasy": (32.0, 9.0),
    "F5_ER": (1.6, 0.9),
}

_PROP_CATEGORY = {
    "K": "prop_strikeouts",
    "BB": "prop_walks",
    "ER": "prop_earned_runs",
    "Outs": "prop_outs",
    "H": "prop_hits",
    "Fantasy": "fantasy_dk",
    "PP_Fantasy": "fantasy_pp",
    "F5_ER": "prop_f5_er",
}

_PROP_LABEL = {
    "K": "Strikeouts",
    "BB": "Walks",
    "ER": "Earned runs",
    "Outs": "Outs",
    "H": "Hits",
    "Fantasy": "DK fantasy",
    "PP_Fantasy": "PrizePicks fantasy",
    "F5_ER": "F5 earned runs",
}


def _z(mean: float, prior: tuple[float, float]) -> float:
    base, sd = prior
    return abs(mean - base) / max(sd, 0.25)


def _confidence_from_trust(trust: str | None, starts: int) -> str:
    if trust == "thin" or starts < 5:
        return "low"
    if starts >= 10:
        return "high"
    return "medium"


def _prop_trend_from_projection(pitcher: dict, prop_key: str) -> Trend | None:
    if pitcher.get("state") == "DATA GAP":
        return None
    projections = pitcher.get("projections") or {}
    dist = projections.get(prop_key) or {}
    mean = dist.get("mean")
    if mean is None:
        return None
    mean = float(mean)
    prior = _PRIORS.get(prop_key)
    if not prior:
        return None
    z = _z(mean, prior)
    pitch_matchup = pitcher.get("pitch_matchup") or {}
    if prop_key == "K":
        k_delta = pitch_matchup.get("k_rate_delta")
        if isinstance(k_delta, (int, float)) and float(k_delta) >= 0.8:
            z = max(z, min(2.2, abs(float(k_delta)) / 0.9))
    if z < 0.55:
        return None
    base, _ = prior
    over = mean >= base
    direction = RUN_BOOST if over else RUN_SUPPRESSION
    name = str(pitcher.get("pitcher") or "SP")
    team = str(pitcher.get("team") or "")
    label = _PROP_LABEL[prop_key]
    side_word = "OVER" if over else "UNDER"
    starts = int((pitcher.get("sample") or {}).get("season_starts") or 0)
    trust = pitcher.get("projection_trust")
    p10, p90 = dist.get("p10"), dist.get("p90")
    band = f" ({p10:.0f}–{p90:.0f})" if isinstance(p10, (int, float)) and isinstance(p90, (int, float)) else ""
    desc = (
        f"{name} projects {mean:.1f} {label.lower()}{band} "
        f"vs {base:.1f} starter prior ({z:.1f}σ)."
    )
    category = _PROP_CATEGORY[prop_key]
    lane_implication = f"{side_word} {label}"
    return Trend(
        trend_id=f"{team}_{name}_{prop_key}_proj".replace(" ", "_"),
        team=team,
        side="away" if team else "away",
        category=category,
        trend_description=desc,
        situation_key=f"{team}|{prop_key}|proj",
        direction=direction,
        sample_size=max(starts, 8),
        effect_size=round(min(2.5, z), 3),
        z_score=round(z if over else -z, 3),
        significance="strong" if z >= 1.2 else ("moderate" if z >= 0.8 else "weak"),
        confidence=_confidence_from_trust(trust, starts),
        key_rate_diffs={f"proj_{prop_key.lower()}": round(mean, 2), "proj_z": round(z, 2)},
        mechanistic_explanation=(
            "Simulation blends skill, recent form, opponent lineup, and pitch-mix response."
        ),
        betting_implications=[
            f"{name} {label} {side_word}",
            f"{team} correlated game script" if prop_key in {"ER", "Outs", "F5_ER"} else "",
        ],
        suggested_model_feature={f"{team}_{prop_key}_proj_z": round(z, 3)},
        data_backed=True,
        relevance=0.88 if trust == "trusted" else 0.55,
    )


def detect_pitcher_prop_trends(pitcher: dict) -> list[Trend]:
    keys = ("K", "ER", "Outs", "H", "Fantasy", "PP_Fantasy", "F5_ER")
    out: list[Trend] = []
    for key in keys:
        trend = _prop_trend_from_projection(pitcher, key)
        if trend is not None:
            # Clean empty implications
            trend.betting_implications = [x for x in trend.betting_implications if x]
            out.append(trend)
    return out


def _normalize_market(market: str) -> str:
    key = str(market or "").lower()
    if key in {"total", "totals", "f5_total"}:
        return "total"
    if key in {"ml", "h2h", "moneyline", "f5_ml"}:
        return "ml"
    if key in {"runline", "spreads", "f5_runline"}:
        return "runline"
    return key or "market"


def detect_market_trends(game: str, away: str, home: str, model_rows: list[dict]) -> list[Trend]:
    out: list[Trend] = []
    for row in model_rows or []:
        edge = row.get("edge")
        model_p = row.get("model")
        if edge is None or model_p is None:
            continue
        try:
            edge_f = float(edge)
            model_f = float(model_p)
        except (TypeError, ValueError):
            continue
        if edge_f < 2.5:
            continue
        market = _normalize_market(str(row.get("market") or ""))
        side = str(row.get("side") or "")
        category = f"market_{market}"
        z = min(2.4, edge_f / 4.0 + abs(model_f - 50.0) / 40.0)
        label = str(row.get("label") or f"{market} {side}")
        price = row.get("mkt")
        price_bit = f" @ {int(price):+d}" if isinstance(price, int) else ""
        desc = f"Model {model_f:.0f}% on {label}{price_bit} ({edge_f:+.1f}pt edge)."
        team = side if side in {away, home} else away
        over = "over" in str(row.get("side") or "").lower() or "OVER" in label.upper()
        under = "under" in str(row.get("side") or "").lower() or "UNDER" in label.upper()
        if market == "total":
            direction = RUN_BOOST if over else (RUN_SUPPRESSION if under else NEUTRAL)
            lean = "OVER" if over else ("UNDER" if under else side)
            implications = [f"Game total {lean}"]
        elif market == "ml":
            direction = RUN_BOOST
            implications = [f"{side} ML value"]
        else:
            direction = RUN_BOOST if edge_f > 0 else RUN_SUPPRESSION
            implications = [label]
        out.append(
            Trend(
                trend_id=f"{game}_{category}_{side}".replace("@", "_"),
                team=team,
                side="home" if team == home else "away",
                category=category,
                trend_description=desc,
                situation_key=f"{game}|{category}|{side}",
                direction=direction,
                sample_size=0,
                effect_size=round(z, 3),
                z_score=round(z, 3),
                significance="strong" if z >= 1.2 else "moderate",
                confidence="medium",
                key_rate_diffs={"model_pct": round(model_f, 1), "edge_pt": round(edge_f, 1)},
                mechanistic_explanation="Priced model edge vs paired market consensus.",
                betting_implications=implications,
                suggested_model_feature={f"{game}_{category}_edge": round(edge_f, 2)},
                data_backed=bool(price),
                relevance=0.75,
            )
        )
    return out


def trends_for_game(
    *,
    situational: list[Trend],
    pitchers: list[dict],
    model_rows: list[dict],
    game: str,
    away: str,
    home: str,
) -> list[Trend]:
    """Merge situational, prop/fantasy, and market trends for one matchup."""
    merged: list[Trend] = list(situational)
    for pitcher in pitchers:
        if str(pitcher.get("team") or "") not in {away, home}:
            continue
        merged.extend(detect_pitcher_prop_trends(pitcher))
    merged.extend(detect_market_trends(game, away, home, model_rows))
    return merged
