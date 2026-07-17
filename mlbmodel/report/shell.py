"""App shell: navigation, layout CSS, and in-page view switching JS."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from mlbmodel.report.interactive import TABLE_UI_CSS, TABLE_UI_JS

_STATIC = Path(__file__).resolve().parent / "static"
_ET = ZoneInfo("America/New_York")

NAV = [
    ("today", "Today"),
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

_SHELL_BASE = """
body{padding:0;min-height:100vh}
#main{max-width:1240px;margin:0 auto;padding:26px 28px 72px}
.view{display:none}.view.on{display:block;animation:viewin .28s ease both}
@keyframes viewin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){.view.on{animation:none}.card{transition:none}}
#main>.view>h2:first-child{font-family:var(--display);font-weight:800;font-size:var(--mm-text-hero);font-variation-settings:'wdth' 125;
letter-spacing:-.02em;margin:0 0 6px;line-height:1.02;text-transform:uppercase;color:var(--text)}
.pagehead h2{color:var(--text)}
#main>.view>h2:first-child::before,.pagehead h2::before{content:"Chase Analytics · MLB Intelligence";display:block;
font-family:var(--display);font-weight:700;font-size:var(--mm-text-2xs);letter-spacing:.22em;text-transform:uppercase;
color:var(--gold);margin-bottom:9px}
.ctx{color:var(--muted);font-size:var(--mm-text-sm);margin-bottom:10px;line-height:1.35}
.note{color:var(--muted);font-size:var(--mm-text-xs);margin-top:6px;line-height:1.35}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}
.card{position:relative;background:linear-gradient(180deg,var(--ca-board-top, #181B26),var(--ca-board-bottom, #12141D));
border:1px solid var(--border-soft);border-radius:16px;
padding:14px 16px 13px;overflow:hidden;box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 14px 38px rgba(0,0,0,.45);
transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:var(--v-grad);opacity:.8}
.card:hover{transform:translateY(-2px);border-color:var(--border-violet);
box-shadow:0 16px 44px rgba(0,0,0,.55),0 0 0 1px rgba(196,176,255,.10),0 0 26px rgba(124,77,255,.14)}
.card .k{color:var(--muted);font-size:var(--mm-text-2xs);text-transform:uppercase;letter-spacing:.13em;font-weight:800}
.card .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:var(--mm-text-3xl);font-variation-settings:'wdth' 120;
margin-top:6px;line-height:1.05;letter-spacing:-.01em}
.cols{display:grid;grid-template-columns:1.4fr 1fr;gap:12px;align-items:start}
.empty{color:var(--muted);font-size:var(--mm-text-sm);padding:14px 16px;border:1px dashed var(--border-2);border-radius:12px;
background:linear-gradient(180deg,rgba(24,26,42,.5),rgba(5,6,12,.5))}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.gcell{display:inline-flex;align-items:center;gap:5px}
.gamepick{border:0;background:none;color:inherit;font:inherit;padding:0;cursor:pointer;text-align:left}
.gamepick:hover b{color:var(--v-light)}
.viewhero-sub{color:var(--muted);font-size:var(--mm-text-sm);margin:0 0 16px;letter-spacing:.02em}
.viewhero-sub b{color:var(--ink);font-family:var(--display);font-weight:700}
.vh-dot{display:inline-block;width:3px;height:3px;border-radius:50%;background:var(--ca-purple);margin:0 10px;vertical-align:2px}
.edge-cat,.edge-ctx .edge-cat{display:block;font-family:var(--display);font-weight:700;font-size:var(--mm-text-2xs);
color:var(--muted);text-transform:uppercase;letter-spacing:.12em;margin-top:3px}
.edge-ctx{color:var(--ink2)}
.edge-book{color:var(--muted);font-size:var(--mm-text-xs)}
.edge-viz{display:inline-flex;align-items:center;gap:9px;justify-content:flex-end}
.edge-viz-track{width:76px;height:6px;border-radius:4px;background:rgba(255,255,255,.07);overflow:hidden;flex:0 0 auto}
.edge-viz-track i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,#5B2BE0,#9A6BFF)}
.edge-viz b{font-family:var(--display);font-weight:800;min-width:48px;text-align:right}
@media(max-width:760px){.edge-viz-track{width:44px}}
.pagehead{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:16px}
.pagehead h2{font-family:var(--display);font-weight:800;font-size:var(--mm-text-hero);font-variation-settings:'wdth' 125;letter-spacing:-.02em;margin:0 0 5px;line-height:1.02;text-transform:uppercase}
.pagehead-sub{margin:0;font-size:var(--mm-text-sm);color:var(--muted);letter-spacing:.04em;text-transform:uppercase}
.pagehead .ctx{margin:0}
.pagehead select{min-width:200px;background:var(--bg-2);color:var(--ink);border:1px solid var(--border-soft);border-radius:11px;
padding:10px 38px 10px 14px;font:600 var(--mm-text-base) var(--sans);transition:border-color .15s ease;cursor:pointer;
appearance:none;-webkit-appearance:none;
background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'><path d='M1 1.5 6 6.5 11 1.5' fill='none' stroke='%239A6BFF' stroke-width='2' stroke-linecap='round'/></svg>");
background-repeat:no-repeat;background-position:right 14px center}
.pagehead select:hover{border-color:var(--border-violet)}
*{scrollbar-width:thin;scrollbar-color:rgba(124,77,255,.35) transparent}
.table-scroll::-webkit-scrollbar{height:8px;width:8px}
.table-scroll::-webkit-scrollbar-thumb{background:rgba(124,77,255,.3);border-radius:8px}
.table-scroll::-webkit-scrollbar-track{background:transparent}
.site-footer{max-width:1240px;margin:52px auto 0;padding:26px 28px 40px;border-top:1px solid var(--border-soft)}
.site-footer__brand{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.site-footer__brand svg{flex:0 0 auto}
.site-footer__mark{font-family:var(--font-wordmark,'Oswald');font-style:italic;font-weight:700;font-size:var(--mm-text-md);letter-spacing:.05em;color:var(--ink)}
.site-footer__mark em{font-style:italic;background:linear-gradient(90deg,#C4B0FF,#9A6BFF);-webkit-background-clip:text;background-clip:text;color:transparent}
.site-footer__tag{color:var(--muted);font-size:var(--mm-text-xs);letter-spacing:.1em;text-transform:uppercase;font-family:var(--display)}
.site-footer p{color:var(--muted);font-size:var(--mm-text-xs);line-height:1.65;max-width:880px;margin:0 0 8px}
.site-footer a{color:var(--v-light)}
.site-footer__links{display:flex;flex-wrap:wrap;gap:7px 18px;margin-top:12px;font-size:var(--mm-text-xs)}
.matchup-report[hidden],.trend-matchup-panel[hidden]{display:none!important}
.matchup-summary .cards{margin-top:12px}
.deployment-notice{position:relative;border:1px solid var(--border-violet);border-radius:12px;padding:11px 14px 11px 16px;
background:linear-gradient(135deg,rgba(124,77,255,.12),rgba(45,212,191,.04));color:var(--ink2);font-size:var(--mm-text-sm);margin-bottom:18px;overflow:hidden}
.deployment-notice::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(180deg,var(--v-light),var(--teal))}
.empty ul{margin:8px 0 0;padding-left:18px}.empty li{margin:3px 0}
.pitcher-prop-deck{display:flex;flex-direction:column;gap:10px}
.pitcher-prop-card{border:1px solid var(--border-soft);border-radius:16px;overflow:hidden;
background:linear-gradient(180deg,var(--ca-board-top,#181A2A),var(--ca-board-bottom,#05060C));
box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 10px 30px rgba(0,0,0,.4);transition:border-color .16s ease}
.pitcher-prop-card:hover,.pitcher-prop-card.on{border-color:var(--border-violet)}
.pitcher-prop-head{width:100%;display:flex;align-items:center;gap:12px;padding:12px 14px;border:0;background:transparent;color:inherit;
font:inherit;text-align:left;cursor:pointer;transition:background .15s ease}
.pitcher-prop-head:hover{background:rgba(124,77,255,.06)}
.pitcher-prop-id{display:flex;align-items:center;gap:10px;flex:1;min-width:0}
.pitcher-prop-id b{display:block;font-family:var(--display);font-size:var(--mm-text-lg)}
.pitcher-prop-meta{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:var(--mm-text-xs);margin-top:3px;flex-wrap:wrap}
.pitcher-prop-summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:var(--mm-text-xs);color:var(--ink2)}
.pitcher-prop-summary b{font-family:var(--display);color:var(--ink)}
.pitcher-prop-chevron{color:var(--muted);font-size:var(--mm-text-md);transition:transform .2s ease;flex:0 0 auto}
.pitcher-prop-card.on .pitcher-prop-chevron{transform:rotate(90deg)}
.pitcher-prop-body{display:none;padding:0 14px 14px;border-top:1px solid var(--border-2)}
.pitcher-prop-card.on .pitcher-prop-body{display:block}
.prop-proj-strip{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 10px}
.prop-chip{display:flex;flex-direction:column;gap:2px;padding:8px 10px;border:1px solid var(--border-2);border-radius:10px;
background:rgba(6,10,18,.45);min-width:88px}
.prop-chip>b{font:800 var(--mm-text-xl) var(--display)}
.prop-chip>i{font-size:var(--mm-text-xs);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:800}
.pitcher-prop-body .ca-board{margin-top:10px}
.pitcher-cell{display:flex;align-items:center;gap:9px;min-width:190px}.pitcher-cell .phead{width:40px;height:40px;flex:0 0 40px}
.pitcher-cell>div>span{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:var(--mm-text-xs);margin-top:3px}
.prop-range{display:block;font-size:var(--mm-text-2xs);color:var(--muted);white-space:nowrap}.prop-mkt{display:block;font-size:var(--mm-text-2xs);margin-top:3px;white-space:nowrap}
.prop-sub{display:block;color:var(--muted);font-size:var(--mm-text-2xs);margin-top:4px}
.detail-strip{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:var(--mm-text-xs);margin:0 0 10px}
.detail-strip b{color:var(--ink)}
.matchup-context-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:900px){.matchup-context-grid{grid-template-columns:1fr}}
.matchup-env-strip{display:flex;flex-wrap:wrap;gap:12px 18px;padding:10px 0 4px;font-size:var(--mm-text-sm);color:var(--ink2)}
.matchup-env-strip b{color:var(--ink);font-family:var(--display)}
.edge-command{margin-bottom:18px}
/* Command deck — stats as typography on one glass strip, not four boxed wells. */
.edge-hero{position:relative;overflow:hidden;display:grid;grid-template-columns:1.45fr 1fr 1fr 1.25fr;
margin-bottom:16px;border:1px solid var(--border-soft);border-radius:18px;
background:linear-gradient(180deg,rgba(24,26,42,.62),rgba(5,6,12,.38));
box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 20px 50px rgba(0,0,0,.5)}
.edge-hero::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;
background:linear-gradient(90deg,transparent,#7C4DFF 22%,#C4B0FF 50%,#7C4DFF 78%,transparent);opacity:.9}
.edge-hero-stat{position:relative;padding:20px 24px 17px;border-left:1px solid var(--border-soft);min-width:0}
.edge-hero-stat:first-child{border-left:0}
.edge-hero-stat .k{display:block;color:var(--gold);font-family:var(--display);font-size:var(--mm-text-2xs);
text-transform:uppercase;letter-spacing:.2em;font-weight:700}
.edge-hero-stat b{display:block;font:800 40px var(--display);font-variation-settings:'wdth' 120;
letter-spacing:-.015em;line-height:1;margin-top:8px;font-variant-numeric:tabular-nums}
.edge-hero-stat b u{text-decoration:none;font-size:var(--mm-text-lg);font-weight:700;color:var(--muted);margin-left:2px}
.edge-hero-stat--lead b{font-size:46px}
.edge-hero-stat i{display:block;color:var(--muted);font-size:var(--mm-text-2xs);font-style:normal;margin-top:6px;
letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media(max-width:880px){.edge-hero{grid-template-columns:repeat(2,1fr)}
.edge-hero-stat{padding:15px 18px 13px}
.edge-hero-stat:nth-child(odd){border-left:0}
.edge-hero-stat:nth-child(n+3){border-top:1px solid var(--border-soft)}
.edge-hero-stat b{font-size:30px}.edge-hero-stat--lead b{font-size:34px}}
.trend-sig{text-align:left;color:var(--ink2);font-size:var(--mm-text-sm);max-width:560px;white-space:normal;line-height:1.4}
.edge-row{display:flex;gap:18px;margin:2px 0 14px}.edge-cell{flex:1;min-width:0}
.edge-cell .k{color:var(--muted);font-size:var(--mm-text-2xs);text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.edgebar{position:relative;height:20px;margin-top:5px;background:rgba(255,255,255,.06);border-radius:6px;overflow:hidden}
.edgebar i{position:absolute;left:0;top:0;height:100%;background:linear-gradient(90deg,rgba(124,77,255,.5),var(--teal));border-radius:6px}
.edgebar b{position:absolute;right:8px;top:0;line-height:20px;font-family:var(--display);font-weight:800;font-size:var(--mm-text-sm)}
.trend-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px}
.trend-list li{font-size:var(--mm-text-sm);line-height:1.5;color:var(--ink2);padding-left:2px}
.trend-list .pill{margin-right:6px;vertical-align:middle}
.chase-nav-link:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
@media(max-width:760px){.cards{grid-template-columns:repeat(2,1fr)}.pagehead{flex-direction:column;align-items:stretch}.pagehead select{width:100%}
.pitcher-prop-head{flex-wrap:wrap}
.pitcher-prop-summary{width:100%;padding-top:4px}
.prop-proj-strip{gap:6px}.prop-chip{min-width:calc(50% - 6px);flex:1}}
"""


def shell_css() -> str:
    model_ui = (_STATIC / "model_ui.css").read_text(encoding="utf-8")
    return _SHELL_BASE + TABLE_UI_CSS + model_ui


def shell_js() -> str:
    return (
        "function show(k){document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));"
        "document.getElementById('v-'+k).classList.add('on');"
        "document.querySelectorAll('.chase-nav-link').forEach(b=>b.classList.toggle('active',b.dataset.v===k));"
        "if(location.hash!=='#'+k)history.replaceState(null,'','#'+k);"
        "window.scrollTo(0,0);}"
        "function switchGame(g){document.querySelectorAll('.matchup-report').forEach(function(x){"
        "var on=x.getAttribute('data-game')===g;"
        "if(on){x.removeAttribute('hidden');}else{x.setAttribute('hidden','');}"
        "if(on){var body=x.querySelector('.matchup-body');var tpl=x.querySelector('template.matchup-full-src');"
        "if(body&&tpl&&body.querySelector('.matchup-summary'))body.innerHTML=tpl.innerHTML;}"
        "});const s=document.getElementById('gameSelect');"
        "if(s)s.value=g;}"
        "function openGame(g){switchGame(g);show('matchups');}"
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
        "if(ev.target.tagName==='INPUT'||ev.target.tagName==='TEXTAREA')return;"
        "var btns=Array.prototype.slice.call(document.querySelectorAll('.chase-nav-link'));"
        "var i=btns.findIndex(function(b){return b.classList.contains('active');});"
        "if(ev.key==='ArrowDown'||ev.key==='ArrowRight'){ev.preventDefault();"
        "var n=btns[(i+1)%btns.length];if(n)n.click();}"
        "if(ev.key==='ArrowUp'||ev.key==='ArrowLeft'){ev.preventDefault();"
        "var p=btns[(i-1+btns.length)%btns.length];if(p)p.click();}});"
        "var boot=(location.hash||'').replace(/^#/,'');"
        "if(boot&&document.getElementById('v-'+boot))show(boot);"
        + TABLE_UI_JS
    )
