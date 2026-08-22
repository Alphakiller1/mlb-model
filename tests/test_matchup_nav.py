"""Matchup breakdown drill-in — the card footer has to actually show the report.

PR #25 uniqued process-nav IDs so 01–07 stopped jumping to the hidden featured copy.
That was necessary and not sufficient: `openGame` still called `show('matchups')`,
which always `window.scrollTo(0,0)` and retriggered the view animation, then
smooth-scrolled to `#matchupDetail` sitting under the full slate. The scroll lost.
Clicking `Full matchup breakdown →` left the user on the cards.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess

import pytest

from mlbmodel.report.matchup import _headshot
from mlbmodel.report.shell import shell_css, shell_js

_NODE = shutil.which("node")

# Mini-DOM + fixture run inside Node. Chrome dump-dom hangs in this environment;
# GitHub-hosted runners ship Node, so this is the portable behavior check.
_RUNNER = r"""
class El {
  constructor(tag, attrs) {
    this.tagName = String(tag).toUpperCase();
    this.attrs = Object.assign({}, attrs || {});
    this.children = [];
    this.parent = null;
    this._text = "";
    this._class = new Set(String(this.attrs.class || "").split(/\s+/).filter(Boolean));
    this._template = this.tagName === "TEMPLATE";
    this.contentChildren = [];
  }
  get classList() {
    const s = this;
    return {
      add(c) { s._class.add(c); },
      remove(c) { s._class.delete(c); },
      contains(c) { return s._class.has(c); },
      toggle(c, force) {
        if (force === undefined) {
          if (s._class.has(c)) { s._class.delete(c); return false; }
          s._class.add(c); return true;
        }
        if (force) s._class.add(c); else s._class.delete(c);
        return !!force;
      }
    };
  }
  get className() { return [...this._class].join(" "); }
  getAttribute(n) {
    if (n === "class") return this.className || null;
    return Object.prototype.hasOwnProperty.call(this.attrs, n) ? this.attrs[n] : null;
  }
  setAttribute(n, v) {
    this.attrs[n] = String(v);
    if (n === "class") this._class = new Set(String(v).split(/\s+/).filter(Boolean));
  }
  removeAttribute(n) { delete this.attrs[n]; }
  hasAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n); }
  appendChild(ch) { ch.parent = this; this.children.push(ch); return ch; }
  get textContent() {
    if (this._text) return this._text;
    return this.children.map((c) => c.textContent).join("");
  }
  set textContent(v) { this._text = String(v); this.children = []; }
  get dataset() {
    const d = {};
    for (const [k, v] of Object.entries(this.attrs)) {
      if (k.slice(0, 5) === "data-") d[k.slice(5)] = v;
    }
    return d;
  }
  get innerHTML() {
    const nodes = this._template ? this.contentChildren : this.children;
    const boxed = new String("html");
    boxed.__nodes = nodes;
    return boxed;
  }
  set innerHTML(html) {
    const src = html && html.__nodes ? html.__nodes : [];
    this.children = src.map(cloneEl);
    this.children.forEach((c) => { c.parent = this; });
    this._text = "";
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) { return selectAll(this, sel, false); }
  closest(sel) {
    let n = this;
    while (n) { if (matches(n, sel)) return n; n = n.parent; }
    return null;
  }
  scrollIntoView() { globalThis.__scrolled.push(this); }
}
function cloneEl(el) {
  const c = new El(el.tagName.toLowerCase(), Object.assign({}, el.attrs));
  c._class = new Set(el._class);
  c._text = el._text;
  c._template = el._template;
  c.children = el.children.map(cloneEl);
  c.children.forEach((ch) => { ch.parent = c; });
  c.contentChildren = el.contentChildren.map(cloneEl);
  return c;
}
function walk(node, fn) {
  fn(node);
  const kids = node._template ? [] : node.children;
  kids.forEach((ch) => walk(ch, fn));
}
function matches(n, sel) {
  if (sel.charAt(0) === ".") return n._class.has(sel.slice(1));
  if (sel.charAt(0) === "#") return n.attrs.id === sel.slice(1);
  const attrEq = sel.match(/^\[([^=]+)="([^"]*)"\]$/);
  if (attrEq) return n.getAttribute(attrEq[1]) === attrEq[2];
  const attrBare = sel.match(/^\[([^\]]+)\]$/);
  if (attrBare) return n.getAttribute(attrBare[1]) != null;
  const tagClass = sel.match(/^([a-z0-9-]+)\.([a-z0-9_-]+)$/i);
  if (tagClass) return n.tagName === tagClass[1].toUpperCase() && n._class.has(tagClass[2]);
  const tagAttr = sel.match(/^([a-z0-9-]+)\[([^=]+)="([^"]*)"\]$/i);
  if (tagAttr) return n.tagName === tagAttr[1].toUpperCase() && n.getAttribute(tagAttr[2]) === tagAttr[3];
  return n.tagName === String(sel).toUpperCase();
}
function selectAll(root, sel, includeRoot) {
  const parts = String(sel).trim().split(/\s+/);
  let set = [];
  walk(root, (n) => {
    if ((includeRoot || n !== root) && matches(n, parts[0])) set.push(n);
  });
  for (let i = 1; i < parts.length; i++) {
    const next = [];
    set.forEach((n) => {
      walk(n, (c) => { if (c !== n && matches(c, parts[i])) next.push(c); });
    });
    set = next;
  }
  set.forEach = Array.prototype.forEach;
  return set;
}
function el(tag, attrs, kids, text) {
  const n = new El(tag, attrs);
  (kids || []).forEach((k) => n.appendChild(k));
  if (text != null) n._text = text;
  return n;
}

