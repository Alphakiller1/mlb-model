"""Vanilla JS helpers for sortable, filterable report tables."""
from __future__ import annotations

TABLE_UI_JS = r"""
(function(){
  function parseNum(t){
    var s=(t||'').replace(/[^0-9.\-+]/g,'');
    var n=parseFloat(s);
    return isNaN(n)?null:n;
  }
  function initTable(table){
    if(!table||table.dataset.uiInit)return;
    table.dataset.uiInit='1';
    var thead=table.tHead;
    if(!thead)return;
    var headers=thead.rows[0].cells;
    for(var i=0;i<headers.length;i++){
      (function(col){
        var th=headers[col];
        if(th.classList.contains('no-sort'))return;
        th.style.cursor='pointer';
        th.setAttribute('role','button');
        th.setAttribute('tabindex','0');
        th.setAttribute('aria-sort','none');
        function sort(){
          var tbody=table.tBodies[0];
          if(!tbody)return;
          var rows=Array.prototype.slice.call(tbody.rows);
          var asc=th.dataset.sortDir!=='asc';
          th.dataset.sortDir=asc?'asc':'desc';
          th.setAttribute('aria-sort',asc?'ascending':'descending');
          rows.sort(function(a,b){
            var av=a.cells[col]?a.cells[col].textContent:'';
            var bv=b.cells[col]?b.cells[col].textContent:'';
            var an=parseNum(av), bn=parseNum(bv);
            if(an!==null&&bn!==null)return asc?an-bn:bn-an;
            return asc?av.localeCompare(bv):bv.localeCompare(av);
          });
          rows.forEach(function(r){tbody.appendChild(r);});
        }
        th.addEventListener('click',sort);
        th.addEventListener('keydown',function(e){
          if(e.key==='Enter'||e.key===' ') { e.preventDefault(); sort(); }
        });
      })(i);
    }
  }
  function initFilter(input){
    if(!input||input.dataset.uiInit)return;
    input.dataset.uiInit='1';
    var tableId=input.getAttribute('data-filter-for');
    var table=document.getElementById(tableId);
    if(!table)return;
    input.addEventListener('input',function(){
      var q=input.value.toLowerCase();
      Array.prototype.forEach.call(table.tBodies[0].rows,function(row){
        if(row.classList.contains('prop-detail'))return;
        row.style.display=row.textContent.toLowerCase().indexOf(q)>=0?'':'none';
      });
    });
  }
  window.MLBTableUI={initTable:initTable,initFilter:initFilter};
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('table.sortable').forEach(initTable);
    document.querySelectorAll('input.table-filter').forEach(initFilter);
  });
})();
"""

TABLE_UI_CSS = """
.table-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 10px;align-items:center}
.table-filter{flex:1;min-width:160px;max-width:320px;background:var(--card);color:var(--ink);
border:1px solid var(--border-2);border-radius:8px;padding:9px 12px;font:600 13px var(--sans)}
.table-scroll table.sortable th{position:sticky;top:0;z-index:2;background:var(--card)}
.top-leans{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}
.top-lean{flex:1 1 200px;min-width:180px;background:linear-gradient(160deg,rgba(31,34,47,.85),rgba(16,18,27,.92));
border:1px solid var(--border-2);border-radius:8px;padding:10px 12px}
.top-lean .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.top-lean .v{font:800 15px var(--display);margin-top:4px}
.top-lean button{border:0;background:none;color:var(--teal);font:inherit;padding:0;cursor:pointer;text-align:left}
.top-lean button:hover{text-decoration:underline}
.pickem-books{display:flex;gap:6px;flex-wrap:wrap;font-size:11px}
.pickem-books span{padding:2px 6px;border-radius:4px;background:rgba(255,255,255,.06)}
.pickem-books .best{border:1px solid var(--teal);color:var(--teal)}
@media (prefers-reduced-motion:reduce){.table-scroll table.sortable th{transition:none}}
#nav .navb:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
.chase-nav-link:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
"""
