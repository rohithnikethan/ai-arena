/* AI Arena: shared helpers (theme, nav, toasts, fetch, agent pickers, confetti). */
(function () {
  'use strict';

  var ROWS = 6, COLS = 7;
  var reducedMotionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

  /* ------------------------------------------------------------------ */
  /* Storage (always guarded)                                            */
  /* ------------------------------------------------------------------ */
  var store = {
    get: function (key, fallback) {
      try {
        var v = window.localStorage.getItem('ai-arena-' + key);
        return v === null ? fallback : JSON.parse(v);
      } catch (e) { return fallback; }
    },
    set: function (key, value) {
      try { window.localStorage.setItem('ai-arena-' + key, JSON.stringify(value)); } catch (e) { /* ignore */ }
    }
  };

  /* ------------------------------------------------------------------ */
  /* Small utilities                                                     */
  /* ------------------------------------------------------------------ */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function reducedMotion() { return !!(reducedMotionQuery && reducedMotionQuery.matches); }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function fmtInt(n) {
    if (n == null || isNaN(n)) return '—';
    return Math.round(n).toLocaleString('en-US');
  }
  function fmtCompact(n) {
    if (n == null || isNaN(n)) return '—';
    var a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
    if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (a >= 1e4) return (n / 1e3).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, '') + 'k';
    return Math.round(n).toLocaleString('en-US');
  }
  function fmtMs(ms) {
    if (ms == null || isNaN(ms)) return '—';
    if (ms >= 10000) return (ms / 1000).toFixed(1) + ' s';
    if (ms >= 100) return Math.round(ms) + ' ms';
    if (ms >= 10) return ms.toFixed(1) + ' ms';
    return ms.toFixed(2) + ' ms';
  }
  var WIN_THRESHOLD = 900000;
  function isWinValue(v) { return v != null && Math.abs(v) >= WIN_THRESHOLD && Math.abs(v) < 1e8; }
  function isInfValue(v) { return v != null && Math.abs(v) >= 1e8; }
  /* Format a search value (minimax score or MCTS rate). */
  function fmtValue(v, kind) {
    if (v == null || isNaN(v)) return '—';
    if (kind === 'mcts') return Math.round(v * 100) + '%';
    if (isInfValue(v)) return v > 0 ? '+∞' : '−∞';
    if (isWinValue(v)) return v > 0 ? 'WIN' : 'LOSS';
    var r = Math.round(v);
    return (r > 0 ? '+' : r < 0 ? '−' : '') + Math.abs(r).toLocaleString('en-US');
  }
  function fmtValueLong(v, kind) {
    if (kind !== 'mcts' && isWinValue(v)) {
      var plies = 1000000 - Math.abs(Math.round(v));
      var suffix = plies > 0 ? ' in ' + plies + ' ' + (plies === 1 ? 'ply' : 'plies') : '';
      return (v > 0 ? 'Forced win' : 'Forced loss') + suffix;
    }
    return fmtValue(v, kind);
  }

  /* ------------------------------------------------------------------ */
  /* Board helpers (display-side only; the server is the rules authority) */
  /* ------------------------------------------------------------------ */
  function emptyBoard() {
    var b = [];
    for (var r = 0; r < ROWS; r++) { b.push([0, 0, 0, 0, 0, 0, 0]); }
    return b;
  }
  function cloneBoard(b) { return b.map(function (row) { return row.slice(); }); }
  function dropRow(board, col) {
    for (var r = ROWS - 1; r >= 0; r--) { if (board[r][col] === 0) return r; }
    return -1;
  }
  function countDiscs(board) {
    var n = 0;
    board.forEach(function (row) { row.forEach(function (v) { if (v) n++; }); });
    return n;
  }
  /* Local four-in-a-row finder, used only by the decorative landing demo. */
  function findWin(board) {
    var dirs = [[0, 1], [1, 0], [1, 1], [1, -1]];
    for (var r = 0; r < ROWS; r++) {
      for (var c = 0; c < COLS; c++) {
        var p = board[r][c];
        if (!p) continue;
        for (var d = 0; d < dirs.length; d++) {
          var cells = [[r, c]], ok = true;
          for (var k = 1; k < 4; k++) {
            var rr = r + dirs[d][0] * k, cc = c + dirs[d][1] * k;
            if (rr < 0 || rr >= ROWS || cc < 0 || cc >= COLS || board[rr][cc] !== p) { ok = false; break; }
            cells.push([rr, cc]);
          }
          if (ok) return { player: p, cells: cells };
        }
      }
    }
    return null;
  }

  /* ------------------------------------------------------------------ */
  /* Icons used from JS                                                  */
  /* ------------------------------------------------------------------ */
  var ICONS = {
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    bulb: '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.3 1.1 2.2h5c0-.9.5-1.7 1.1-2.2A6 6 0 0 0 12 3z"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    tree: '<circle cx="12" cy="4.5" r="2"/><circle cx="5" cy="19.5" r="2"/><circle cx="12" cy="19.5" r="2"/><circle cx="19" cy="19.5" r="2"/><path d="M12 6.5V17.5M12 10 5 17.5M12 10l7 7.5"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    maximize: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    trophy: '<path d="M8 21h8M12 17v4"/><path d="M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
    sparkles: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    dice: '<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="15" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><circle cx="9" cy="15" r="1" fill="currentColor"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'
  };
  function icon(name, size) {
    size = size || 18;
    return '<svg class="icon" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || ICONS.info) + '</svg>';
  }

  /* ------------------------------------------------------------------ */
  /* Theme                                                               */
  /* ------------------------------------------------------------------ */
  function currentTheme() { return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'; }
  function setTheme(theme, persist) {
    document.documentElement.setAttribute('data-theme', theme);
    if (persist !== false) { try { localStorage.setItem('ai-arena-theme', theme); } catch (e) { /* ignore */ } }
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
  }
  function initTheme() {
    $all('[data-theme-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () { setTheme(currentTheme() === 'dark' ? 'light' : 'dark'); });
    });
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: light)');
      var onChange = function (e) {
        var saved = null;
        try { saved = localStorage.getItem('ai-arena-theme'); } catch (err) { /* ignore */ }
        if (!saved) setTheme(e.matches ? 'light' : 'dark', false);
      };
      if (mq.addEventListener) mq.addEventListener('change', onChange);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Mobile nav                                                          */
  /* ------------------------------------------------------------------ */
  function initNav() {
    var btn = $('[data-nav-toggle]');
    if (!btn) return;
    var header = $('.site-header');
    function close() { header.classList.remove('nav-open'); btn.setAttribute('aria-expanded', 'false'); btn.setAttribute('aria-label', 'Open menu'); }
    btn.addEventListener('click', function () {
      var open = !header.classList.contains('nav-open');
      header.classList.toggle('nav-open', open);
      btn.setAttribute('aria-expanded', String(open));
      btn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    document.addEventListener('click', function (e) { if (!header.contains(e.target)) close(); });
  }

  /* ------------------------------------------------------------------ */
  /* Toasts                                                              */
  /* ------------------------------------------------------------------ */
  function toast(message, opts) {
    opts = opts || {};
    var region = $('#toast-region');
    if (!region) return;
    var type = opts.type || 'info';
    var iconName = opts.icon || (type === 'error' ? 'alert' : type === 'success' ? 'check' : 'info');
    var el = document.createElement('div');
    el.className = 'toast is-' + type;
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');
    el.innerHTML =
      '<span class="toast-icon">' + icon(iconName, 16) + '</span>' +
      '<div class="toast-body">' +
      (opts.title ? '<div class="toast-title">' + escapeHtml(opts.title) + '</div>' : '') +
      '<div class="toast-msg">' + escapeHtml(message) + '</div></div>' +
      '<button class="toast-close" type="button" aria-label="Dismiss notification">' + icon('close', 14) + '</button>';
    region.appendChild(el);
    while (region.children.length > 4) region.removeChild(region.firstChild);
    var timer = null;
    function dismiss() {
      if (timer) clearTimeout(timer);
      if (!el.parentNode) return;
      el.classList.add('is-leaving');
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, reducedMotion() ? 0 : 260);
    }
    el.querySelector('.toast-close').addEventListener('click', dismiss);
    var ms = opts.timeout != null ? opts.timeout : (type === 'error' ? 6500 : 4000);
    if (ms > 0) timer = setTimeout(dismiss, ms);
    el.addEventListener('mouseenter', function () { if (timer) { clearTimeout(timer); timer = null; } });
    el.addEventListener('mouseleave', function () { if (!timer && ms > 0) timer = setTimeout(dismiss, 2000); });
    return dismiss;
  }

  /* ------------------------------------------------------------------ */
  /* Fetch helper: JSON in/out; toasts on failure and rethrows           */
  /* ------------------------------------------------------------------ */
  function api(path, body, opts) {
    opts = opts || {};
    var init = { method: body === undefined ? 'GET' : 'POST', headers: { 'Accept': 'application/json' }, signal: opts.signal };
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    var quiet = opts.quiet === true;
    function fail(msg, status) {
      var err = new Error(msg);
      err.status = status || 0;
      if (!quiet) toast(msg, { type: 'error', title: opts.errorTitle || 'Request failed' });
      throw err;
    }
    return fetch(path, init).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!res.ok) {
          fail((data && data.error) || ('The server answered ' + res.status + ' ' + (res.statusText || '')).trim() + '.', res.status);
        }
        if (data === null) fail('The server sent an unreadable response.', res.status);
        return data;
      });
    }, function (err) {
      if (err && err.name === 'AbortError') throw err;
      fail('Could not reach the server. Is "python app.py" still running?', 0);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Agent catalogue + picker widget                                     */
  /* ------------------------------------------------------------------ */
  var AGENTS = {
    random: { label: 'Random', short: 'Random', icon: 'dice', level: 1, param: null,
      blurb: 'Plays a uniformly random legal move. No parameters to tune.' },
    greedy: { label: 'Greedy', short: 'Greedy', icon: 'target', level: 2, param: null,
      blurb: 'Looks one move ahead: wins if it can, blocks if it must, else maximises the heuristic.' },
    minimax: { label: 'Minimax', short: 'Minimax', icon: 'tree', level: 3,
      param: { key: 'depth', label: 'Search depth', min: 1, max: 6, step: 1, def: 4, unit: 'ply' },
      blurb: 'Explores every line of play to a fixed depth. Exact, but exponential.' },
    alphabeta: { label: 'Alpha-Beta', short: 'α-β', icon: 'scissors', level: 4,
      param: { key: 'depth', label: 'Search depth', min: 1, max: 8, step: 1, def: 5, unit: 'ply' },
      blurb: 'Minimax with pruning and move ordering: same answer, far fewer nodes.' },
    mcts: { label: 'MCTS', short: 'MCTS', icon: 'sparkles', level: 4,
      param: { key: 'iterations', label: 'Simulations', min: 100, max: 10000, step: 100, def: 1500, unit: 'sims' },
      blurb: 'Monte Carlo Tree Search: random playouts guided by the UCT formula.' }
  };
  var AGENT_ORDER = ['random', 'greedy', 'minimax', 'alphabeta', 'mcts'];

  function agentLabel(cfg) {
    if (!cfg) return 'Agent';
    var meta = AGENTS[cfg.type];
    if (!meta) return String(cfg.type);
    if (meta.param) return meta.label + ' · ' + (meta.param.key === 'depth' ? 'd' + cfg.depth : fmtCompact(cfg.iterations) + ' sims');
    return meta.label;
  }

  function updateRangeFill(input) {
    var min = parseFloat(input.min) || 0, max = parseFloat(input.max) || 100, v = parseFloat(input.value) || 0;
    input.style.setProperty('--pct', ((v - min) / (max - min || 1) * 100) + '%');
  }
  function initRanges(root) {
    $all('input[type="range"]', root).forEach(function (r) {
      updateRangeFill(r);
      if (!r._fillBound) {
        r.addEventListener('input', function () { updateRangeFill(r); });
        r._fillBound = true;
      }
    });
  }

  var pickerCount = 0;
  /**
   * AgentPicker: renders an agent <select> + parameter slider into `root`.
   * opts: {type, value, storeKey, onChange, label}
   */
  function AgentPicker(root, opts) {
    opts = opts || {};
    this.root = root;
    this.onChange = opts.onChange || function () {};
    this.storeKey = opts.storeKey || null;
    this.values = {};
    var saved = this.storeKey ? store.get(this.storeKey, null) : null;
    var type = (saved && AGENTS[saved.type]) ? saved.type : (opts.type || 'alphabeta');
    var self = this;
    AGENT_ORDER.forEach(function (t) {
      var p = AGENTS[t].param;
      if (p) self.values[t] = p.def;
    });
    if (saved && saved.values) {
      Object.keys(saved.values).forEach(function (t) {
        var p = AGENTS[t] && AGENTS[t].param;
        if (p) self.values[t] = clamp(Number(saved.values[t]) || p.def, p.min, p.max);
      });
    } else if (opts.value != null && AGENTS[type].param) {
      this.values[type] = opts.value;
    }
    var id = 'agent-' + (++pickerCount);
    root.innerHTML =
      '<div class="field">' +
      '  <label class="field-label" for="' + id + '-type"><span>' + escapeHtml(opts.label || 'Agent') + '</span></label>' +
      '  <select class="select" id="' + id + '-type">' +
      AGENT_ORDER.map(function (t) { return '<option value="' + t + '">' + AGENTS[t].label + '</option>'; }).join('') +
      '  </select>' +
      '</div>' +
      '<div class="field" data-param-field>' +
      '  <label class="field-label" for="' + id + '-param"><span data-param-label>Parameter</span><span class="field-value" data-param-value>-</span></label>' +
      '  <input type="range" id="' + id + '-param">' +
      '  <span class="field-hint" data-param-hint></span>' +
      '</div>';
    this.select = root.querySelector('select');
    this.range = root.querySelector('input[type="range"]');
    this.paramLabel = root.querySelector('[data-param-label]');
    this.paramValue = root.querySelector('[data-param-value]');
    this.paramHint = root.querySelector('[data-param-hint]');
    this.select.value = type;
    this.select.addEventListener('change', function () { self._sync(); self._changed(); });
    this.range.addEventListener('input', function () {
      self.values[self.select.value] = Number(self.range.value);
      self._syncValue();
    });
    this.range.addEventListener('change', function () { self._changed(); });
    this._sync();
  }
  AgentPicker.prototype._sync = function () {
    var meta = AGENTS[this.select.value];
    var p = meta.param;
    if (p) {
      this.range.disabled = false;
      this.range.min = p.min; this.range.max = p.max; this.range.step = p.step;
      this.range.value = this.values[this.select.value];
      this.paramLabel.textContent = p.label;
    } else {
      this.range.disabled = true;
      this.range.min = 0; this.range.max = 1; this.range.step = 1; this.range.value = 0;
      this.paramLabel.textContent = 'Parameters';
    }
    this.paramHint.textContent = meta.blurb;
    this._syncValue();
  };
  AgentPicker.prototype._syncValue = function () {
    var meta = AGENTS[this.select.value];
    var p = meta.param;
    this.paramValue.textContent = p ? (fmtInt(this.values[this.select.value]) + ' ' + p.unit) : 'none';
    updateRangeFill(this.range);
  };
  AgentPicker.prototype._changed = function () {
    if (this.storeKey) store.set(this.storeKey, { type: this.select.value, values: this.values });
    this.onChange(this.getConfig());
  };
  AgentPicker.prototype.getConfig = function () {
    var t = this.select.value;
    var cfg = { type: t };
    var p = AGENTS[t].param;
    if (p) cfg[p.key] = Number(this.values[t]);
    return cfg;
  };
  AgentPicker.prototype.setDisabled = function (disabled) {
    this.select.disabled = disabled;
    this.range.disabled = disabled || !AGENTS[this.select.value].param;
  };
  AgentPicker.prototype.label = function () { return agentLabel(this.getConfig()); };

  /* ------------------------------------------------------------------ */
  /* Confetti (vanilla canvas)                                           */
  /* ------------------------------------------------------------------ */
  function confetti(opts) {
    if (reducedMotion()) return;
    opts = opts || {};
    var canvas = document.createElement('canvas');
    canvas.className = 'confetti-canvas';
    document.body.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = window.innerWidth, H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    ctx.scale(dpr, dpr);
    var colors = opts.colors || ['#8b5cf6', '#22d3ee', '#f43f5e', '#facc15', '#34d399', '#ffffff'];
    var parts = [];
    var count = opts.count || 180;
    for (var i = 0; i < count; i++) {
      var fromLeft = i % 2 === 0;
      parts.push({
        x: fromLeft ? -10 : W + 10,
        y: H * (0.55 + Math.random() * 0.3),
        vx: (fromLeft ? 1 : -1) * (6 + Math.random() * 9),
        vy: -(10 + Math.random() * 12),
        w: 6 + Math.random() * 6, h: 8 + Math.random() * 8,
        rot: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.3,
        color: colors[i % colors.length],
        shape: Math.random() < 0.3 ? 'circle' : 'rect'
      });
    }
    var start = performance.now(), duration = opts.duration || 3200;
    function frame(now) {
      var t = now - start;
      ctx.clearRect(0, 0, W, H);
      var alpha = t > duration - 600 ? Math.max(0, (duration - t) / 600) : 1;
      ctx.globalAlpha = alpha;
      parts.forEach(function (p) {
        p.vy += 0.32; p.vx *= 0.99; p.vy *= 0.99;
        p.x += p.vx; p.y += p.vy; p.rot += p.vr;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        if (p.shape === 'circle') { ctx.beginPath(); ctx.arc(0, 0, p.w / 2, 0, Math.PI * 2); ctx.fill(); }
        else ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.rot * 2)) + 2);
        ctx.restore();
      });
      if (t < duration) requestAnimationFrame(frame);
      else if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    }
    requestAnimationFrame(frame);
  }

  /* ------------------------------------------------------------------ */
  /* Reveal-on-scroll                                                    */
  /* ------------------------------------------------------------------ */
  function initReveal() {
    var els = $all('.reveal');
    if (!els.length) return;
    if (!('IntersectionObserver' in window) || reducedMotion()) {
      els.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
    els.forEach(function (el) { io.observe(el); });
  }

  /* Ignore shortcuts while typing in a form control. */
  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || '').toLowerCase();
    return tag === 'input' && el.type !== 'range' && el.type !== 'radio' && el.type !== 'checkbox' || tag === 'textarea' || tag === 'select' || el.isContentEditable;
  }

  function setLoading(btn, loading) {
    if (!btn) return;
    btn.classList.toggle('is-loading', !!loading);
    btn.disabled = !!loading;
    btn.setAttribute('aria-busy', loading ? 'true' : 'false');
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initNav();
    initRanges(document);
    initReveal();
  });

  window.Arena = {
    ROWS: ROWS, COLS: COLS,
    $: $, $all: $all, sleep: sleep, clamp: clamp, escapeHtml: escapeHtml, cssVar: cssVar,
    reducedMotion: reducedMotion, store: store,
    fmtInt: fmtInt, fmtCompact: fmtCompact, fmtMs: fmtMs, fmtValue: fmtValue, fmtValueLong: fmtValueLong,
    isWinValue: isWinValue, isInfValue: isInfValue,
    emptyBoard: emptyBoard, cloneBoard: cloneBoard, dropRow: dropRow, countDiscs: countDiscs, findWin: findWin,
    icon: icon, theme: currentTheme, setTheme: setTheme,
    toast: toast, api: api,
    AGENTS: AGENTS, AGENT_ORDER: AGENT_ORDER, agentLabel: agentLabel, AgentPicker: AgentPicker,
    initRanges: initRanges, updateRangeFill: updateRangeFill,
    confetti: confetti, isTypingTarget: isTypingTarget, setLoading: setLoading
  };
})();
