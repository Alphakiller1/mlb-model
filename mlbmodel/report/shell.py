"""App shell: desk sidebar, primary desk CSS, and in-page view switching JS."""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path
from zoneinfo import ZoneInfo

from mlbmodel.report.board import BOARD_JS, board_css
from mlbmodel.report.chase_theme import brand_css
from mlbmodel.report.interactive import TABLE_UI_CSS, TABLE_UI_JS

_STATIC = Path(__file__).resolve().parent / "static"
_ET = ZoneInfo("America/New_York")
e = html.escape

NAV = [
    ("matchups", "Matchups"),
    ("trends", "Trends"),
    ("markets", "Markets"),
    ("props", "Props"),
    ("results", "Results"),
    ("research", "Research"),
]


def slate_view_label(slate_date: str | None) -> str:
    """Nav label for the slate landing view — Tomorrow when the board is next day."""
    raw = str(slate_date or "").strip()[:10]
    if not raw:
        return "Today"
    try:
        slate = dt.date.fromisoformat(raw)
    except ValueError:
        return "Slate"
    today = dt.datetime.now(_ET).date()
    if slate == today:
        return "Today"
    if slate == today + dt.timedelta(days=1):
        return "Tomorrow"
    return slate.strftime("%b %d")


def desk_sidebar_html(
    nav_items: list[tuple[str, str, str]],
    *,
    active: str = "today",
    slate_date: str = "",
    meta_lines: list[str] | None = None,
) -> str:
    """Left Terminal Desk rail — product identity lives here, not a Chase top bar."""
    links = "".join(
        f'<button type="button" class="{"on" if key == active else ""}" '
        f'data-v="{e(key)}" onclick="{onclick}">{e(label)}</button>'
        for key, label, onclick in nav_items
    )
    meta = meta_lines or [
        f'Slate <b>{e(slate_date or "—")}</b>',
        "Model <b>v1-expected-runs</b>",
        "Mode <b>Paper desk</b>",
    ]
    return (
        '<aside class="sidebar" aria-label="MLB Model">'
        '<div class="brand">'
        '<div class="brand__mark">Chase <span>Analytics</span></div>'
        '<div class="brand__sub">MLB Model</div>'
        "</div>"
        f'<nav class="nav">{links}</nav>'
        f'<div class="nav__meta">{"<br>".join(meta)}</div>'
        "</aside>"
    )


def shell_css() -> str:
    """Brand tokens first, then the desk layout, then the shared board.

    Order matters: chase_tokens.css must land before desk_app.css so the desk's local
    names (--ink, --panel, --line …) resolve to Chase values instead of forking the palette.
    """
    desk = (_STATIC / "desk_app.css").read_text(encoding="utf-8")
    return brand_css() + desk + board_css() + TABLE_UI_CSS


def shell_js() -> str:
    return (
        "function show(k){document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));"
        "document.getElementById('v-'+k).classList.add('on');"
        "document.querySelectorAll('.sidebar .nav button').forEach(b=>b.classList.toggle('on',b.dataset.v===k));"
        "if(location.hash!=='#'+k)history.replaceState(null,'','#'+k);"
        "window.scrollTo(0,0);}"
        "function switchGame(g){document.querySelectorAll('.matchup-report').forEach(function(x){"
        "var on=x.getAttribute('data-game')===g;"
        "if(on){x.removeAttribute('hidden');}else{x.setAttribute('hidden','');}"
        "if(on){var body=x.querySelector('.matchup-body');var tpl=x.querySelector('template.matchup-full-src');"
        "if(body&&tpl&&body.querySelector('.matchup-summary'))body.innerHTML=tpl.innerHTML;}"
        "});const s=document.getElementById('gameSelect');"
        "if(s)s.value=g;}"
        # The board and the breakdown now live in one section, so opening a game swaps the
        # detail panel and scrolls to it rather than switching views out from under the board.
        "function openGame(g){show('matchups');switchGame(g);"
        "var d=document.getElementById('matchupDetail');"
        "if(d)d.scrollIntoView({behavior:'smooth',block:'start'});}"
        "function switchPropPitcher(i){document.querySelectorAll('[data-prop-detail]').forEach(function(p){"
        "if(p.getAttribute('data-prop-detail')===String(i)){p.removeAttribute('hidden');}else{p.setAttribute('hidden','');}});"
        "document.querySelectorAll('[data-prop-index]').forEach(function(b){"
        "b.classList.toggle('active',b.getAttribute('data-prop-index')===String(i));});}"
        "function togglePitcherCard(i){const c=document.getElementById('prop-card-'+i);"
        "if(c){c.classList.toggle('on');const b=c.querySelector('.pitcher-prop-head');"
        "if(b)b.setAttribute('aria-expanded',c.classList.contains('on')?'true':'false');}}"
        "function switchTrendGame(g){document.querySelectorAll('.trend-matchup-panel').forEach(function(p){"
        "if(p.getAttribute('data-game')===g){p.removeAttribute('hidden');}else{p.setAttribute('hidden','');}"
        "});const s=document.getElementById('trendGameSelect');if(s)s.value=g;}"
        "function togglePitcher(i){togglePitcherCard(i);}"
        "function showReportTab(b,k){const r=b.closest('.rtabs');"
        "r.querySelectorAll('.rtabbar button').forEach(x=>x.classList.remove('on'));"
        "r.querySelectorAll('.pn').forEach(x=>x.classList.remove('on'));"
        "b.classList.add('on');r.querySelector('[data-panel=\"'+k+'\"]').classList.add('on');}"
        "document.addEventListener('keydown',function(ev){"
        "if(ev.target.tagName==='INPUT'||ev.target.tagName==='TEXTAREA'||ev.target.tagName==='SELECT')return;"
        "var btns=Array.prototype.slice.call(document.querySelectorAll('.sidebar .nav button'));"
        "var i=btns.findIndex(function(b){return b.classList.contains('on');});"
        "if(ev.key==='ArrowDown'||ev.key==='ArrowRight'){ev.preventDefault();"
        "var n=btns[(i+1)%btns.length];if(n)n.click();}"
        "if(ev.key==='ArrowUp'||ev.key==='ArrowLeft'){ev.preventDefault();"
        "var p=btns[(i-1+btns.length)%btns.length];if(p)p.click();}});"
        "var boot=(location.hash||'').replace(/^#/,'');"
        "if(boot&&document.getElementById('v-'+boot))show(boot);"
        + BOARD_JS
        + TABLE_UI_JS
    )