const matchups = el("section", {id: "v-matchups", class: "view on"});
const trends = el("section", {id: "v-trends", class: "view"});
const board = el("section", {class: "bd"}, [el("article", {class: "bd-card"}, [], "BOARD")]);
const label = el("span", {id: "matchupDetailLabel"});
const select = el("select", {id: "gameSelect"});
select.attrs.value = "AAA@BBB";
Object.defineProperty(select, "value", {
  get() { return this.attrs.value; },
  set(v) { this.attrs.value = v; }
});
const aaaDecision = el("section", {class: "desk-step", id: "m-decision-AAA-BBB", "data-step": "m-decision"}, [], "DEC-AAA");
const aaaNav = el("a", {href: "#m-decision-AAA-BBB", class: "desk-process-link"});
const aaa = el("div", {class: "matchup-report", "data-game": "AAA@BBB"}, [
  el("div", {class: "matchup-body"}, [
    el("div", {class: "matchup-process"}, [
      el("nav", {class: "desk-process"}, [aaaNav]),
      aaaDecision
    ])
  ])
]);
const cccDecision = el("section", {class: "desk-step", id: "m-decision-CCC-DDD", "data-step": "m-decision"}, [], "DEC-CCC");
const cccNav = el("a", {href: "#m-decision-CCC-DDD", class: "desk-process-link"});
const cccTpl = el("template", {class: "matchup-full-src"});
cccTpl.contentChildren = [
  el("div", {class: "matchup-process"}, [
    el("nav", {class: "desk-process"}, [cccNav]),
    cccDecision
  ])
];
const cccBody = el("div", {class: "matchup-body"}, [
  el("div", {class: "matchup-summary"}, [], "SUMMARY-CCC")
]);
const ccc = el("div", {class: "matchup-report", "data-game": "CCC@DDD", hidden: ""}, [cccBody, cccTpl]);
const detail = el("div", {class: "matchup-detail", id: "matchupDetail"}, [label, aaa, ccc]);
matchups.appendChild(board);
matchups.appendChild(detail);
const btnM = el("button", {"data-v": "matchups", class: "on"});
const btnT = el("button", {"data-v": "trends"});
const nav = el("nav", {class: "nav"}, [btnM, btnT]);
const sidebar = el("aside", {class: "sidebar"}, [nav]);
const root = el("body", {}, [sidebar, select, matchups, trends]);

const document = {
  getElementById(id) {
    let hit = null;
    walk(root, (n) => { if (!hit && n.attrs && n.attrs.id === id) hit = n; });
    return hit;
  },
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
  querySelectorAll(sel) { return selectAll(root, sel, false); },
  addEventListener() {}
};
const window = { scrollTo() { window.__scrolledTo = true; } };
const location = { hash: "" };
const history = { replaceState() {} };
globalThis.document = document;
globalThis.window = window;
globalThis.location = location;
globalThis.history = history;
globalThis.__scrolled = [];

SHELL_JS

