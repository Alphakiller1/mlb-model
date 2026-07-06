"""App shell: navigation, layout CSS, and in-page view switching JS."""
from __future__ import annotations

from pathlib import Path

from mlbmodel.report.interactive import TABLE_UI_CSS, TABLE_UI_JS

_STATIC = Path(__file__).resolve().parent / "static"

NAV = [
    ("today", "Today"),
    ("matchups", "Matchups"),
    ("trends", "Trends"),
    ("markets", "Markets"),
    ("props", "Props"),
    ("results", "Results"),
    ("research", "Research"),
]

_SHELL_BASE = """
body{padding:0;min-height:100vh}
#main{max-width:1240px;margin:0 auto;padding:26px 28px 72px}
.view{display:none}.view.on{display:block;animation:viewin .28s ease both}
@keyframes viewin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){.view.on{animation:none}.card{transition:none}}
#main>.view>h2:first-child{font-family:var(--display);font-weight:800;font-size:30px;font-variation-settings:'wdth' 125;
letter-spacing:-.02em;margin:0 0 5px;line-height:1.05}
.ctx{color:var(--muted);font-size:12px;margin-bottom:10px;line-height:1.35}
.note{color:var(--muted);font-size:11px;margin-top:6px;line-height:1.35}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}
.card{position:relative;background:linear-gradient(180deg,var(--ca-board-top, #181B26),var(--ca-board-bottom, #12141D));
border:2px solid var(--ca-panel-border, var(--border-violet));border-radius:14px;
padding:12px 14px 11px;overflow:hidden;box-shadow:var(--ca-card-shadow);
transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:var(--v-grad);opacity:.7}
.card:hover{transform:translateY(-2px);border-color:var(--ca-panel-border);
box-shadow:0 10px 34px rgba(0,0,0,.5),0 0 0 1px rgba(196,176,255,.12)}
.card .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.card .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:24px;font-variation-settings:'wdth' 120;
margin-top:4px;line-height:1.05;letter-spacing:-.01em}
.cols{display:grid;grid-template-columns:1.4fr 1fr;gap:12px;align-items:start}
.empty{color:var(--muted);font-size:12px;padding:12px;border:1px dashed var(--border-2);border-radius:8px}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.gcell{display:inline-flex;align-items:center;gap:5px}
.gamepick{border:0;background:none;color:inherit;font:inherit;padding:0;cursor:pointer;text-align:left}
.gamepick:hover b{color:var(--teal)}
.pagehead{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:16px}
.pagehead h2{font-family:var(--display);font-weight:800;font-size:30px;font-variation-settings:'wdth' 125;letter-spacing:-.02em;margin:0 0 5px;line-height:1.05}
.pagehead .ctx{margin:0}
.pagehead select{min-width:180px;background:var(--card);color:var(--ink);border:1px solid var(--border-2);border-radius:10px;padding:10px 13px;font:600 13px var(--sans);transition:border-color .15s ease}
.pagehead select:hover{border-color:var(--ca-panel-border)}
.matchup-report{display:none}.matchup-report.on{display:block}
.matchup-summary .cards{margin-top:12px}
.deployment-notice{position:relative;border:1px solid var(--border-violet);border-radius:12px;padding:11px 14px 11px 16px;
background:linear-gradient(135deg,rgba(124,77,255,.12),rgba(45,212,191,.04));color:var(--ink2);font-size:12px;margin-bottom:18px;overflow:hidden}
.deployment-notice::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(180deg,var(--v-light),var(--teal))}
.empty ul{margin:8px 0 0;padding-left:18px}.empty li{margin:3px 0}
.pitcher-prop-deck{display:flex;flex-direction:column;gap:10px}
.pitcher-prop-card{border:2px solid var(--ca-panel-border,var(--border-violet));border-radius:16px;overflow:hidden}
.pitcher-prop-head{width:100%;display:flex;align-items:center;gap:12px;padding:12px 14px;border:0;background:transparent;color:inherit;
font:inherit;text-align:left;cursor:pointer;transition:background .15s ease}
.pitcher-prop-head:hover{background:rgba(124,77,255,.06)}
.pitcher-prop-id{display:flex;align-items:center;gap:10px;flex:1;min-width:0}
.pitcher-prop-id b{display:block;font-family:var(--display);font-size:15px}
.pitcher-prop-meta{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:11px;margin-top:3px;flex-wrap:wrap}
.pitcher-prop-summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--ink2)}
.pitcher-prop-summary b{font-family:var(--display);color:var(--ink)}
.pitcher-prop-chevron{color:var(--muted);font-size:14px;transition:transform .2s ease;flex:0 0 auto}
.pitcher-prop-card.on .pitcher-prop-chevron{transform:rotate(90deg)}
.pitcher-prop-body{display:none;padding:0 14px 14px;border-top:1px solid var(--border-2)}
.pitcher-prop-card.on .pitcher-prop-body{display:block}
.prop-proj-strip{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 10px}
.prop-chip{display:flex;flex-direction:column;gap:2px;padding:8px 10px;border:1px solid var(--border-2);border-radius:10px;
background:rgba(6,10,18,.45);min-width:88px}
.prop-chip>b{font:800 17px var(--display)}
.prop-chip>i{font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:800}
.pitcher-prop-body .ca-board{margin-top:10px}
.pitcher-cell{display:flex;align-items:center;gap:9px;min-width:190px}.pitcher-cell .phead{width:40px;height:40px;flex:0 0 40px}
.pitcher-cell>div>span{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:11px;margin-top:3px}
.prop-range{display:block;font-size:10px;color:var(--muted);white-space:nowrap}.prop-mkt{display:block;font-size:10px;margin-top:3px;white-space:nowrap}
.prop-sub{display:block;color:var(--muted);font-size:10px;margin-top:4px}
.detail-strip{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin:0 0 10px}
.detail-strip b{color:var(--ink)}
.matchup-context-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:900px){.matchup-context-grid{grid-template-columns:1fr}}
.matchup-env-strip{display:flex;flex-wrap:wrap;gap:12px 18px;padding:10px 0 4px;font-size:12px;color:var(--ink2)}
.matchup-env-strip b{color:var(--ink);font-family:var(--display)}
.edge-command{margin-bottom:18px}
.edge-hero{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.edge-hero-stat{position:relative;background:linear-gradient(180deg,var(--ca-board-top,#181B26),var(--ca-board-bottom,#12141D));
border:2px solid var(--ca-panel-border,var(--border-violet));border-radius:14px;padding:14px 16px;box-shadow:var(--ca-card-shadow)}
.edge-hero-stat .k{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em;font-weight:800}
.edge-hero-stat b{display:block;font:800 24px var(--display);margin-top:4px}
.edge-hero-stat i{display:block;color:var(--muted);font-size:10px;font-style:normal;margin-top:4px}
@media(max-width:880px){.edge-hero{grid-template-columns:repeat(2,1fr)}}
.trend-sig{text-align:left;color:var(--ink2);font-size:12.5px;max-width:560px;white-space:normal;line-height:1.4}
.edge-row{display:flex;gap:18px;margin:2px 0 14px}.edge-cell{flex:1;min-width:0}
.edge-cell .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.edgebar{position:relative;height:20px;margin-top:5px;background:rgba(255,255,255,.06);border-radius:6px;overflow:hidden}
.edgebar i{position:absolute;left:0;top:0;height:100%;background:linear-gradient(90deg,rgba(124,77,255,.5),var(--teal));border-radius:6px}
.edgebar b{position:absolute;right:8px;top:0;line-height:20px;font-family:var(--display);font-weight:800;font-size:12px}
.trend-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px}
.trend-list li{font-size:12.5px;line-height:1.5;color:var(--ink2);padding-left:2px}
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
        "function switchGame(g){document.querySelectorAll('.matchup-report').forEach(x=>{"
        "const on=x.dataset.game===g;x.classList.toggle('on',on);"
        "if(on){const body=x.querySelector('.matchup-body');const tpl=x.querySelector('template.matchup-full-src');"
        "if(body&&tpl&&body.querySelector('.matchup-summary'))body.innerHTML=tpl.innerHTML;}"
        "});const s=document.getElementById('gameSelect');"
        "if(s)s.value=g;}"
        "function openGame(g){switchGame(g);show('matchups');}"
        "function togglePitcherCard(i){const c=document.getElementById('prop-card-'+i);"
        "if(c){c.classList.toggle('on');const b=c.querySelector('.pitcher-prop-head');"
        "if(b)b.setAttribute('aria-expanded',c.classList.contains('on')?'true':'false');}}"
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
