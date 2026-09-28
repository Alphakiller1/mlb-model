/**
 * MLBMA icon system — neon purple line-art marks (8-icon grid, 1024px PNG),
 * plus thin inline SVG for micro utility affordances (arrows, wind, etc.).
 *
 * Regenerate marks: python scripts/build_neon_icons.py
 * Validate:         python scripts/validate_mlbma_icons.py
 */
(function(global) {
  'use strict';

  var ICON_VER = '20260612a';
  var ICON_BASE = 'assets/icons/';
  var MICRO_PX = 18;

  var SVG_ATTRS = ' xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';

  function L(body) { return '<svg' + SVG_ATTRS + '>' + body + '</svg>'; }

  var NEON = {
    field: 'neon-diamond-field',
    ball: 'neon-baseball',
    bat: 'neon-bat',
    stadium: 'neon-stadium',
    weather: 'neon-weather-field',
    vs: 'neon-vs',
    up: 'neon-trend-up',
    down: 'neon-trend-down'
  };

  /**
   * Crisp inline-SVG poster marks (violet neon). These replaced the generated PNG
   * marks, which rendered soft at badge sizes — vectors stay sharp at any DPI.
   * Bodies are 24x24 line art with light violet fills for poster mass.
   */
  var V = '#9A6BFF';
  var V_FILL = 'rgba(154,107,255,.12)';
  var NEON_SVG = {
    'neon-diamond-field':
      '<path d="M4.6 8.2A10.8 10.8 0 0 1 19.4 8.2" stroke-opacity=".45"/>'
      + '<path d="M12 4.6 19.4 12 12 19.4 4.6 12Z" fill="' + V_FILL + '"/>'
      + '<path d="M12 8.8 15.2 12 12 15.2 8.8 12Z"/>'
      + '<circle cx="12" cy="12" r="1" fill="' + V + '" stroke="none"/>',
    'neon-baseball':
      '<circle cx="12" cy="12" r="8.4" fill="' + V_FILL + '"/>'
      + '<path d="M6.2 6.4c2 1.6 3.2 3.4 3.2 5.6s-1.2 4-3.2 5.6"/>'
      + '<path d="M17.8 6.4c-2 1.6-3.2 3.4-3.2 5.6s1.2 4 3.2 5.6"/>',
    'neon-bat':
      '<path d="M13.2 10.8 19.6 4.4" stroke-width="3.4"/>'
      + '<path d="M4.9 19.1l8.3-8.3"/>'
      + '<circle cx="4.7" cy="19.3" r="1" fill="' + V + '" stroke="none"/>'
      + '<circle cx="7.6" cy="7.4" r="2.3" fill="' + V_FILL + '"/>',
    'neon-stadium':
      '<path d="M3.4 9.8 12 5.4l8.6 4.4" stroke-opacity=".6"/>'
      + '<path d="M4.6 10.8v3.4c0 3 3.3 5.3 7.4 5.3s7.4-2.3 7.4-5.3v-3.4" fill="' + V_FILL + '"/>'
      + '<path d="M12 12.4l2.6 2.5-2.6 2.5-2.6-2.5Z"/>',
    'neon-weather-field':
      '<path d="M7.2 9.6a4.5 4.5 0 0 1 8.8-1.2 3.4 3.4 0 0 1-1 6.6H8.8A3.2 3.2 0 0 1 7.2 9.6Z" fill="' + V_FILL + '"/>'
      + '<path d="M5.4 18.2h6.2"/><path d="M14 18.2h3"/>'
      + '<path d="M7.6 20.8h5.4" stroke-opacity=".55"/>',
    'neon-vs':
      '<path d="M5.2 4.6 7.6 9.4l-2 .9 3.2 4.9" stroke-opacity=".6"/>'
      + '<path d="M18.8 19.4 16.4 14.6l2-.9-3.2-4.9" stroke-opacity=".6"/>'
      + '<text x="12" y="15.6" text-anchor="middle" font-size="10.5" font-weight="900" font-style="italic" font-family="inherit" fill="' + V + '" stroke="none">VS</text>',
    'neon-trend-up':
      '<path d="M4 19.6h16" stroke-opacity=".45"/>'
      + '<rect x="5.2" y="13.8" width="2.7" height="5.8" rx=".7" fill="' + V_FILL + '"/>'
      + '<rect x="10.6" y="10.6" width="2.7" height="9" rx=".7" fill="' + V_FILL + '"/>'
      + '<rect x="16" y="7.4" width="2.7" height="12.2" rx=".7" fill="' + V_FILL + '"/>'
      + '<path d="M4.6 9.8 10.4 5.8l3.8 2.4 5.4-3.9"/>'
      + '<path d="M16.4 4h3.2v3.2"/>',
    'neon-trend-down':
      '<path d="M4 19.6h16" stroke-opacity=".45"/>'
      + '<rect x="5.2" y="7.4" width="2.7" height="12.2" rx=".7" fill="' + V_FILL + '"/>'
      + '<rect x="10.6" y="10.6" width="2.7" height="9" rx=".7" fill="' + V_FILL + '"/>'
      + '<rect x="16" y="13.8" width="2.7" height="5.8" rx=".7" fill="' + V_FILL + '"/>'
      + '<path d="M4.6 4.6 10.4 8.6l3.8-2.4 5.4 3.9"/>'
      + '<path d="M19.6 6.9v3.2h-3.2" transform="translate(0,0)"/>'
  };

  function neonSvgHtml(file, size) {
    var body = NEON_SVG[file];
    if (!body) return '';
    return '<svg class="ca-icon-img ca-icon-img--mark" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" '
      + 'fill="none" stroke="' + V + '" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
      + 'style="filter:drop-shadow(0 0 3.5px rgba(154,107,255,.45))" aria-hidden="true" focusable="false">'
      + body + '</svg>';
  }

  /** All section marks map to the 8 neon line-art icons (replace, never stack). */
  var MARK_ICONS = {
    dashboard: NEON.stadium,
    'team-rankings': NEON.up,
    trends: NEON.up,
    matchups: NEON.vs,
    compare: NEON.vs,
    'team-profile': NEON.stadium,
    'player-profile': NEON.bat,
    offense: NEON.bat,
    pitching: NEON.ball,
    lineups: NEON.field,
    metrics: NEON.up,
    'research-lab': NEON.up,
    alerts: NEON.down,
    glossary: NEON.ball,
    reports: NEON.up,
    settings: NEON.stadium,
    'strike-zone': NEON.field,
    'velocity-gauge': NEON.up,
    'search-filter': NEON.stadium,
    'team-shield': NEON.stadium,
    'roster-board': NEON.stadium,
    'lab-flask': NEON.up,
    'notify-bell': NEON.down,
    playbook: NEON.up,
    'summary-doc': NEON.up,
    'config-gear': NEON.stadium,
    'diamond-field': NEON.field,
    'lineup-bars': NEON.field,
    'trend-line': NEON.down,
    'matchup-plates': NEON.vs,
    'batting-chart': NEON.bat,
    'compare-stats': NEON.vs,
    'player-card': NEON.bat,
    'offense-power': NEON.bat,
    'analytics-hub': NEON.stadium,
    baseball: NEON.ball,
    bat: NEON.bat,
    bats: NEON.vs,
    'home-plate': NEON.field,
    home: NEON.field,
    diamond: NEON.field,
    glove: NEON.stadium,
    cap: NEON.stadium,
    helmet: NEON.bat,
    mask: NEON.field,
    magnifier: NEON.stadium,
    binoculars: NEON.stadium,
    pennant: NEON.up,
    trophy: NEON.up,
    target: NEON.ball,
    crosshair: NEON.field,
    radar: NEON.up,
    gauge: NEON.up,
    activity: NEON.down,
    flame: NEON.down,
    'chart-line': NEON.down,
    'line-chart': NEON.down,
    scoreboard: NEON.up,
    'bar-chart-3': NEON.up,
    layers: NEON.up,
    'circle-dollar-sign': NEON.up,
    split: NEON.vs,
    clock: NEON.stadium,
    'alert-triangle': NEON.down,
    stadium: NEON.stadium,
    'clipboard-list': NEON.up,
    'flask-conical': NEON.up,
    swords: NEON.vs,
    'trending-up': NEON.up,
    'trending-down': NEON.down,
    'trend-up': NEON.up,
    'trend-down': NEON.down,
    'calendar-days': NEON.field,
    'list-ordered': NEON.field,
    'layout-grid': NEON.stadium,
    'table-2': NEON.up,
    'book-open': NEON.ball,
    'git-compare': NEON.vs,
    search: NEON.stadium,
    list: NEON.field,
    insight: NEON.up
  };

  /** Thin line SVGs — utility controls + micro-size fallbacks (<=18px). */
  var LINE_ICONS = {
    'trending-up': L('<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>'),
    'trending-down': L('<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>'),
    'arrow-up': L('<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>'),
    'arrow-down': L('<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>'),
    'arrow-right': L('<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>'),
    'arrow-left-right': L('<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>'),
    'git-branch': L('<line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>'),
    wind: L('<path d="M17.7 7.7a2.5 2.5 0 1 1 1.8 4.3H2"/><path d="M9.6 4.6A2 2 0 1 1 11 8H2"/><path d="M12.6 19.4A2 2 0 1 0 14 16H2"/>'),
    'map-pin': L('<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>'),
    users: L('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
    'circle-dot': L('<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>'),
    calendar: L('<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>'),
    list: L('<line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/>'),
    search: L('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'),
    'book-open': L('<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>')
  };

  var ICON_ALIAS = {
    trend: 'trends', 'trend-up': 'trends', 'trend-down': 'trend-line',
    bars: 'team-rankings', chart: 'metrics',
    dollar: 'metrics', edge: 'metrics', betting: 'metrics',
    award: 'team-rankings', leader: 'team-rankings',
    rankings: 'team-rankings', grid: 'dashboard',
    process: 'strike-zone', power: 'offense-power', regression: 'trend-line',
    analyst: 'reports', clipboard: 'reports',
    discipline: 'strike-zone', shield: 'team-shield', swap: 'arrow-left-right',
    onbase: 'offense', contact: 'batting-chart',
    pitching: 'pitching', flask: 'research-lab',
    open: 'arrow-right', barrel: 'offense-power',
    rotation: 'pitching', starters: 'pitching', bullpen: 'team-shield',
    calendar: 'lineups', schedule: 'lineups',
    opponents: 'search-filter', wins: 'team-rankings', results: 'team-rankings',
    flame: 'trend-line', activity: 'trend-line', sustainability: 'strike-zone',
    lightbulb: 'reports', research: 'research-lab', intel: 'search-filter', brain: 'research-lab',
    insight: 'research-lab',
    users: 'player-profile', roster: 'team-profile',
    'chart-line': 'trend-line', linechart: 'trend-line',
    platoon: 'compare-stats', branch: 'git-branch',
    away: 'diamond-field', venue: 'diamond-field',
    weather: 'wind', window: 'settings',
    table: 'metrics', data: 'metrics', grades: 'metrics', scoring: 'trends',
    velocity: 'velocity-gauge', zap: 'matchups', risk: 'alerts',
    fade: 'trend-line', scout: 'search-filter', usage: 'metrics', tonight: 'matchups',
    matchup: 'matchups', game: 'diamond-field', production: 'metrics',
    skills: 'offense', depth: 'lineups', late: 'settings', analysis: 'reports',
    plate: 'diamond-field', mound: 'pitching', identity: 'team-profile', intelligence: 'search-filter',
    compare: 'compare', matchups: 'matchups', lineup: 'lineups', split: 'compare-stats',
    batting: 'offense'
  };

  var PROFILE_ICONS = {
    lineup: 'lineups', rotation: 'pitching', bullpen: 'team-shield', starters: 'pitching', relievers: 'team-shield',
    'offense-profile': 'offense', batting: 'offense', 'rolling-trend': 'trends', momentum: 'trends', trend: 'trends',
    'schedule-context': 'lineups', schedule: 'lineups', opponents: 'search-filter',
    'surface-wins': 'team-rankings', results: 'team-rankings', tonight: 'matchups',
    'analyst-take': 'reports', analysis: 'reports', sustainability: 'strike-zone',
    'research-takeaways': 'research-lab', 'staff-takeaways': 'reports', 'staff-snapshot': 'team-shield',
    pitching: 'pitching', 'rotation-section': 'pitching', 'bullpen-section': 'team-shield',
    roster: 'team-profile', usage: 'metrics', 'run-production': 'metrics', 'plate-skills': 'offense',
    'totals-lean': 'metrics', 'matchup-risk': 'matchups', 'fade-conditions': 'alerts',
    'research-note': 'research-lab', 'run-prevention': 'pitching', 'depth-gap': 'lineups',
    'late-inning': 'settings', 'high-leverage': 'alerts', 'platoon-angle': 'compare-stats',
    'contact-hot': 'trends', 'contact-cold': 'trend-line', 'contact-flat': 'strike-zone',
    'platoon-profile': 'compare-stats', 'discipline-split': 'compare-stats', 'process-upside': 'strike-zone',
    'regression-watch': 'trend-line', 'platoon-report': 'compare-stats', identity: 'team-profile', intelligence: 'search-filter',
    target: 'strike-zone', spark: 'metrics', shield: 'team-shield', list: 'lineups', split: 'compare-stats',
    insight: 'research-lab'
  };

  function resolveLucideName(name) {
    if (!name) return 'circle-dot';
    var key = String(name).toLowerCase();
    return ICON_ALIAS[key] || key;
  }

  function profileIcon(key) {
    if (!key) return 'reports';
    var k = String(key).toLowerCase();
    if (PROFILE_ICONS[k]) return PROFILE_ICONS[k];
    return resolveLucideName(k);
  }

  function markFile(name) {
    var key = profileIcon(name);
    if (MARK_ICONS[key]) return MARK_ICONS[key];
    key = resolveLucideName(key);
    return MARK_ICONS[key] || null;
  }

  function lineIcon(name) {
    var key = resolveLucideName(profileIcon(name));
    return LINE_ICONS[key] || LINE_ICONS[name] || null;
  }

  function isMarkIcon(name) {
    return !!markFile(name);
  }

  function markAssetUrl(file) {
    return ICON_BASE + file + '.png?v=' + ICON_VER;
  }

  function iconImgHtml(name, px) {
    var file = markFile(name);
    if (!file) return '';
    var size = px || 46;
    var svg = neonSvgHtml(file, size);
    if (svg) return svg;
    return '<img class="ca-icon-img ca-icon-img--mark" src="' + markAssetUrl(file) + '" '
      + 'alt="" width="' + size + '" height="' + size + '" loading="lazy" decoding="async" '
      + 'draggable="false">';
  }

  function iconSvg(name, opts) {
    opts = opts || {};
    var resolved = profileIcon(name);
    var useLine = opts.preferLine || (opts.px && opts.px <= MICRO_PX);
    if (useLine) {
      var line = lineIcon(name);
      if (line) return line;
    }
    var img = iconImgHtml(resolved, opts.px);
    if (img) return img;
    var key = resolveLucideName(resolved);
    return LINE_ICONS[key] || LINE_ICONS['circle-dot'];
  }

  function neonWrapHtml(name, px, small, hero) {
    var cls = 'ca-neon-icon';
    if (small) cls += ' ca-neon-icon--sm';
    if (hero) cls += ' ca-neon-icon--hero';
    return '<span class="' + cls + '" aria-hidden="true">' + iconImgHtml(name, px) + '</span>';
  }

  function iconCircleHtml(name, small, hero) {
    var px = hero ? 50 : (small ? 38 : 46);
    if (isMarkIcon(name)) return neonWrapHtml(name, px, small, hero);
    var cls = 'ca-icon-circle';
    if (hero) cls += ' ca-icon-circle--hero';
    else if (small) cls += ' ca-icon-circle--sm';
    return '<span class="' + cls + '" aria-hidden="true">' + iconSvg(name, { px: px, preferLine: true }) + '</span>';
  }

  function iconHtml(name, size) {
    var px = size || 18;
    var out = iconSvg(name, { px: px, preferLine: px <= MICRO_PX });
    if (out.indexOf('<img') === 0) {
      return out.replace(/width="\d+"/, 'width="' + px + '"').replace(/height="\d+"/, 'height="' + px + '"');
    }
    return out.replace('<svg', '<svg style="width:' + px + 'px;height:' + px + 'px;flex:none"');
  }

  function neonSizeFromContext(el) {
    var circle = el.closest('.ca-icon-circle');
    if (circle && circle.classList.contains('ca-icon-circle--hero')) return 50;
    if (circle && circle.classList.contains('ca-icon-circle--sm')) return 38;
    if (circle) return 46;
    var inlinePx = parseInt(el.style.width, 10) || parseInt(el.style.height, 10) || 0;
    return inlinePx > MICRO_PX ? inlinePx : 46;
  }

  function mountReplacedIcon(el, node, name) {
    var tag = String(node.tagName || '').toUpperCase();
    if ((tag === 'IMG' || tag === 'SVG') && isMarkIcon(name)) {
      var toolIcon = el.closest('.ca-tool-card__icon');
      var circle = el.closest('.ca-icon-circle');
      var sectionIcon = el.closest('.ca-section-head .ca-icon, .ca-icon');
      var px = neonSizeFromContext(el);
      var small = px <= 40;
      var hero = circle && circle.classList.contains('ca-icon-circle--hero');
      var wrap = document.createElement('span');
      wrap.className = 'ca-neon-icon' + (small ? ' ca-neon-icon--sm' : '') + (hero ? ' ca-neon-icon--hero' : '') + (toolIcon ? ' ca-neon-icon--tool' : '');
      wrap.appendChild(node);
      if (toolIcon && circle) {
        toolIcon.classList.add('ca-tool-card__icon--asset');
        toolIcon.innerHTML = '';
        toolIcon.appendChild(wrap);
        return;
      }
      if (circle) {
        if (sectionIcon) sectionIcon.classList.add('ca-icon--asset');
        circle.replaceWith(wrap);
        return;
      }
      if (sectionIcon) {
        sectionIcon.classList.add('ca-icon--asset');
        sectionIcon.innerHTML = '';
        sectionIcon.appendChild(wrap);
        return;
      }
    }
    if (el.style.width) node.style.width = el.style.width;
    if (el.style.height) node.style.height = el.style.height;
    el.replaceWith(node);
  }

  function refreshIcons(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var nodes = scope.querySelectorAll('[data-lucide]');
    nodes.forEach(function(el) {
      var name = el.getAttribute('data-lucide');
      if (!name) return;
      var inlinePx = parseInt(el.style.width, 10) || parseInt(el.style.height, 10) || 0;
      var useLine = inlinePx > 0 && inlinePx <= MICRO_PX && !isMarkIcon(name);
      var tmp = document.createElement('div');
      tmp.innerHTML = iconSvg(name, { px: useLine ? inlinePx : neonSizeFromContext(el), preferLine: useLine });
      var node = tmp.firstElementChild;
      if (!node) return;
      mountReplacedIcon(el, node, name);
    });
    return Promise.resolve();
  }

  function initOnReady() {
    refreshIcons(document.body);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOnReady);
  } else {
    initOnReady();
  }

  global.MLBMAIcons = {
    MARK_ICONS: MARK_ICONS,
    LINE_ICONS: LINE_ICONS,
    CA_ICONS: MARK_ICONS,
    iconCircleHtml: iconCircleHtml,
    iconHtml: iconHtml,
    iconSvg: iconSvg,
    iconImgHtml: iconImgHtml,
    refreshIcons: refreshIcons,
    resolveLucideName: resolveLucideName,
    profileIcon: profileIcon,
    isMarkIcon: isMarkIcon,
    markFile: markFile,
    PROFILE_ICONS: PROFILE_ICONS,
    ICON_ALIAS: ICON_ALIAS
  };
})(typeof window !== 'undefined' ? window : this);
