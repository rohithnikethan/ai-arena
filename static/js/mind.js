/* AI Arena: "AI Mind" panel: explanation, stats chips, column bars and a D3 search tree. */
(function () {
  'use strict';
  var A = window.Arena;
  var COLORS = { pos: '#b756f2', neg: '#0d9488', neutral: '#878c91' };

  function kindOf(type) { return type === 'mcts' ? 'mcts' : 'minimax'; }

  /* ------------------------------------------------------------------ */
  /* Alpha-beta bounds                                                   */
  /* ------------------------------------------------------------------ */
  /* Is a node's value exact, or only a bound? Returns 'upper' (true value <=
     value), 'lower' (true value >= value) or null (exact / not applicable).
     If the engine supplies node.bound we use it as is. Otherwise we apply the
     fail-soft window rule to the [alpha, beta] window the node was searched
     with (node.alpha / node.beta, root player's view, null = infinite):
     value <= alpha means an upper bound, value >= beta a lower bound. The
     column bars use the same rule on the root's children, so a "<=" in the
     bars and in the tree always agree. Proven wins/losses are shown as is. */
  function nodeBound(node, type) {
    if (!node) return null;
    if (Object.prototype.hasOwnProperty.call(node, 'bound')) {
      return node.bound === 'upper' || node.bound === 'lower' ? node.bound : null;
    }
    if (type !== 'alphabeta' || node.terminal || node.pruned) return null;
    var v = node.value;
    if (v == null || isNaN(v) || A.isWinValue(v) || A.isInfValue(v)) return null;
    var alpha = node.alpha == null ? -Infinity : node.alpha;
    var beta = node.beta == null ? Infinity : node.beta;
    if (v <= alpha) return 'upper';
    if (v >= beta) return 'lower';
    return null;
  }
  function boundPrefix(b) { return b === 'upper' ? '≤' : b === 'lower' ? '≥' : ''; }
  /* Per-column bounds for the bars: from the engine if given, else from the
     traced root children, else the old rule (alpha-beta: every non-chosen
     column is an upper bound). */
  function columnBounds(result, type) {
    var out = [null, null, null, null, null, null, null];
    if (!result || type !== 'alphabeta') return out;
    var given = result.column_bounds;
    if (Array.isArray(given)) {
      for (var i = 0; i < 7; i++) out[i] = given[i] === 'upper' || given[i] === 'lower' ? given[i] : null;
      return out;
    }
    var kids = result.tree && result.tree.children;
    var scores = result.column_scores || [];
    if (kids && kids.length) {
      kids.forEach(function (k) { if (k.move != null && k.move >= 0 && k.move < 7) out[k.move] = nodeBound(k, type); });
      return out;
    }
    for (var c = 0; c < 7; c++) {
      var v = scores[c];
      if (c !== result.column && v != null && !isNaN(v) && Math.abs(v) < 900000) out[c] = 'upper';
    }
    return out;
  }

  /* ------------------------------------------------------------------ */
  /* Value -> colour                                                     */
  /* ------------------------------------------------------------------ */
  function mix(a, b, t) {
    if (window.d3 && d3.interpolateRgb) return d3.interpolateRgb(a, b)(t);
    return t < 0.5 ? a : b;
  }
  /* Map a node to t in [-1, 1] (positive = good for the root player). */
  function nodeScore(d, kind, rootPlayer, scale) {
    if (kind === 'mcts') {
      var rate = null;
      if (d.value != null && d.value >= 0 && d.value <= 1) rate = d.value;
      else if (d.visits) {
        rate = d.wins / d.visits;
        // wins are counted for the player who made the move into this node
        if (d.player != null && rootPlayer != null && d.player !== rootPlayer) rate = 1 - rate;
      }
      return rate == null ? null : Math.max(-1, Math.min(1, (rate - 0.5) * 4));
    }
    var v = d.value;
    if (v == null || isNaN(v)) return null;
    if (Math.abs(v) >= 900000) return v > 0 ? 1 : -1;
    // heuristic values: normalise by the largest non-terminal magnitude in this tree
    return (v > 0 ? 1 : -1) * Math.min(1, Math.sqrt(Math.abs(v) / (scale || 1)) * 0.85);
  }
  function treeScale(tree) {
    var m = 0;
    (function walk(n) {
      if (n.value != null && Math.abs(n.value) < 900000) m = Math.max(m, Math.abs(n.value));
      (n.children || []).forEach(walk);
    })(tree);
    return m || 1;
  }
  function scoreColor(t) {
    if (t == null) return COLORS.neutral;
    return t >= 0 ? mix(COLORS.neutral, COLORS.pos, Math.min(1, t)) : mix(COLORS.neutral, COLORS.neg, Math.min(1, -t));
  }

  /* ------------------------------------------------------------------ */
  /* Column bars                                                         */
  /* ------------------------------------------------------------------ */
  function ColumnBars(root) {
    this.root = root;
    root.classList.add('col-bars', 'is-empty');
    var html = '';
    for (var c = 0; c < 7; c++) {
      html += '<div class="col-bar"><div class="col-bar-track"><div class="col-bar-fill"></div></div>' +
        '<span class="col-bar-label">—</span><span class="col-bar-sub">&nbsp;</span></div>';
    }
    root.innerHTML = html;
    this.bars = Array.prototype.slice.call(root.querySelectorAll('.col-bar'));
    root.setAttribute('role', 'img');
    root.setAttribute('aria-label', 'Per-column evaluation: waiting for the AI to think');
  }
  ColumnBars.prototype.clear = function () {
    this.root.classList.add('is-empty');
    this.bars.forEach(function (b) {
      b.className = 'col-bar';
      b.querySelector('.col-bar-fill').style.height = '0%';
      b.querySelector('.col-bar-label').textContent = '—';
      b.querySelector('.col-bar-sub').innerHTML = '&nbsp;';
      b.title = '';
    });
    this.root.setAttribute('aria-label', 'Per-column evaluation: waiting for the AI to think');
  };
  ColumnBars.prototype.render = function (result, type) {
    var kind = kindOf(type);
    var scores = (result && result.column_scores) || [];
    var visits = (result && result.column_visits) || [];
    var chosen = result ? result.column : null;
    var legal = [];
    for (var i = 0; i < 7; i++) if (scores[i] != null && !isNaN(scores[i])) legal.push(scores[i]);
    if (!legal.length) { this.clear(); this._markChosen(chosen); return; }
    this.root.classList.remove('is-empty');

    var finite = legal.filter(function (v) { return kind === 'mcts' || Math.abs(v) < 900000; });
    var lo = finite.length ? Math.min.apply(null, finite) : 0;
    var hi = finite.length ? Math.max.apply(null, finite) : 1;
    var bounds = columnBounds(result, type);
    var described = [];
    this.bars.forEach(function (bar, c) {
      var v = scores[c];
      var fill = bar.querySelector('.col-bar-fill');
      var label = bar.querySelector('.col-bar-label');
      var sub = bar.querySelector('.col-bar-sub');
      bar.className = 'col-bar';
      if (v == null || isNaN(v)) {
        bar.classList.add('is-illegal');
        fill.style.height = '0%';
        label.textContent = '—';
        sub.innerHTML = '&nbsp;';
        bar.title = 'Column ' + (c + 1) + ': not a legal move';
        return;
      }
      var h;
      if (kind === 'mcts') h = Math.max(4, Math.min(100, v * 100));
      else if (v >= 900000) h = 100;
      else if (v <= -900000) h = 4;
      else if (hi - lo < 1e-9) h = 55;
      else h = 14 + (v - lo) / (hi - lo) * 74;
      fill.style.height = h.toFixed(1) + '%';
      label.textContent = A.fmtValue(v, kind);
      if (kind === 'mcts' && visits[c] != null) sub.textContent = A.fmtCompact(visits[c]) + ' visits';
      else sub.innerHTML = '&nbsp;';
      if (kind !== 'mcts' && v <= -900000) bar.classList.add('is-loss');
      if (c === chosen) bar.classList.add('is-best');
      // alpha-beta cut-offs: such root scores are bounds, not exact values
      var bound = bounds[c];
      if (bound) { bar.classList.add('is-bound'); label.textContent = boundPrefix(bound) + label.textContent; }
      bar.title = 'Column ' + (c + 1) + ': ' + (bound === 'upper' ? 'at most ' : bound === 'lower' ? 'at least ' : '') + A.fmtValueLong(v, kind) +
        (bound === 'upper' ? ' (upper bound: pruning proved it cannot beat the chosen move)' : '') +
        (bound === 'lower' ? ' (lower bound: the search stopped once it was good enough)' : '') +
        (kind === 'mcts' && visits[c] != null ? ' (' + A.fmtInt(visits[c]) + ' visits)' : '');
      described.push('column ' + (c + 1) + ' ' + (bound === 'upper' ? 'at most ' : bound === 'lower' ? 'at least ' : '') + A.fmtValue(v, kind));
    });
    this.root.setAttribute('aria-label', 'Per-column evaluation: ' + described.join(', '));
  };
  ColumnBars.prototype._markChosen = function (col) {
    this.bars.forEach(function (b, c) { b.classList.toggle('is-best', c === col); });
  };

  /* ------------------------------------------------------------------ */
  /* Tree view (D3)                                                      */
  /* ------------------------------------------------------------------ */
  var treeCount = 0;
  var allTrees = [];
  var HINT = 'Scroll to zoom · drag to pan · click a node to expand';
  var HINT_LONG = 'Zoom: mouse wheel or pinch. Pan: drag (two fingers on a touch screen). ' +
    'Expand or collapse a node: click it, or focus it with Tab and press Enter. Arrow keys move between nodes.';
  /* Every tree shares one Tree/Radial setting, so switching it in one panel
     (Arena has two) updates the others at once. */
  function setLayoutAll(layout) {
    A.store.set('tree-layout', layout);
    allTrees.forEach(function (t) {
      t.box.querySelectorAll('input[type="radio"]').forEach(function (inp) { inp.checked = inp.value === layout; });
      if (t.layout === layout) return;
      t.layout = layout;
      t.draw(true);
    });
  }
  function TreeView(box, opts) {
    opts = opts || {};
    this.box = box;
    this.layout = A.store.get('tree-layout', 'tree') === 'radial' ? 'radial' : 'tree';
    this.data = null;
    this.kind = 'minimax';
    this.rootPlayer = 1;
    this.expanded = {};
    this.uid = ++treeCount;
    this.focusId = null;
    this._build();
    allTrees.push(this);
  }

  TreeView.prototype._build = function () {
    var self = this;
    var n = this.uid;
    this.box.classList.add('tree-box');
    this.box.innerHTML =
      '<div class="tree-toolbar">' +
      '  <div class="seg sm" role="radiogroup" aria-label="Tree layout">' +
      '    <label><input type="radio" name="tree-layout-' + n + '" value="tree"' + (this.layout === 'tree' ? ' checked' : '') + '><span>Tree</span></label>' +
      '    <label><input type="radio" name="tree-layout-' + n + '" value="radial"' + (this.layout === 'radial' ? ' checked' : '') + '><span>Radial</span></label>' +
      '  </div>' +
      '  <button type="button" class="icon-btn sm tree-help" data-help title="' + HINT_LONG + '" aria-label="How to explore the tree">?</button>' +
      '  <button type="button" class="icon-btn sm" data-fit title="Re-centre: fit the whole tree in view" aria-label="Fit tree to view">' + A.icon('fit', 15) + '</button>' +
      '  <button type="button" class="icon-btn sm" data-expand title="Expand tree to full screen" aria-label="Expand tree to full screen" aria-pressed="false">' + A.icon('maximize', 15) + '</button>' +
      '</div>' +
      '<div class="tree-hint" hidden>' + HINT + '</div>' +
      '<svg class="tree-svg" role="group" aria-label="Search tree" aria-roledescription="search tree"></svg>' +
      '<div class="tree-legend" hidden></div>' +
      '<div class="tree-tip" role="tooltip"></div>' +
      '<div class="empty" data-empty><span class="empty-icon">' + A.icon('tree', 22) + '</span><strong>No search tree yet</strong><span>The AI\'s game tree appears here after it moves.</span></div>';
    this.svgEl = this.box.querySelector('svg.tree-svg');
    this.tip = this.box.querySelector('.tree-tip');
    this.legend = this.box.querySelector('.tree-legend');
    this.hintEl = this.box.querySelector('.tree-hint');
    this.emptyEl = this.box.querySelector('[data-empty]');
    this.box.querySelectorAll('input[type="radio"]').forEach(function (inp) {
      inp.addEventListener('change', function () {
        if (inp.checked) setLayoutAll(inp.value);
      });
    });
    this.box.querySelector('[data-fit]').addEventListener('click', function () { self.fit(true); });
    this.box.querySelector('[data-help]').addEventListener('click', function () {
      A.toast(HINT_LONG, { title: 'Exploring the search tree', icon: 'tree', timeout: 7000 });
    });
    this.expandBtn = this.box.querySelector('[data-expand]');
    // requestFullscreen must run synchronously inside the click.
    this.expandBtn.addEventListener('click', function () { A.fullscreen.toggle(self.box); });
    this.box.addEventListener('arena:fullscreen', function (e) {
      if (e.target === self.box) self._syncExpand();
    });

    if (!window.d3) {
      this.setEmpty('Tree view unavailable', 'The D3 library could not be loaded (offline?). Everything else still works.', true);
      return;
    }
    this.svg = d3.select(this.svgEl);
    this.g = this.svg.append('g');
    this.gLinks = this.g.append('g');
    this.gNodes = this.g.append('g');
    /* Touch: a single finger scrolls the page (unless the tree is expanded to
       full screen); pinch or a two-finger drag zooms and pans the tree. */
    this.zoom = d3.zoom().scaleExtent([0.12, 5])
      .filter(function (e) {
        if (e.type === 'touchstart') return e.touches.length >= 2 || A.fullscreen.isActive(self.box);
        return (!e.ctrlKey || e.type === 'wheel') && !e.button;
      })
      .on('zoom', function (e) {
        self.g.attr('transform', e.transform);
        if (e.sourceEvent) self._hideTip();
      });
    this.svg.call(this.zoom).on('dblclick.zoom', null);
    this.svgEl.addEventListener('keydown', function (e) { self._onKey(e); });
    if (window.ResizeObserver) {
      var lastW = 0, lastH = 0;
      new ResizeObserver(function () {
        var w = self.box.clientWidth, h = self.box.clientHeight;
        if (self.data && (Math.abs(w - lastW) > 30 || Math.abs(h - lastH) > 30)) { lastW = w; lastH = h; self.fit(false); }
      }).observe(this.box);
    }
  };

  TreeView.prototype._syncExpand = function () {
    var on = A.fullscreen.isActive(this.box);
    var label = on ? 'Exit full-screen tree (Esc)' : 'Expand tree to full screen';
    this.box.classList.toggle('is-expanded', on);
    this.expandBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    this.expandBtn.setAttribute('aria-label', label);
    this.expandBtn.setAttribute('title', label);
    this.expandBtn.innerHTML = A.icon(on ? 'minimize' : 'maximize', 15);
    var self = this;
    // refit once the new size has been laid out
    requestAnimationFrame(function () { requestAnimationFrame(function () { self.fit(false); }); });
  };

  TreeView.prototype.setEmpty = function (title, msg, isError) {
    this.data = null;
    if (this.gLinks) { this.gLinks.selectAll('*').remove(); this.gNodes.selectAll('*').remove(); }
    this.emptyEl.hidden = false;
    this.emptyEl.classList.toggle('is-error', !!isError);
    this.emptyEl.innerHTML = '<span class="empty-icon">' + A.icon(isError ? 'alert' : 'tree', 22) + '</span><strong>' + A.escapeHtml(title) + '</strong><span>' + A.escapeHtml(msg) + '</span>';
    this.legend.hidden = true;
    this.hintEl.hidden = true;
    this._hideTip();
  };

  TreeView.prototype.setLoading = function () {
    this.setEmpty('Searching…', 'Building the game tree.', false);
    this.emptyEl.querySelector('.empty-icon').innerHTML = '<span class="spinner"></span>';
  };

  TreeView.prototype.render = function (tree, opts) {
    opts = opts || {};
    if (!this.svg) return;
    if (!tree) {
      this.setEmpty('No tree for this agent', opts.emptyMsg || 'This agent does not search a game tree, so there is nothing to draw.', false);
      return;
    }
    this.kind = kindOf(opts.type);
    this.type = opts.type;
    this.rootPlayer = opts.player || tree.player || 1;
    this.data = tree;
    this.scale = treeScale(tree);
    // assign ids & depths, default expansion (depth < 2, plus the best line)
    var self = this, seq = 0;
    this.expanded = {};
    (function walk(node, depth) {
      if (node.id == null) node.id = 'n' + (seq++);
      node.__depth = depth;
      var kids = node.children || [];
      if (kids.length && (depth === 0 || node.best)) self.expanded[node.id] = true;
      kids.forEach(function (k) { walk(k, depth + 1); });
    })(tree, 0);
    this.emptyEl.hidden = true;
    this.hintEl.hidden = false;
    this._renderLegend();
    this.draw(true);
  };

  TreeView.prototype._renderLegend = function () {
    var mcts = this.kind === 'mcts';
    this.legend.hidden = false;
    this.legend.innerHTML =
      '<span><i class="lg-scale"></i>' + (mcts ? 'win rate low → high' : 'bad → good for AI') + '</span>' +
      '<span><i class="lg-best"></i>chosen line</span>' +
      (mcts ? '<span>size = visits</span>' : '<span><i class="lg-pruned"></i>pruned ✂</span>');
  };

  TreeView.prototype.draw = function (refit) {
    if (!this.data || !this.svg) return;
    var self = this;
    var radial = this.layout === 'radial';
    var root = d3.hierarchy(this.data, function (d) {
      if (!d.children || !d.children.length) return null;
      return (radial || self.expanded[d.id]) ? d.children : null;
    });
    var maxVisits = 1;
    root.each(function (n) { if (n.data.visits && n.depth > 0) maxVisits = Math.max(maxVisits, n.data.visits); });
    var mcts = this.kind === 'mcts';
    var rScale = function (n) {
      if (n.depth === 0) return 8;
      if (mcts && n.data.visits != null) return (radial && n.depth >= 3 ? 1.5 : 2.5) + (radial ? 5.5 : 7.5) * Math.sqrt(n.data.visits / maxVisits);
      return radial ? (n.depth >= 3 ? 2.5 : 4) : 5.5;
    };

    var pos;
    if (radial) {
      var leaves = root.leaves().length;
      var R = Math.max(110, Math.min(250, leaves * 0.8)) * Math.max(1, root.height) / 3;
      d3.tree().size([2 * Math.PI, R]).separation(function (a, b) { return (a.parent === b.parent ? 1 : 2) / Math.max(1, a.depth); })(root);
      pos = function (n) { var a = n.x - Math.PI / 2; return [n.y * Math.cos(a), n.y * Math.sin(a)]; };
    } else {
      d3.tree().nodeSize([20, 150]).separation(function (a, b) { return a.parent === b.parent ? 1 : 1.35; })(root);
      pos = function (n) { return [n.y, n.x]; };
    }

    var links = root.links();
    var linkGen = radial
      ? d3.linkRadial().angle(function (d) { return d.x; }).radius(function (d) { return d.y; })
      : d3.linkHorizontal().x(function (d) { return d.y; }).y(function (d) { return d.x; });

    var dur = A.reducedMotion() ? 0 : 350;
    var linkSel = this.gLinks.selectAll('path.tree-link').data(links, function (d) { return d.target.data.id; });
    linkSel.exit().remove();
    linkSel.enter().append('path').attr('class', 'tree-link')
      .merge(linkSel)
      .attr('class', function (d) {
        return 'tree-link' + (isOnBest(d.target) ? ' is-best' : '') + (d.target.data.pruned ? ' is-pruned' : '');
      })
      .attr('d', linkGen);
    // best links on top
    this.gLinks.selectAll('path.is-best').raise();

    var nodeSel = this.gNodes.selectAll('g.tree-node').data(root.descendants(), function (d) { return d.data.id; });
    nodeSel.exit().remove();
    var enter = nodeSel.enter().append('g').attr('class', 'tree-node');
    enter.append('circle');
    enter.append('text').attr('class', 'lbl');
    enter.append('text').attr('class', 'scissor');
    var all = enter.merge(nodeSel);
    all.attr('class', function (d) {
      var hidden = d.data.children && d.data.children.length && !d.children;
      return 'tree-node' + (d.data.pruned ? ' is-pruned' : '') + (isOnBest(d) ? ' is-best' : '') + (hidden ? ' is-collapsed' : '');
    })
      .attr('transform', function (d) { var p = pos(d); return 'translate(' + p[0].toFixed(1) + ',' + p[1].toFixed(1) + ')'; })
      .attr('role', 'button')
      .attr('aria-label', function (d) { return self._nodeLabel(d); })
      .attr('aria-expanded', function (d) {
        if (radial || !d.data.children || !d.data.children.length) return null;
        return d.children ? 'true' : 'false';
      });
    // roving tabindex: Tab enters the tree once, arrow keys move inside it
    var ids = root.descendants().map(function (d) { return d.data.id; });
    if (ids.indexOf(this.focusId) === -1) this.focusId = root.data.id;
    all.attr('tabindex', function (d) { return d.data.id === self.focusId ? 0 : -1; });
    this._visible = root.descendants();
    this._pos = pos;
    all.select('circle')
      .attr('r', rScale)
      .attr('fill', function (d) { return d.depth === 0 ? 'url(#root-grad-' + self.uid + ')' : scoreColor(nodeScore(d.data, self.kind, self.rootPlayer, self.scale)); });
    all.select('text.lbl')
      .attr('x', function (d) { return radial ? 0 : (d.children ? -10 : 10); })
      .attr('y', function (d) { return radial ? -rScale(d) - 4 : 3.5; })
      .attr('text-anchor', function (d) { return radial ? 'middle' : (d.children ? 'end' : 'start'); })
      .text(function (d) {
        if (d.depth === 0) return radial ? 'now' : 'now';
        if (radial && d.depth > 1) return '';
        var col = d.data.move != null ? 'c' + (d.data.move + 1) : '';
        if (radial || d.children) return col;
        var v = mcts ? (d.data.visits != null ? A.fmtCompact(d.data.visits) + 'v' : '')
          : (d.data.value != null ? boundPrefix(nodeBound(d.data, self.type)) + A.fmtValue(d.data.value, 'minimax') : '');
        var hidden = d.data.children && d.data.children.length && !d.children ? '  ▸' + d.data.children.length : '';
        return col + (v ? ' · ' + v : '') + hidden;
      });
    all.select('text.scissor')
      .attr('x', function (d) { return rScale(d) + 3; })
      .attr('y', function (d) { return radial ? 4 : -6; })
      .text(function (d) { return d.data.pruned ? '✂' : ''; });

    all.on('mouseenter', function (e, d) { self._showTip(e, d); })
      .on('mousemove', function (e, d) { self._moveTip(e); })
      .on('mouseleave', function () { self._hideTip(); })
      .on('focus', function (e, d) { self.focusId = d.data.id; self._showTip(null, d, this); })
      .on('blur', function () { self._hideTip(); })
      .on('click', function (e, d) {
        self.focusId = d.data.id;
        self._toggle(d);
      });

    this._ensureDefs();
    this.svg.attr('aria-label', 'Search tree with ' + root.descendants().length + ' visible nodes');
    if (refit) this.fit(false);
    void dur;
  };

  function isOnBest(n) {
    // a node is on the chosen line if it and all its ancestors are flagged best
    var cur = n;
    while (cur) {
      if (cur.depth > 0 && !cur.data.best) return false;
      cur = cur.parent;
    }
    return true;
  }

  TreeView.prototype._ensureDefs = function () {
    if (this.svg.select('defs').size()) return;
    var defs = this.svg.insert('defs', ':first-child');
    var g = defs.append('radialGradient').attr('id', 'root-grad-' + this.uid).attr('cx', '35%').attr('cy', '30%');
    g.append('stop').attr('offset', '0%').attr('stop-color', '#f3e8ff');
    g.append('stop').attr('offset', '55%').attr('stop-color', '#a444e8');
    g.append('stop').attr('offset', '100%').attr('stop-color', '#5a1582');
  };

  TreeView.prototype.fit = function (animated) {
    if (!this.svg || !this.data) return;
    var w = this.box.clientWidth, h = this.box.clientHeight;
    if (!w || !h) return;
    var bbox;
    try { bbox = this.g.node().getBBox(); } catch (e) { return; }
    if (!bbox || !bbox.width && !bbox.height) return;
    var pad = 36;
    var scale = Math.min((w - pad * 2) / Math.max(bbox.width, 1), (h - pad * 2 - 30) / Math.max(bbox.height, 1));
    var maxScale = (this.layout === 'radial' ? 1.6 : 1.25) * (A.fullscreen.isActive(this.box) ? 1.6 : 1);
    scale = Math.max(0.12, Math.min(maxScale, scale));
    var tx = w / 2 - (bbox.x + bbox.width / 2) * scale;
    var ty = (h - 24) / 2 - (bbox.y + bbox.height / 2) * scale;
    var t = d3.zoomIdentity.translate(tx, ty).scale(scale);
    if (animated && !A.reducedMotion()) this.svg.transition().duration(450).call(this.zoom.transform, t);
    else this.svg.call(this.zoom.transform, t);
  };

  TreeView.prototype._toggle = function (d) {
    if (this.layout === 'radial' || !d.data.children || !d.data.children.length) return false;
    this.expanded[d.data.id] = !this.expanded[d.data.id];
    this.draw(false);
    return true;
  };

  TreeView.prototype._nodeLabel = function (d) {
    var n = d.data;
    var parts = [d.depth === 0 ? 'Current position' : 'Column ' + (n.move + 1) + ', ply ' + d.depth];
    if (this.kind === 'mcts') {
      if (n.visits != null) parts.push(A.fmtInt(n.visits) + ' visits');
      if (n.visits) parts.push('win rate ' + Math.round(n.wins / n.visits * 100) + '%');
    } else if (n.value != null) {
      var b = nodeBound(n, this.type);
      parts.push('value ' + (b === 'upper' ? 'at most ' : b === 'lower' ? 'at least ' : '') + A.fmtValueLong(n.value, 'minimax') +
        (b ? (b === 'upper' ? ' (upper bound)' : ' (lower bound)') : ''));
    }
    if (n.pruned) parts.push('pruned');
    if (isOnBest(d) && d.depth > 0) parts.push('on the chosen line');
    if (n.children && n.children.length) parts.push(n.children.length + ' children' + (this.layout === 'radial' ? '' : d.children ? ', expanded' : ', collapsed'));
    return parts.join(', ');
  };

  TreeView.prototype._focusNode = function (id) {
    this.focusId = id;
    var el = null;
    this.gNodes.selectAll('g.tree-node').attr('tabindex', function (d) {
      if (d.data.id === id) el = this;
      return d.data.id === id ? 0 : -1;
    });
    if (!el) return;
    el.focus({ preventScroll: true });
    // bring the node into view if it is outside the visible area
    var r = el.getBoundingClientRect(), b = this.box.getBoundingClientRect();
    if (r.left < b.left + 20 || r.right > b.right - 20 || r.top < b.top + 50 || r.bottom > b.bottom - 50) {
      var d = d3.select(el).datum(), p = this._pos(d);
      this.svg.call(this.zoom.translateTo, p[0], p[1]);
      this._showTip(null, d, el);
    }
  };

  TreeView.prototype._onKey = function (e) {
    var t = e.target.closest && e.target.closest('g.tree-node');
    if (!t || !this._visible) return;
    var d = d3.select(t).datum(), list = this._visible, i = list.indexOf(d);
    var target = null;
    switch (e.key) {
      case 'Enter': case ' ':
        e.preventDefault();
        if (this._toggle(d)) this._focusNode(d.data.id);
        return;
      case 'ArrowDown': target = list[i + 1]; break;
      case 'ArrowUp': target = list[i - 1]; break;
      case 'ArrowRight':
        if (d.children && d.children.length) target = d.children[0];
        else if (this._toggle(d)) { e.preventDefault(); this._focusNode(d.data.id); return; }
        break;
      case 'ArrowLeft':
        if (d.children && this.layout !== 'radial' && d.depth > 0) { e.preventDefault(); this._toggle(d); this._focusNode(d.data.id); return; }
        target = d.parent;
        break;
      case 'Home': target = list[0]; break;
      case 'End': target = list[list.length - 1]; break;
      case 'Escape': this._hideTip(); return;
      default: return;
    }
    e.preventDefault();
    if (target) this._focusNode(target.data.id);
  };

  TreeView.prototype._showTip = function (e, d, el) {
    var n = d.data, mcts = this.kind === 'mcts';
    var player = n.player === 2 ? 2 : 1;
    var title = d.depth === 0 ? 'Current position' : 'Column ' + (n.move + 1);
    var rows = [];
    if (d.depth > 0) rows.push(['Ply', d.depth]);
    if (mcts) {
      if (n.visits != null) rows.push(['Visits', A.fmtInt(n.visits)]);
      if (n.wins != null) rows.push(['Wins', (Math.round(n.wins * 10) / 10).toLocaleString('en-US')]);
      if (n.visits) rows.push(['Win rate', Math.round(n.wins / n.visits * 100) + '%']);
    } else {
      var nb = nodeBound(n, this.type);
      rows.push(['Value', n.value != null ? (nb ? boundPrefix(nb) + ' ' : '') + A.fmtValueLong(n.value, 'minimax') + (nb ? (nb === 'upper' ? ' (upper bound)' : ' (lower bound)') : '') : '—']);
      if (this.type === 'alphabeta' || n.alpha != null || n.beta != null) {
        rows.push(['α (alpha)', n.alpha != null ? A.fmtValue(n.alpha, 'minimax') : '−∞']);
        rows.push(['β (beta)', n.beta != null ? A.fmtValue(n.beta, 'minimax') : '+∞']);
      }
    }
    if (n.children && n.children.length) rows.push(['Children', n.children.length]);
    var nbound = mcts ? null : nodeBound(n, this.type);
    var note = n.pruned ? 'Pruned: α ≥ β, so this branch cannot change the value backed up to the root.'
      : n.terminal ? 'Terminal position: the game ends here.'
        : nbound === 'upper' ? 'Upper bound: a cut-off below proved this line is worth at most this much, which is all the search needed to know.'
        : nbound === 'lower' ? 'Lower bound: a cut-off below proved this line is worth at least this much, which is all the search needed to know.'
        : isOnBest(d) && d.depth > 0 ? 'On the principal (chosen) line.' : '';
    this.tip.innerHTML =
      '<div class="tt-title">' + (d.depth > 0 ? '<span class="mini-disc p' + player + '"></span>' : A.icon('cpu', 14)) + A.escapeHtml(title) + '</div>' +
      '<dl>' + rows.map(function (r) { return '<dt>' + A.escapeHtml(r[0]) + '</dt><dd>' + A.escapeHtml(r[1]) + '</dd>'; }).join('') + '</dl>' +
      (note ? '<div class="tt-note">' + A.escapeHtml(note) + '</div>' : '');
    this.tip.classList.add('is-visible');
    if (e) { this._moveTip(e); return; }
    // keyboard focus: place the tooltip next to the node
    var r = (el || this.box).getBoundingClientRect();
    this._moveTip({ clientX: r.right, clientY: r.top + r.height / 2 });
  };
  TreeView.prototype._moveTip = function (e) {
    var rect = this.box.getBoundingClientRect();
    var x = e.clientX - rect.left + 14, y = e.clientY - rect.top + 14;
    var tw = this.tip.offsetWidth, th = this.tip.offsetHeight;
    if (x + tw > rect.width - 6) x = e.clientX - rect.left - tw - 14;
    if (y + th > rect.height - 6) y = e.clientY - rect.top - th - 14;
    this.tip.style.left = Math.max(6, x) + 'px';
    this.tip.style.top = Math.max(6, y) + 'px';
  };
  TreeView.prototype._hideTip = function () { this.tip.classList.remove('is-visible'); };

  /* ------------------------------------------------------------------ */
  /* Mind panel                                                          */
  /* ------------------------------------------------------------------ */
  /**
   * new MindPanel(root, {title, subtitle, compact, bars: element|null, owner: html})
   */
  function MindPanel(root, opts) {
    opts = opts || {};
    this.root = root;
    this.compact = !!opts.compact;
    root.classList.add('mind');
    if (this.compact) root.classList.add('compact');
    root.innerHTML =
      '<div class="mind-head">' +
      '  <div><div class="card-title">' + (opts.owner || A.icon('cpu', 18)) + '<span data-title>' + A.escapeHtml(opts.title || 'AI Mind') + '</span></div>' +
      '  <div class="card-sub" data-subtitle>' + A.escapeHtml(opts.subtitle || 'What the AI considered on its last move') + '</div></div>' +
      '  <span class="pill" data-status><span class="dot"></span>Idle</span>' +
      '</div>' +
      '<div class="mind-explain is-placeholder" data-explain>' + A.icon('bulb', 18) + '<span data-explain-text>' + A.escapeHtml(opts.placeholder || 'Make a move and the AI will explain its reply here.') + '</span></div>' +
      '<div class="chips' + (this.compact ? ' compact' : '') + '">' +
      chip('nodes', 'layers', 'Nodes') + chip('pruned', 'scissors', 'Pruned') + chip('time', 'clock', 'Time') + chip('speed', 'zap', 'Nodes/s') +
      '</div>' +
      '<div class="mind-pv" data-pv hidden></div>' +
      '<div data-tree></div>';
    this.statusEl = root.querySelector('[data-status]');
    this.explainEl = root.querySelector('[data-explain]');
    this.explainText = root.querySelector('[data-explain-text]');
    this.pvEl = root.querySelector('[data-pv]');
    this.chipEls = {};
    var self = this;
    root.querySelectorAll('[data-chip]').forEach(function (el) { self.chipEls[el.getAttribute('data-chip')] = el; });
    this.tree = new TreeView(root.querySelector('[data-tree]'));
    this.bars = opts.bars ? new ColumnBars(opts.bars) : null;
    this.lastResult = null;
  }
  function chip(key, ic, label) {
    return '<div class="chip" data-chip="' + key + '"><div class="chip-label">' + A.icon(ic, 13) + '<span data-chip-label>' + label + '</span></div><div class="chip-value" data-chip-value>—</div></div>';
  }

  MindPanel.prototype.setStatus = function (kind, text) {
    var cls = { idle: '', think: 'is-think', good: 'is-good', bad: 'is-bad', red: 'is-red', yellow: 'is-yellow' }[kind] || '';
    this.statusEl.className = 'pill ' + cls;
    this.statusEl.innerHTML = (kind === 'think' ? '<span class="spinner"></span>' : '<span class="dot"></span>') + A.escapeHtml(text);
  };
  MindPanel.prototype.setTitle = function (title, subtitle) {
    if (title != null) this.root.querySelector('[data-title]').textContent = title;
    if (subtitle != null) this.root.querySelector('[data-subtitle]').textContent = subtitle;
  };
  MindPanel.prototype._setChip = function (key, value, label) {
    var el = this.chipEls[key];
    if (!el) return;
    el.querySelector('[data-chip-value]').textContent = value;
    if (label) el.querySelector('[data-chip-label]').textContent = label;
  };
  MindPanel.prototype._explain = function (text, state) {
    this.explainEl.classList.toggle('is-placeholder', state === 'placeholder');
    this.explainEl.classList.toggle('is-thinking', state === 'thinking');
    if (state === 'thinking') {
      this.explainText.innerHTML = A.escapeHtml(text) + '<span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span>';
    } else {
      this.explainText.textContent = text;
    }
  };

  MindPanel.prototype.reset = function (message) {
    this.lastResult = null;
    this.setStatus('idle', 'Idle');
    this._explain(message || 'Make a move and the AI will explain its reply here.', 'placeholder');
    ['nodes', 'pruned', 'time', 'speed'].forEach(function (k) { this._setChip(k, '—'); }, this);
    this._setChip('pruned', '—', 'Pruned');
    this.pvEl.hidden = true;
    this.tree.setEmpty('No search tree yet', 'The AI\'s game tree appears here after it moves.');
    if (this.bars) this.bars.clear();
  };

  MindPanel.prototype.thinking = function (label) {
    this.setStatus('think', 'Thinking');
    this._explain((label || 'The AI') + ' is searching the game tree', 'thinking');
    this.tree.setLoading();
  };

  MindPanel.prototype.error = function (msg) {
    this.setStatus('bad', 'Error');
    this._explain(msg || 'Something went wrong while the AI was thinking.', 'placeholder');
    this.tree.setEmpty('Search failed', msg || 'The request did not complete.', true);
  };

  /** Show a choose_move result. ctx: {type, player} */
  MindPanel.prototype.show = function (res, ctx) {
    ctx = ctx || {};
    this.lastResult = { res: res, ctx: ctx };
    var type = ctx.type || 'alphabeta';
    var s = res.stats || {};
    this.setStatus(ctx.player === 2 ? 'yellow' : 'red', 'Played column ' + (res.column + 1));
    this._explain(res.explanation || ('Chose column ' + (res.column + 1) + '.'), 'done');
    this._setChip('nodes', A.fmtCompact(s.nodes));
    if (type === 'mcts') this._setChip('pruned', A.fmtCompact(s.iterations != null ? s.iterations : ctx.iterations), 'Sims');
    else this._setChip('pruned', A.fmtCompact(s.pruned), 'Pruned');
    this._setChip('time', A.fmtMs(s.time_ms));
    this._setChip('speed', A.fmtCompact(s.nodes_per_sec));

    var pv = res.principal_variation || [];
    if (pv.length > 1) {
      var p = ctx.player || 1;
      this.pvEl.hidden = false;
      this.pvEl.innerHTML = '<span>Expected line:</span>' + pv.slice(0, 8).map(function (c, i) {
        var who = (i % 2 === 0) ? p : (3 - p);
        return '<span class="pv-move"><span class="mini-disc p' + who + '"></span>' + (c + 1) + '</span>';
      }).join('');
    } else {
      this.pvEl.hidden = true;
    }
    var depthInfo = s.depth != null ? 'depth ' + s.depth : (s.iterations != null ? A.fmtInt(s.iterations) + ' simulations' : '');
    this.tree.render(res.tree, {
      type: type, player: ctx.player,
      emptyMsg: type === 'random' ? 'Random play does not search: it simply picks any legal column.'
        : type === 'greedy' ? 'Greedy looks only one move ahead, so there is no deep tree to draw.'
          : 'No tree was returned for this move.'
    });
    if (depthInfo) this.tree.svgEl.setAttribute('aria-label', 'Search tree (' + depthInfo + ')');
    if (this.bars) this.bars.render(res, type);
  };

  MindPanel.prototype.retheme = function () {
    if (this.tree && this.tree.data) this.tree.draw(false);
  };

  document.addEventListener('themechange', function () {
    // node colours are theme-independent; strokes use CSS variables, but redraw to refresh fills
    MindPanel._all.forEach(function (m) { m.retheme(); });
  });
  MindPanel._all = [];
  var Orig = MindPanel;
  function TrackedMindPanel(root, opts) { Orig.call(this, root, opts); MindPanel._all.push(this); }
  TrackedMindPanel.prototype = Orig.prototype;
  TrackedMindPanel._all = MindPanel._all;

  window.MindPanel = TrackedMindPanel;
  window.MindPanel.nodeBound = nodeBound;
  window.ColumnBars = ColumnBars;
  window.TreeView = TreeView;
})();