function panel(g) {
  return document.querySelectorAll(".matchup-report").filter((n) => n.getAttribute("data-game") === g)[0];
}
function snapshot(tag) {
  const m = document.getElementById("v-matchups");
  const a = panel("AAA@BBB");
  const c = panel("CCC@DDD");
  return {
    tag,
    drilled: m.classList.contains("is-drilled"),
    matchupsOn: m.classList.contains("on"),
    trendsOn: document.getElementById("v-trends").classList.contains("on"),
    aaaHidden: a.hasAttribute("hidden"),
    cccHidden: c.hasAttribute("hidden"),
    cccHasSummary: !!c.querySelector(".matchup-summary"),
    cccHasDecision: !!c.querySelector('[data-step="m-decision"]'),
    label: (document.getElementById("matchupDetailLabel").textContent || "").trim(),
    select: document.getElementById("gameSelect").value,
    scrolledIds: globalThis.__scrolled.map((n) => n.attrs.id || "")
  };
}

const results = [];
results.push(snapshot("boot"));
openGame("CCC@DDD");
results.push(snapshot("open-ccc"));
globalThis.__scrolled = [];
const liveNav = panel("CCC@DDD").querySelector(".desk-process").querySelector("a")
  || panel("CCC@DDD").querySelector("a");
jumpMatchupStep(liveNav, "m-decision");
results.push(snapshot("jump-ccc"));
show("matchups");
results.push(snapshot("nav-back"));
openGame("AAA@BBB");
results.push(snapshot("open-aaa"));
show("trends");
openGame("CCC@DDD");
results.push(snapshot("from-trends"));
process.stdout.write(JSON.stringify(results));
"""


def test_shell_js_open_game_keeps_drill_and_does_not_unconditionally_scroll():
    js = shell_js()
    assert "function openGame(g){show('matchups',true);switchGame(g);openMatchup();}" in js
    assert "function closeMatchup" in js
    assert "function openMatchup" in js
    # The old path reset the view (and scrolled to 0) on every card click.
    assert "function openGame(g){show('matchups');switchGame(g);" not in js
    assert "function show(k,keep)" in js


def test_shell_css_hides_board_while_drilled():
    css = shell_css()
    assert "#v-matchups.is-drilled > .bd { display: none; }" in css
    assert "#v-matchups:not(.is-drilled) > .matchup-detail { display: none; }" in css


def test_headshot_survives_nan_pitcher_id():
    html = _headshot(float("nan"))
    assert "phead-na" in html
    assert "people/nan" not in html
    assert math.isnan(float("nan"))
    html_none = _headshot(None)
    assert "phead-na" in html_none
    html_ok = _headshot(592450)
    assert "592450" in html_ok


def _run_nav_js() -> list[dict]:
    if not _NODE:
        pytest.skip("node not installed")
    script = _RUNNER.replace("SHELL_JS", shell_js())
    proc = subprocess.run(
        [_NODE, "--eval", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        pytest.fail(f"nav js runner failed: {proc.stderr[-800:]}\n{proc.stdout[-400:]}")
    return json.loads(proc.stdout)


def test_open_game_drills_into_hydrated_report_not_the_board():
    snaps = {row["tag"]: row for row in _run_nav_js()}

    boot = snaps["boot"]
    assert boot["drilled"] is False
    assert boot["cccHasSummary"] is True
    assert boot["cccHasDecision"] is False

    opened = snaps["open-ccc"]
    assert opened["drilled"] is True
    assert opened["cccHidden"] is False
    assert opened["aaaHidden"] is True
    assert opened["cccHasSummary"] is False
    assert opened["cccHasDecision"] is True
    assert opened["label"] == "CCC @ DDD"
    assert opened["select"] == "CCC@DDD"

    jumped = snaps["jump-ccc"]
    assert jumped["scrolledIds"] == ["m-decision-CCC-DDD"]

    back = snaps["nav-back"]
    assert back["drilled"] is False

    featured = snaps["open-aaa"]
    assert featured["drilled"] is True
    assert featured["aaaHidden"] is False
    assert featured["cccHidden"] is True

    from_trends = snaps["from-trends"]
    assert from_trends["matchupsOn"] is True
    assert from_trends["trendsOn"] is False
    assert from_trends["drilled"] is True
    assert from_trends["cccHasDecision"] is True
    assert from_trends["cccHidden"] is False
