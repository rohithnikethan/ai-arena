/* AI Arena: Game Review - post-game analysis on the Play page.
 *
 * play.js fires `play:over` (with the move list) when a game ends and
 * `play:reset` on new game / undo.  "Review game" posts the columns to
 * /api/analyze, which re-searches every position with exact alpha-beta
 * values, and this file renders the evaluation graph, graded move list,
 * a position viewer and per-player summary.
 */
(function () {
  'use strict';
  var A = window.Arena;
  var $ = A.$;
  var panel = $('#review');
  var btn = $('#btn-review');
  if (!panel || !btn || !window.BoardView) return;

  var BADGES = {
    best: { label: 'Best', sym: '' },
    good: { label: 'Good', sym: '' },
    inaccuracy: { label: 'Inaccuracy', sym: '?!' },
    mistake: { label: 'Mistake', sym: '?' },
    blunder: { label: 'Blunder', sym: '??' }
  };
  var BADGE_ORDER = ['best', 'good', 'inaccuracy', 'mistake', 'blunder'];
  var TAGS = { missed_win: 'Missed win', allowed_forced_loss: 'Allowed forced loss' };
  var WIN = 1000000, MATE = WIN - 100;

  var R = { game: null, data: null, sel: 0, token: 0, view: null, loading: false };

  function colourName(p) { return p === 1 ? 'Red' : 'Yellow'; }
  function plural(n, w) { return n + ' ' + w + (n === 1 ? '' : 's'); }

  function whoName(player) {
    if (!R.game) return colourName(player);
    if (player === R.game.human) return 'You';
    for (var i = 0; i < R.game.moves.length; i++) {
      if (R.game.moves[i].by === 'ai' && R.game.moves[i].label) return R.game.moves[i].label;
    }
    return 'AI';
  }

  /* moves the winner still needs for a proven value (mover's perspective) */
  function mateMoves(v) {
    var plies = WIN - Math.abs(Math.round(v));
    return v > 0 ? Math.floor((plies + 1) / 2) : Math.floor(plies / 2);
  }
  function fmtVal(v) {
    if (v == null) return { text: '—', title: 'Column full' };
    if (Math.abs(v) >= MATE) {
      var n = mateMoves(v);
      return v > 0 ? { text: 'W' + n, title: 'Forced win in ' + plural(n, 'move') }
        : { text: 'L' + n, title: 'Forced loss: the opponent wins in ' + plural(n, 'move') };
    }
    var r = Math.round(v);
    return { text: (r > 0 ? '+' : r < 0 ? '−' : '') + Math.abs(r), title: 'Heuristic score ' + r };
  }

  function badgeHtml(key, big) {
    var b = BADGES[key];
    return '<span class="rv-badge is-' + key + (big ? ' is-big' : '') + '">' + b.label +
      (b.sym ? ' <span class="rv-sym" aria-hidden="true">' + b.sym + '</span>' : '') + '</span>';
  }
  function tagsHtml(tags) {
    return (tags || []).map(function (t) {
      return '<span class="rv-tag is-' + t + '">' + A.icon(t === 'missed_win' ? 'target' : 'alert', 12) + TAGS[t] + '</span>';
    }).join('');
  }

  /* ------------------------------------------------------------ states */
  function renderHead(sub) {
    return '<div class="card-head rv-head">' +
      '<div><div class="card-title">' + A.icon('target', 18) + 'Game review</div>' +
      '<div class="card-sub">' + sub + '</div></div>' +
      '<button class="btn btn-ghost btn-sm" type="button" data-rv-close>' + A.icon('close', 15) + 'Close</button></div>';
  }

  function renderLoading(n) {
    panel.innerHTML = renderHead('Re-searching every position of the game.') +
      '<div class="rv-loading" role="status">' +
      '<span class="spinner" aria-hidden="true"></span>' +
      '<div><strong>Analysing ' + plural(n, 'move') + '…</strong>' +
      '<span>Alpha-beta searches each position with a full window per candidate column, so every move gets an exact score rather than a pruning bound. Usually under two seconds.</span></div></div>' +
      '<div class="skeleton rv-skel-graph"></div>' +
      '<div class="rv-main"><div class="skeleton rv-skel-board"></div><div class="skeleton rv-skel-list"></div></div>';
  }

  function renderError(msg) {
    panel.innerHTML = renderHead('The analysis could not be completed.') +
      '<div class="empty is-error"><span class="empty-icon">' + A.icon('alert', 20) + '</span>' +
      '<span>' + A.escapeHtml(msg || 'Something went wrong.') + '</span>' +
      '<button class="btn btn-sm" type="button" data-rv-retry>' + A.icon('refresh', 15) + 'Try again</button></div>';
  }

  /* ------------------------------------------------------------ summary */
  function renderSummary(d) {
    return '<div class="rv-summary">' + [1, 2].map(function (p) {
      var s = d.summary[String(p)];
      if (!s || !s.moves) return '';
      var rows = BADGE_ORDER.map(function (k) {
        return '<li class="' + (s[k] ? '' : 'is-zero') + '"><span class="rv-dot is-' + k + '"></span>' + BADGES[k].label +
          '<span class="rv-count">' + s[k] + '</span></li>';
      }).join('');
      var tags = Object.keys(TAGS).filter(function (t) { return s[t]; }).map(function (t) {
        return '<span class="rv-tag is-' + t + '">' + TAGS[t] + ' ×' + s[t] + '</span>';
      }).join('');
      return '<div class="rv-player">' +
        '<div class="rv-player-head"><span class="mini-disc p' + p + '"></span><strong>' + A.escapeHtml(whoName(p)) + '</strong>' +
        '<span class="rv-player-colour">' + colourName(p) + '</span></div>' +
        '<div class="rv-acc"><span class="rv-acc-num">' + Math.round(s.accuracy) + '%</span>' +
        '<span class="rv-acc-label">of ' + plural(s.moves, 'move') + ' rated Best or Good</span></div>' +
        '<ul class="rv-counts">' + rows + '</ul>' + (tags ? '<div class="rv-tags">' + tags + '</div>' : '') + '</div>';
    }).join('') + '</div>';
  }

  /* ------------------------------------------------------------ graph */
  var G = { W: 640, H: 190, l: 76, r: 10, t: 8, b: 22, band: 22 };  // W, H, l set from the container

  function graphGeom(d) {
    var evals = d.evals;
    var cap = 8;
    evals.forEach(function (e) { if (e.mate == null) cap = Math.max(cap, Math.abs(e.score)); });
    cap = Math.ceil(cap * 1.1);
    var inner = G.H - G.t - G.b;
    var mid = G.t + inner / 2;
    var half = inner / 2 - G.band;          // heuristic half-height
    var step = (G.W - G.l - G.r) / Math.max(1, evals.length - 1);
    function x(i) { return G.l + i * step; }
    function y(e) {
      if (e.mate != null) {
        var redWins = e.mate > 0 || (e.mate === 0 && e.score > 0);
        return redWins ? G.t + G.band / 2 : G.t + inner - G.band / 2;
      }
      return mid - (e.score / cap) * half;
    }
    return { x: x, y: y, mid: mid, cap: cap, inner: inner, step: step };
  }

  function renderGraph() {
    return '<div class="rv-graph-wrap"><div class="rv-graph-cap"><span>Evaluation (Red\'s view)</span>' +
      '<span class="rv-graph-key"><span class="rv-dot is-red"></span>Red better<span class="rv-dot is-yellow"></span>Yellow better</span></div>' +
      '<div id="rv-graph"></div></div>';
  }

  /* Draw the SVG at the container's real pixel size so text is never stretched. */
  function drawGraph() {
    var holder = $('#rv-graph', panel);
    if (!holder || !R.data) return;
    G.W = Math.max(260, Math.round(holder.clientWidth || 640));
    G.H = G.W < 480 ? 160 : 190;
    G.l = G.W < 480 ? 62 : 76;
    holder.innerHTML = graphSvg(R.data);
    moveGraphCursor();
  }

  function graphSvg(d) {
    var g = graphGeom(d), ev = d.evals;
    var pts = ev.map(function (e, i) { return [g.x(i), g.y(e)]; });
    var line = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var area = line + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + g.mid + ' L' + pts[0][0].toFixed(1) + ' ' + g.mid + ' Z';
    var top = G.t, bot = G.t + g.inner;
    var s = '<svg class="rv-graph" viewBox="0 0 ' + G.W + ' ' + G.H + '" role="img" aria-label="Evaluation graph from Red\'s point of view: up is better for Red, down for Yellow. The top and bottom bands mark proven forced wins.">';
    s += '<defs><clipPath id="rv-clip-up"><rect x="0" y="0" width="' + G.W + '" height="' + g.mid + '"/></clipPath>' +
      '<clipPath id="rv-clip-down"><rect x="0" y="' + g.mid + '" width="' + G.W + '" height="' + (G.H - g.mid) + '"/></clipPath></defs>';
    s += '<rect class="rv-band is-red" x="' + G.l + '" y="' + top + '" width="' + (G.W - G.l - G.r) + '" height="' + G.band + '"/>';
    s += '<rect class="rv-band is-yellow" x="' + G.l + '" y="' + (bot - G.band) + '" width="' + (G.W - G.l - G.r) + '" height="' + G.band + '"/>';
    s += '<text class="rv-axis" x="' + (G.l - 6) + '" y="' + (top + G.band / 2 + 4) + '" text-anchor="end">Red wins</text>';
    s += '<text class="rv-axis" x="' + (G.l - 6) + '" y="' + (bot - G.band / 2 + 4) + '" text-anchor="end">Yellow wins</text>';
    s += '<text class="rv-axis" x="' + (G.l - 6) + '" y="' + (g.mid + 4) + '" text-anchor="end">0</text>';
    s += '<line class="rv-zero" x1="' + G.l + '" x2="' + (G.W - G.r) + '" y1="' + g.mid + '" y2="' + g.mid + '"/>';
    s += '<path class="rv-area is-red" clip-path="url(#rv-clip-up)" d="' + area + '"/>';
    s += '<path class="rv-area is-yellow" clip-path="url(#rv-clip-down)" d="' + area + '"/>';
    s += '<path class="rv-line" d="' + line + '"/>';
    // x ticks every 5 plies
    for (var i = 0; i < ev.length; i += 5) {
      s += '<text class="rv-axis" x="' + g.x(i).toFixed(1) + '" y="' + (G.H - 6) + '" text-anchor="middle">' + i + '</text>';
    }
    s += '<line class="rv-cursor" id="rv-cursor" x1="0" x2="0" y1="' + top + '" y2="' + bot + '"/>';
    // markers for non-best moves (placed at the position after the move)
    d.moves.forEach(function (m, k) {
      if (m.badge === 'best' || m.badge === 'good') return;
      var p = pts[k + 1];
      s += '<circle class="rv-mark is-' + m.badge + '" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="4.5"/>';
    });
    s += '<circle class="rv-sel" id="rv-sel" r="6" cx="0" cy="0"/>';
    // hit areas: one per move
    d.moves.forEach(function (m, k) {
      var e = ev[k + 1];
      s += '<rect class="rv-hit" data-move="' + k + '" x="' + (g.x(k + 1) - g.step / 2).toFixed(1) + '" y="0" width="' + g.step.toFixed(1) + '" height="' + G.H + '">' +
        '<title>Move ' + m.ply + ' (' + colourName(m.player) + ', column ' + (m.column + 1) + '): ' + BADGES[m.badge].label + '. Eval after: ' + A.escapeHtml(e.label) + '</title></rect>';
    });
    return s + '</svg>';
  }

  function moveGraphCursor() {
    if (!R.data || !R.data.moves.length) return;
    R.sel = A.clamp(R.sel, 0, R.data.moves.length - 1);
    var g = graphGeom(R.data);
    var i = A.clamp(R.sel + 1, 0, R.data.evals.length - 1), e = R.data.evals[i];
    if (!e) return;
    var cx = g.x(i), cy = g.y(e);
    var cur = $('#rv-cursor', panel), sel = $('#rv-sel', panel);
    if (cur) { cur.setAttribute('x1', cx); cur.setAttribute('x2', cx); }
    if (sel) { sel.setAttribute('cx', cx); sel.setAttribute('cy', cy); sel.setAttribute('class', 'rv-sel is-' + R.data.moves[R.sel].badge); }
  }

  /* ------------------------------------------------------------ list */
  function renderList(d) {
    return '<div class="rv-list-wrap"><div class="rv-list-head"><span>Moves</span><span class="rv-hint">' +
      '<span class="kbd">←</span><span class="kbd">→</span> step</span></div>' +
      '<ol class="rv-list" id="rv-list" role="listbox" tabindex="0" aria-label="Reviewed moves">' +
      d.moves.map(function (m, k) {
        var tags = m.tags.map(function (t) { return TAGS[t]; });
        var aria = 'Move ' + m.ply + ', ' + whoName(m.player) + ', column ' + (m.column + 1) + ', ' + BADGES[m.badge].label +
          (tags.length ? ', ' + tags.join(', ') : '');
        return '<li role="option" id="rv-m-' + k + '" data-move="' + k + '" aria-selected="false" aria-label="' + A.escapeHtml(aria) + '">' +
          '<span class="rv-num">' + m.ply + '.</span><span class="mini-disc p' + m.player + '"></span>' +
          '<span class="rv-who">' + A.escapeHtml(whoName(m.player)) + '</span>' +
          '<span class="rv-col">col ' + (m.column + 1) + '</span>' + badgeHtml(m.badge) +
          (m.tags.length ? '<span class="rv-row-tags">' + tagsHtml(m.tags) + '</span>' : '') + '</li>';
      }).join('') + '</ol></div>';
  }

  /* ------------------------------------------------------------ detail */
  function renderDetail() {
    var d = R.data, m = d.moves[R.sel];
    var after = d.evals[Math.min(R.sel + 1, d.evals.length - 1)] || { label: '—' };
    var sameBest = m.best_columns.indexOf(m.column) !== -1;
    var vals = m.values.map(function (v, c) {
      var f = fmtVal(v);
      var cls = (c === m.column ? ' is-played' : '') + (m.best_columns.indexOf(c) !== -1 && v != null ? ' is-best' : '');
      return '<div class="rv-val' + cls + '" title="Column ' + (c + 1) + ': ' + A.escapeHtml(f.title) + '">' +
        '<span class="rv-val-col">' + (c + 1) + '</span><span class="rv-val-num">' + f.text + '</span></div>';
    }).join('');
    var html = '<div class="rv-detail-head">' + badgeHtml(m.badge, true) +
      '<strong>' + m.ply + '. ' + A.escapeHtml(whoName(m.player)) + ' <span class="faint">(' + colourName(m.player) + ')</span> played column ' + (m.column + 1) + '</strong></div>' +
      (m.tags.length ? '<div class="rv-tags">' + tagsHtml(m.tags) + '</div>' : '') +
      '<p class="rv-comment">' + A.escapeHtml(m.comment) + '</p>' +
      '<p class="rv-best">' + A.icon(sameBest ? 'check' : 'bulb', 15) +
      '<span>' + (sameBest ? '' : '<strong>Best was column ' + (m.best_column + 1) + '.</strong> ') + A.escapeHtml(m.reason) + '</span></p>' +
      '<div class="rv-vals-head">Exact depth-' + d.depth + ' value of each column for ' + colourName(m.player) +
      (m.values.some(function (v) { return v != null && Math.abs(v) >= MATE; }) ? ' · W<i>n</i> / L<i>n</i> = forced win / loss in <i>n</i> moves' : '') + '</div>' +
      '<div class="rv-vals">' + vals + '</div>' +
      '<div class="rv-eval-after">Position after this move, from Red\'s view: <strong>' + A.escapeHtml(after.label) + '</strong></div>';
    $('#rv-detail-text', panel).innerHTML = html;
  }

  function renderBoard() {
    var m = R.data.moves[R.sel];
    var b = A.cloneBoard(m.board_before);
    var row = A.dropRow(b, m.column);
    b[row][m.column] = m.player;
    var last = R.sel === R.data.moves.length - 1;
    var winning = last && R.game && R.game.state && R.game.state.winner ? R.game.state.winning_cells : [];
    R.view.render(b, { last: [row, m.column], winning: winning });
    var cells = R.view.cells;
    panel.querySelectorAll('.rv-mark-played, .rv-mark-best').forEach(function (el) {
      el.classList.remove('rv-mark-played', 'rv-mark-best');
      el.removeAttribute('data-badge');
    });
    panel.querySelectorAll('.rv-ghost').forEach(function (el) { el.parentNode.removeChild(el); });
    cells[row][m.column].classList.add('rv-mark-played');
    cells[row][m.column].setAttribute('data-badge', m.badge);
    if (m.best_columns.indexOf(m.column) === -1) {
      var br = A.dropRow(m.board_before, m.best_column);
      var cell = cells[br][m.best_column];
      cell.classList.add('rv-mark-best');
      var ghost = document.createElement('div');
      ghost.className = 'rv-ghost p' + m.player;
      cell.appendChild(ghost);
    }
    var cap = $('#rv-board-cap', panel);
    cap.innerHTML = '<span><span class="rv-ring is-' + m.badge + '"></span>Played</span>' +
      (m.best_columns.indexOf(m.column) === -1 ? '<span><span class="rv-ring is-target"></span>Best move</span>' : '<span>' + A.icon('check', 13) + 'Played the best move</span>');
  }

  function select(k, opts) {
    if (!R.data || !R.data.moves.length) return;
    opts = opts || {};
    k = A.clamp(Number(k) || 0, 0, R.data.moves.length - 1);
    R.sel = k;
    var list = $('#rv-list', panel);
    if (!list) return;
    list.querySelectorAll('[aria-selected="true"]').forEach(function (li) { li.setAttribute('aria-selected', 'false'); });
    var li = $('#rv-m-' + k, panel);
    li.setAttribute('aria-selected', 'true');
    list.setAttribute('aria-activedescendant', li.id);
    // keep the row visible without scrolling the page
    var top = li.offsetTop - list.offsetTop, bottom = top + li.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top - 4;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
    renderBoard();
    renderDetail();
    moveGraphCursor();
    if (opts.focus) list.focus({ preventScroll: true });
  }

  function keyMoment(d) {
    var humanMove = -1, any = -1;
    d.moves.forEach(function (m, k) {
      var bad = m.badge === 'blunder' || m.badge === 'mistake' || m.tags.length;
      if (bad && any === -1) any = k;
      if (bad && humanMove === -1 && R.game && m.player === R.game.human) humanMove = k;
    });
    return humanMove !== -1 ? humanMove : any !== -1 ? any : d.moves.length - 1;
  }

  function renderReview(d) {
    var sub = 'Alpha-beta re-searched all ' + plural(d.moves.length, 'position') + ' at depth ' + d.depth +
      ', with an exact (full-window) score for every legal column · ' + A.fmtCompact(d.nodes) + ' nodes in ' + A.fmtMs(d.time_ms) + '.';
    var t = d.thresholds;
    panel.innerHTML = renderHead(sub) + renderSummary(d) + renderGraph() +
      '<div class="rv-main">' +
      '<div class="rv-detail"><div class="rv-board" id="rv-board"></div><div class="rv-board-cap" id="rv-board-cap"></div>' +
      '<div class="rv-detail-text" id="rv-detail-text" aria-live="polite"></div></div>' +
      renderList(d) + '</div>' +
      '<details class="rv-method"><summary>' + A.icon('info', 15) + 'How moves are graded</summary>' +
      '<p>For each position the engine plays every legal column and searches the reply with a full alpha-beta window, so each score is the exact depth-' + d.depth + ' minimax value (ordinary alpha-beta only gives bounds for the columns it rejects). ' +
      'The <em>loss</em> of a move is the best score minus the played score, in heuristic points (an open three is worth 5, an open two 2, a centre disc 3).</p>' +
      '<ul><li>' + badgeHtml('best') + ' loss 0 (ties count)</li><li>' + badgeHtml('good') + ' loss ≤ ' + t.good + ', or a slower forced win</li>' +
      '<li>' + badgeHtml('inaccuracy') + ' loss ≤ ' + t.inaccuracy + ', or losing sooner in an already lost position</li>' +
      '<li>' + badgeHtml('mistake') + ' loss ≤ ' + t.mistake + '</li><li>' + badgeHtml('blunder') + ' larger losses, and always for a <em>missed win</em> (a proven win was available and the move gives it up) or an <em>allowed forced loss</em> (the position was not lost before the move but is after it).</li></ul>' +
      '<p>Forced wins and losses found within the horizon are proofs; other scores are heuristic estimates. The graph averages depths ' + d.depth + ' and ' + (d.depth - 1) + ' to cancel the odd/even horizon effect; grading never uses those averaged numbers.</p></details>';
    R.view = new BoardView($('#rv-board', panel), { interactive: false, ghost: false, labels: true });
    // Pick the move before drawing: the graph cursor reads R.sel, which may
    // still point past the end of this (shorter) game.
    R.sel = A.clamp(keyMoment(d), 0, d.moves.length - 1);
    drawGraph();
    select(R.sel);
  }

  /* ------------------------------------------------------------ open / close */
  function show() {
    panel.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    panel.scrollIntoView({ behavior: A.reducedMotion() ? 'auto' : 'smooth', block: 'start' });
    panel.focus({ preventScroll: true });
  }

  function close() {
    var wasOpen = !panel.hidden;
    panel.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
    return wasOpen;
  }

  function openReview() {
    if (!R.game) { A.toast('Finish a game first, then review it.', { timeout: 2500 }); return; }
    if (R.data) { show(); drawGraph(); select(R.sel); return; }
    if (R.loading) return;
    var token = ++R.token;
    R.loading = true;
    A.setLoading(btn, true);
    renderLoading(R.game.moves.length);
    show();
    A.api('/api/analyze', { moves: R.game.moves.map(function (m) { return m.col; }) }, { errorTitle: 'Review failed' })
      .then(function (res) {
        if (token !== R.token) return;
        if (!res || !res.moves || !res.moves.length || !res.evals) throw new Error('The analysis came back empty.');
        // R.data is cached only once the review has rendered, so "Try again"
        // after a failure re-runs the analysis instead of the broken cache.
        R.data = res;
        try { renderReview(res); }
        catch (err) { R.data = null; throw err; }
        var list = $('#rv-list', panel);
        if (list) list.focus({ preventScroll: true });
      })
      .catch(function (err) {
        if (token !== R.token) return;
        R.data = null;
        R.sel = 0;
        renderError(err && err.message);
      })
      .then(function () {
        if (token !== R.token) return;
        R.loading = false;
        A.setLoading(btn, false);
      });
  }

  /* ------------------------------------------------------------ events */
  document.addEventListener('play:over', function (e) {
    R.token++;
    R.game = e.detail;
    R.data = null;
    R.sel = 0;
    R.loading = false;
    A.setLoading(btn, false);
    close();
  });
  document.addEventListener('play:reset', function () {
    R.token++;
    R.game = null;
    R.data = null;
    R.sel = 0;
    R.loading = false;
    A.setLoading(btn, false);
    close();
  });

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (R.data && !panel.hidden) drawGraph(); }, 120);
  });

  btn.setAttribute('aria-expanded', 'false');
  btn.addEventListener('click', openReview);

  panel.addEventListener('click', function (e) {
    var t = e.target;
    if (t.closest('[data-rv-close]')) { close(); btn.focus({ preventScroll: true }); return; }
    if (t.closest('[data-rv-retry]')) { R.loading = false; openReview(); return; }
    var hit = t.closest('[data-move]');
    if (hit && R.data) select(Number(hit.getAttribute('data-move')), { focus: hit.tagName.toLowerCase() === 'li' });
  });

  panel.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.preventDefault(); close(); btn.focus({ preventScroll: true }); return; }
    if (!R.data || e.target.id !== 'rv-list') return;
    var k = { ArrowUp: -1, ArrowDown: 1 }[e.key];
    if (k) { e.preventDefault(); select(R.sel + k); }
    else if (e.key === 'Home') { e.preventDefault(); select(0); }
    else if (e.key === 'End') { e.preventDefault(); select(R.data.moves.length - 1); }
  });

  // R opens the review; Left/Right step through moves while it is open.
  // Skips form controls, board columns (their own arrow-key focus moves) and
  // anything another handler already consumed; 1-7 / U / N / H stay play.js's.
  document.addEventListener('keydown', function (e) {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target;
    if (A.isTypingTarget(t, { allowSelect: e.key === 'r' || e.key === 'R' })) return;
    if (e.key === 'r' || e.key === 'R') {
      if (R.game) { e.preventDefault(); openReview(); }
      return;
    }
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if (panel.hidden || !R.data) return;
    if (t && t.closest && (t.closest('.board-col') || t.closest('input, select, textarea, .seg'))) return;
    e.preventDefault();
    select(R.sel + (e.key === 'ArrowLeft' ? -1 : 1));
  });
})();
