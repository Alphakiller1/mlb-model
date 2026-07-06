"""App shell: navigation, layout CSS, and in-page view switching JS."""
from __future__ import annotations

from mlbmodel.report.interactive import TABLE_UI_CSS, TABLE_UI_JS

NAV = [
    ("today", "Today"),
    ("matchups", "Matchups"),
    ("trends", "Trends"),
    ("markets", "Markets"),
    ("props", "Props"),
    ("portfolio", "Portfolio"),
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
.ctx{color:var(--muted);font-size:13px;margin-bottom:18px}
.note{color:var(--muted);font-size:11.5px;margin-top:10px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin-bottom:16px}
.card{position:relative;background:var(--ca-panel-glass);border:1px solid var(--border-2);border-radius:14px;
padding:15px 16px 14px;overflow:hidden;box-shadow:var(--ca-card-shadow);
transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:var(--v-grad);opacity:.7}
.card:hover{transform:translateY(-2px);border-color:var(--ca-panel-border);
box-shadow:0 10px 34px rgba(0,0,0,.5),0 0 0 1px rgba(196,176,255,.12)}
.card .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em;font-weight:800}
.card .v{color:var(--ink);font-family:var(--display);font-weight:800;font-size:26px;font-variation-settings:'wdth' 120;
margin-top:4px;line-height:1.05;letter-spacing:-.01em}
.cols{display:grid;grid-template-columns:1.4fr 1fr;gap:14px;align-items:start}
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
.empty{color:var(--muted);font-size:13px;padding:18px;border:1px dashed var(--border-2);border-radius:8px}
.empty ul{margin:8px 0 0;padding-left:18px}.empty li{margin:3px 0}
.prop-table{min-width:720px}.prop-main{cursor:pointer}.prop-main:hover{background:rgba(124,77,255,.06)}
.prop-table th:first-child,.prop-table td:first-child{position:sticky;left:0;z-index:2;background:var(--card)}
.prop-table th:first-child{z-index:3}.prop-main:hover td:first-child{background:#181A27}
.pitcher-cell{display:flex;align-items:center;gap:9px;min-width:190px}.pitcher-cell .phead{width:40px;height:40px;flex:0 0 40px}
.pitcher-cell>div>span{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:11px;margin-top:3px}
.starter-base{min-width:88px}.starter-base b{display:block}.starter-base span{display:block;color:var(--muted);font-size:10px;margin-top:2px;white-space:nowrap}
.prop-cell{min-width:82px}.prop-cell>b{display:block;font:800 17px var(--display)}
.prop-range{display:block;font-size:10px;color:var(--muted);white-space:nowrap}.prop-mkt{display:block;font-size:10px;margin-top:3px;white-space:nowrap}
.prop-sub{display:block;color:var(--muted);font-size:10px;margin-top:4px}
.prop-detail{display:none;background:rgba(6,10,18,.6)}.prop-detail.on{display:table-row}
.prop-detail>td{padding:14px!important}.prop-detail-grid{display:grid;grid-template-columns:1fr;gap:12px}
.detail-strip{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin:0 0 10px}
.detail-strip b{color:var(--ink)}
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
.prop-board .table-scroll{overflow:visible}
.prop-board .prop-table{min-width:0;width:100%;border-collapse:separate;border-spacing:0}
.prop-board .prop-table thead{display:none}
.prop-board .prop-table tbody{display:flex;flex-direction:column;gap:12px}
.prop-board .prop-table tr.prop-main{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px;padding:14px 14px 12px;
border:1px solid var(--border-2);border-radius:14px;background:var(--card);box-shadow:var(--ca-card-shadow)}
.prop-board .prop-table tr.prop-main td{display:block;position:static!important;background:transparent!important;
min-width:0;padding:0;border:0}
.prop-board .prop-table tr.prop-main td:first-child{grid-column:1/-1;padding-bottom:4px}
.prop-board .prop-table tr.prop-main td[data-label]:not(:first-child)::before{content:attr(data-label);display:block;
font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:800;margin-bottom:4px}
.prop-board .prop-table tr.prop-detail{display:block;margin-top:-4px}
.prop-board .prop-table tr.prop-detail>td{display:block;padding:0 4px 8px!important;border:0}
.prop-board .prop-table tr.prop-detail.on>td{border:1px solid var(--border-2);border-top:0;border-radius:0 0 14px 14px;
background:rgba(6,10,18,.85);padding:12px 12px 14px!important;margin-top:-8px}}
@media(min-width:761px){.prop-table{min-width:720px}}
"""


def shell_css() -> str:
    return _SHELL_BASE + TABLE_UI_CSS


def shell_js() -> str:
    return (
        "function show(k){document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));"
        "document.getElementById('v-'+k).classList.add('on');"
        "document.querySelectorAll('.chase-nav-link').forEach(b=>b.classList.toggle('active',b.dataset.v===k));"
        "if(location.hash!=='#'+k)history.replaceState(null,'','#'+k);"
        "window.scrollTo(0,0);}"
        "function switchGame(g){document.querySelectorAll('.matchup-report').forEach(x=>"
        "x.classList.toggle('on',x.dataset.game===g));const s=document.getElementById('gameSelect');"
        "if(s)s.value=g;}"
        "function openGame(g){switchGame(g);show('matchups');}"
        "function togglePitcher(i){const r=document.getElementById('prop-detail-'+i);"
        "if(r)r.classList.toggle('on');}"
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
