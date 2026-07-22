"""Rank slate opportunities and summarize historical edge / CLV / team accuracy."""
from __future__ import annotations

from collections import defaultdict

from mlbmodel.leans.record import edge_points
from mlbmodel.report.decision import MKT_LABEL

MIN_EDGE_PTS = 0.5
_PICKEM_LEAN_PTS = 8.0


def _market_label(market: str) -> str:
    key = str(market or "").lower()
    return MKT_LABEL.get(key, key.replace("_", " ").title())


def _price_str(price) -> str | None:
    if isinstance(price, int):
        return f"{price:+d}"
    return None


def collect_slate_opportunities(
    *,
    pkmap: dict[int, str] | None,
    market_plays: list[dict],
    model_by_pk: dict[int, list[dict]],
    prop_reports: list[dict],
    pickem_rows: list[dict],
) -> list[dict]:
    """Unified, ranked list of today's actionable edges with market lines."""
    pkmap = pkmap or {}
    ops: list[dict] = []
    seen: set[tuple] = set()

    def add(**row: object) -> None:
        key = (
            row.get("game_pk"),
            row.get("category"),
            row.get("market"),
            str(row.get("selection") or "").lower(),
            row.get("line"),
            row.get("price"),
        )
        if key in seen:
            return
        seen.add(key)
        ops.append(row)  # type: ignore[arg-type]

    for play in market_plays:
        verdict = str(play.get("verdict") or "")
        if verdict not in {"STRONG", "BET", "LEAN"}:
            continue
        edge_pts = float(play.get("medge") or 0)
        add(
            score=float(play.get("score") or 0),
            category="sharp",
            game=str(play.get("game") or ""),
            game_pk=play.get("pk"),
            market=str(play.get("mkt_type") or "market"),
            market_label=_market_label(str(play.get("mkt_type") or "")),
            selection=str(play.get("sel") or ""),
            line=play.get("market_line"),
            price=_price_str(play.get("price")),
            model_pct=play.get("model_p"),
            edge_pts=edge_pts,
            state=verdict,
            context="sharp + model fusion",
            book=str(play.get("book") or "") or None,
        )

    for pk, markets in (model_by_pk or {}).items():
        game = pkmap.get(pk, str(pk))
        for market in markets or []:
            edge_pts = edge_points(market.get("edge"))
            state = str(market.get("state") or "")
            actionable = state in {"BET", "MONITOR"}
            has_edge = edge_pts is not None and edge_pts >= MIN_EDGE_PTS
            if not actionable and not has_edge:
                continue
            market_type = str(market.get("market") or "market")
            category = "f5" if market_type.startswith("f5_") else "game"
            score = (edge_pts or 0) + (20 if state == "BET" else 10 if state == "MONITOR" else 0)
            add(
                score=score,
                category=category,
                game=game,
                game_pk=pk,
                market=market_type,
                market_label=_market_label(market_type),
                selection=str(market.get("side") or ""),
                line=market.get("line"),
                price=_price_str(market.get("mkt")),
                model_pct=market.get("model"),
                edge_pts=edge_pts,
                state=state or "EDGE",
                context="model vs live line",
                book=str(market.get("book") or "") or None,
            )

    for item in prop_reports:
        edge_pts = edge_points(item.get("edge"))
        state = str(item.get("state") or "")
        actionable = state in {"BET", "MONITOR"}
        has_edge = edge_pts is not None and edge_pts >= MIN_EDGE_PTS
        if not actionable and not has_edge:
            continue
        pitcher = str(item.get("pitcher") or "")
        prop = str(item.get("prop") or "prop")
        side = str(item.get("side") or "")
        line = item.get("line")
        label = f'{side.title()} {prop} {line:g}' if line is not None else f'{side.title()} {prop}'
        add(
            score=(edge_pts or 0) + (15 if state == "BET" else 8),
            category="prop",
            game="",
            game_pk=item.get("game_pk"),
            market=prop.lower(),
            market_label=prop,
            selection=side,
            line=line,
            price=_price_str(item.get("best_odds")),
            model_pct=(
                float(item["model_probability"]) * 100
                if item.get("model_probability") is not None else None
            ),
            edge_pts=edge_pts,
            state=state or "EDGE",
            context=pitcher,
            book=str(item.get("best_book") or "") or None,
            label=label,
        )

    for item in pickem_rows:
        p_over = item.get("p_over")
        if p_over is None:
            continue
        edge_pts = item.get("edge_pts")
        if edge_pts is None:
            edge_pts = abs(float(p_over) - 0.5) * 100
        lean = str(item.get("lean") or "").upper()
        if lean not in {"OVER", "UNDER"}:
            continue
        prop = str(item.get("prop") or "prop")
        line = item.get("line")
        state = lean if float(edge_pts) >= _PICKEM_LEAN_PTS else "WATCH"
        lean_prob = float(p_over) if lean == "OVER" else 1 - float(p_over)
        add(
            score=float(edge_pts) + (5 if state in {"OVER", "UNDER"} else 0),
            category="pickem",
            game="",
            game_pk=item.get("game_pk"),
            market=prop.lower().replace(" ", "_"),
            market_label=prop,
            selection=lean.lower(),
            line=line,
            price=None,
            model_pct=lean_prob * 100,
            edge_pts=float(edge_pts),
            state=state,
            context=f'{item.get("pitcher")} · {item.get("book", "")}',
            book=str(item.get("book") or "") or None,
        )

    ops.sort(key=lambda row: -(float(row.get("score") or 0)))
    return ops


def clv_from_snapshots(rows: list[dict]) -> dict | None:
    """Mean close-minus-entry probability (CLV) from executable snapshot rows."""
    usable = [
        row for row in rows
        if row.get("entry_prob") is not None and row.get("implied_probability") is not None
    ]
    if not usable:
        return None
    clv_vals = [
        float(row["implied_probability"]) - float(row["entry_prob"])
        for row in usable
    ]
    wins = sum(1 for row in usable if row.get("won"))
    by_market: dict[str, list[float]] = defaultdict(list)
    for row in usable:
        mkt = str(row.get("market_type") or "ml").lower()
        by_market[mkt].append(
            float(row["implied_probability"]) - float(row["entry_prob"])
        )
    market_clv = {
        mkt: round(sum(vals) / len(vals) * 100, 2)
        for mkt, vals in by_market.items()
        if vals
    }
    return {
        "n": len(usable),
        "clv_pts": round(sum(clv_vals) / len(clv_vals) * 100, 2),
        "win_rate": round(wins / len(usable) * 100, 1) if usable else None,
        "by_market": market_clv,
    }


def team_prediction_record(
    lean_rows: list[dict],
    games_by_pk: dict[int, dict] | None = None,
    *,
    min_samples: int = 3,
) -> list[dict]:
    """Hit rate by team for settled ML / F5-ML leans where selection is a team code."""
    games_by_pk = games_by_pk or {}
    teams: dict[str, dict] = defaultdict(lambda: {"w": 0, "l": 0, "p": 0})

    for row in lean_rows:
        if not row.get("settled"):
            continue
        market = str(row.get("market") or "").lower()
        if market not in {"ml", "moneyline", "h2h", "f5_ml"}:
            continue
        team = str(row.get("selection") or "").upper().strip()
        if len(team) != 3:
            continue
        if row.get("push"):
            teams[team]["p"] += 1
        elif row.get("won"):
            teams[team]["w"] += 1
        else:
            teams[team]["l"] += 1

    out = []
    for team, rec in teams.items():
        n = rec["w"] + rec["l"]
        if n < min_samples:
            continue
        out.append({
            "team": team,
            "w": rec["w"],
            "l": rec["l"],
            "p": rec["p"],
            "hit_rate": rec["w"] / n * 100 if n else 0,
            "n": n,
        })
    out.sort(key=lambda row: (-row["hit_rate"], -row["n"]))
    return out


def market_type_record(lean_rows: list[dict], *, min_samples: int = 2) -> list[dict]:
    """Settled performance grouped by market type and source."""
    groups: dict[tuple[str, str], dict] = defaultdict(lambda: {"w": 0, "l": 0, "p": 0, "edge_sum": 0.0, "n_edge": 0})

    for row in lean_rows:
        if not row.get("settled"):
            continue
        market = str(row.get("market") or "unknown").lower()
        source = str(row.get("source") or "unknown")
        key = (source, market)
        if row.get("push"):
            groups[key]["p"] += 1
        elif row.get("won"):
            groups[key]["w"] += 1
        else:
            groups[key]["l"] += 1
        edge = edge_points(row.get("edge"))
        if edge is not None:
            groups[key]["edge_sum"] += edge
            groups[key]["n_edge"] += 1

    out = []
    for (source, market), rec in groups.items():
        n = rec["w"] + rec["l"]
        if n < min_samples:
            continue
        out.append({
            "source": source,
            "market": market,
            "market_label": _market_label(market),
            "w": rec["w"],
            "l": rec["l"],
            "p": rec["p"],
            "hit_rate": rec["w"] / n * 100 if n else 0,
            "avg_edge_pts": (
                rec["edge_sum"] / rec["n_edge"] if rec["n_edge"] else None
            ),
            "n": n,
        })
    out.sort(key=lambda row: (-row["hit_rate"], -row["n"]))
    return out
