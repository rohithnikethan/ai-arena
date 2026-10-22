/* AI Arena: "Step through alpha-beta" debugger on the Learn page.
   The animation is not scripted: we really run minimax / alpha-beta (fail-soft,
   as in the pseudocode on the page) over a small tree, record an event trace,
   turn every event into a state snapshot, and replay the snapshots on an SVG. */
(function () {
  'use strict';

  var INF = Infinity;
  var LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

  /* ================================================================== */
  /* Core: trees, search, trace (DOM-free so it can be tested in Node)   */
  /* ================================================================== */

  /* Presets are nested arrays; numbers are leaves. The root is always MAX and
     layers alternate MAX / MIN. */
  var PRESETS = {
    textbook: {
      label: 'Textbook (AIMA Fig. 5.2/5.5)',
      blurb: 'The classic two-ply example from AIMA, the same tree as the figure above.',
      tree: [[3, 12, 8], [2, 4, 6], [14, 5, 2]]
    },
    best: {
      label: 'Best-case ordering',
      blurb: 'Every node tries its best move first, so the bounds are tight immediately. Knuth and Moore\'s minimum is 3² + 3¹ − 1 = 11 leaves.',
      tree: [
        [[5, 3, 1], [7, 2, 6], [8, 4, 0]],
        [[4, 2, 1], [9, 3, 6], [8, 7, 2]],
        [[3, 2, 1], [6, 5, 1], [9, 4, 3]]
      ]
    },
    worst: {
      label: 'Worst-case ordering',
      blurb: 'Every node tries its worst move first, so each new child looks better than the last and nothing can ever be cut.',
      tree: [
        [[5, 6, 7], [3, 4, 5], [1, 2, 3]],
        [[8, 9, 10], [6, 7, 8], [4, 5, 6]],
        [[11, 12, 13], [9, 10, 11], [7, 8, 9]]
      ]
    }
  };

  /* Random depth-3 tree, branching 2–3 at every node, leaf values 0–20. */
  function randomSpec(rng) {
    rng = rng || Math.random;
    function grow(depth) {
      if (depth === 3) return Math.floor(rng() * 21);
      var k = 2 + Math.floor(rng() * 2), out = [];
      for (var i = 0; i < k; i++) out.push(grow(depth + 1));
      return out;
    }
    return grow(0);
  }

  /* Turn a nested-array spec into a flat node list with ids, kinds, labels. */
  function buildTree(spec) {
    var nodes = [];
    function make(s, depth, parent) {
      var n = { id: nodes.length, depth: depth, parent: parent, children: [] };
      nodes.push(n);
      if (typeof s === 'number') {
        n.kind = 'leaf'; n.value = s; n.leaves = 1;
      } else {
        n.kind = depth % 2 === 0 ? 'max' : 'min';
        n.leaves = 0;
        s.forEach(function (c) {
          var child = make(c, depth + 1, n.id);
          n.children.push(child.id);
          n.leaves += child.leaves;
        });
      }
      return n;
    }
    make(spec, 0, -1);
    /* Letter the internal nodes in breadth-first order (A = root, B, C, D, ...)
       and number the leaves left to right for the layout. */
    var queue = [0], letter = 0, leafIndex = 0, maxDepth = 0;
    while (queue.length) {
      var n = nodes[queue.shift()];
      if (n.kind !== 'leaf') { n.label = LETTERS[letter++] || ('N' + letter); }
      queue = queue.concat(n.children);
    }
    (function order(id) {
      var n = nodes[id];
      maxDepth = Math.max(maxDepth, n.depth);
      if (n.kind === 'leaf') { n.leafIndex = leafIndex++; return; }
      n.children.forEach(order);
    })(0);
    return { nodes: nodes, leafCount: leafIndex, depth: maxDepth };
  }

  /* Run the search and return its event trace.
     useAB = false: plain minimax (no window, no cut-offs).
     useAB = true:  fail-soft alpha-beta: alpha and beta are passed down, MAX
                    raises alpha, MIN lowers beta, the loop breaks when alpha >= beta.
     Besides the fail-soft value v, every node also gets a sound interval
     [lo, hi] that is guaranteed to contain its true minimax value. This is what
     the algorithm has actually proven from the leaves it looked at, and is what
     we display ("≤ 2", "≥ 7") for nodes whose search was cut short. */
  function search(tree, useAB) {
    var nodes = tree.nodes, events = [], result = {}, best = {};
    var evaluated = 0, pruned = 0;

    function rec(id, alpha, beta, aSrc, bSrc) {
      var n = nodes[id];
      if (n.kind === 'leaf') {
        evaluated++;
        events.push({ t: 'leaf', n: id, alpha: alpha, beta: beta });
        result[id] = { v: n.value, lo: n.value, hi: n.value };
        return result[id];
      }
      var isMax = n.kind === 'max';
      var value = isMax ? -INF : INF;
      var lo = isMax ? -INF : INF, hi = isMax ? -INF : INF;
      var a = alpha, b = beta, cut = false;
      best[id] = -1;
      events.push({ t: 'enter', n: id, alpha: a, beta: b, aSrc: aSrc, bSrc: bSrc });

      for (var i = 0; i < n.children.length; i++) {
        var cid = n.children[i];
        var r = rec(cid, a, b, aSrc, bSrc);
        var e = { t: 'update', n: id, c: cid, cv: r.v, clo: r.lo, chi: r.hi,
                  oldV: value, oldA: a, oldB: b, improved: false,
                  last: i === n.children.length - 1 };
        if (isMax ? r.v > value : r.v < value) { value = r.v; best[id] = i; e.improved = true; }
        if (isMax) { lo = Math.max(lo, r.lo); hi = Math.max(hi, r.hi); }
        else { lo = Math.min(lo, r.lo); hi = Math.min(hi, r.hi); }
        if (useAB) {
          /* MAX raises alpha, MIN lowers beta; remember who set the bound so the
             prune caption can say which ancestor makes this node irrelevant. */
          if (isMax && value > a) { a = value; aSrc = { n: id, via: cid, v: value }; }
          if (!isMax && value < b) { b = value; bSrc = { n: id, via: cid, v: value }; }
        }
        e.v = value; e.a = a; e.b = b;
        e.cutNoop = useAB && a >= b && e.last;
        events.push(e);

        if (useAB && a >= b) {
          var skipped = n.children.slice(i + 1);
          if (skipped.length) {
            var leaves = 0;
            skipped.forEach(function (s) { leaves += nodes[s].leaves; });
            pruned += leaves;
            cut = true;
            events.push({ t: 'prune', n: id, skipped: skipped, leaves: leaves, a: a, b: b,
                          src: isMax ? bSrc : aSrc });
          }
          break;
        }
      }
      /* Unexplored children make one side of the interval unknown. */
      if (cut) { if (isMax) hi = INF; else lo = -INF; }
      /* Fail-soft window theorem: v <= alpha0 means true <= v, v >= beta0 means
         true >= v, otherwise v is exact. Intersect with the interval (both sound). */
      if (value <= alpha) { hi = Math.min(hi, value); }
      else if (value >= beta) { lo = Math.max(lo, value); }
      else { lo = Math.max(lo, value); hi = Math.min(hi, value); }
      result[id] = { v: value, lo: lo, hi: hi };
      return result[id];
    }

    var rootRes = rec(0, -INF, INF, null, null);

    /* Principal variation: follow the first child that achieved each value. */
    var pv = [0], cur = 0;
    while (nodes[cur].kind !== 'leaf' && best[cur] >= 0) {
      cur = nodes[cur].children[best[cur]];
      pv.push(cur);
    }
    events.push({ t: 'done', n: 0, v: rootRes.v, pv: pv });
    return { events: events, value: rootRes.v, result: result, pv: pv,
             evaluated: evaluated, pruned: pruned, total: tree.leafCount };
  }

  /* Reference minimax (no tracing), used for the self-check and the tests. */
  function minimaxValue(tree, id) {
    var n = tree.nodes[id || 0];
    if (n.kind === 'leaf') return n.value;
    var vals = n.children.map(function (c) { return minimaxValue(tree, c); });
    return n.kind === 'max' ? Math.max.apply(null, vals) : Math.min.apply(null, vals);
  }

  /* ------------------------------------------------------------------ */
  /* Captions                                                            */
  /* ------------------------------------------------------------------ */
  function fmt(v) {
    if (v === INF) return '+∞';
    if (v === -INF) return '−∞';
    return (v < 0 ? '−' : '') + Math.abs(v);
  }
  function fmtRange(lo, hi) {
    if (lo === hi) return fmt(lo);
    if (hi === INF) return '≥' + fmt(lo);
    if (lo === -INF) return '≤' + fmt(hi);
    return fmt(lo) + '…' + fmt(hi);
  }
  function win(a, b) { return '[' + fmt(a) + ', ' + fmt(b) + ']'; }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
  function leavesTxt(n) { return n + (n === 1 ? ' leaf' : ' leaves'); }
  function shortName(tree, id) { var x = tree.nodes[id]; return x.kind === 'leaf' ? 'leaf ' + fmt(x.value) : x.label; }

  function nodeName(tree, id) {
    var n = tree.nodes[id];
    if (n.kind === 'leaf') return 'leaf ' + fmt(n.value) + ' (under ' + tree.nodes[n.parent].label + ')';
    return (n.kind === 'max' ? 'MAX' : 'MIN') + ' node ' + n.label;
  }
  function b(s) { return '<strong>' + s + '</strong>'; }

  function caption(tree, e, useAB, stats) {
    var nodes = tree.nodes, n = nodes[e.n], s;
    var isMax = n.kind === 'max';
    switch (e.t) {
      case 'enter': {
        var who = isMax ? 'MAX wants the highest value, so value starts at −∞.'
                        : 'MIN wants the lowest value, so value starts at +∞.';
        if (e.n === 0) {
          s = 'Start at the ' + b('MAX root ' + n.label) + (useAB ? ' with window ' + b('[α, β] = ' + win(e.alpha, e.beta)) + ': nothing is known yet. ' : '. ') + who;
        } else {
          s = 'Enter ' + b(nodeName(tree, e.n)) + (useAB ? ', passing down the window ' + b(win(e.alpha, e.beta)) + '. ' : '. ') + who;
          if (useAB && e.alpha !== -INF && e.aSrc) s += ' α = ' + fmt(e.alpha) + ' because MAX at ' + nodes[e.aSrc.n].label + ' can already guarantee ' + fmt(e.alpha) + '.';
          if (useAB && e.beta !== INF && e.bSrc) s += ' β = ' + fmt(e.beta) + ' because MIN at ' + nodes[e.bSrc.n].label + ' can already hold MAX to ' + fmt(e.beta) + '.';
        }
        return s;
      }
      case 'leaf':
        return 'Evaluate a ' + b('leaf under ' + tree.nodes[n.parent].label) + ': leaves are scored directly, and this one is worth ' + b(fmt(n.value)) + '.';
      case 'update': {
        var c = nodes[e.c];
        var childTxt = c.kind === 'leaf' ? 'the leaf returned ' + fmt(e.cv)
                                         : 'child ' + c.label + ' returned ' + fmt(e.cv);
        if (e.clo !== e.chi) childTxt += ' (only a bound: true value ' + fmtRange(e.clo, e.chi).replace(/^([≤≥])/, '$1 ') + ', because part of ' + c.label + ' was pruned)';
        var op = isMax ? 'max' : 'min';
        s = b(nodeName(tree, e.n)) + ': ' + childTxt + ', so ';
        if (e.improved) s += 'value = ' + op + '(' + fmt(e.oldV) + ', ' + fmt(e.cv) + ') = ' + b(fmt(e.v));
        else s += 'value stays ' + b(fmt(e.v)) + ' (' + op + '(' + fmt(e.oldV) + ', ' + fmt(e.cv) + ') = ' + fmt(e.v) + ')';
        if (useAB) {
          if (isMax) {
            s += e.a !== e.oldA ? ' and α = max(' + fmt(e.oldA) + ', ' + fmt(e.v) + ') = ' + b(fmt(e.a)) + '.'
                                : '; α stays ' + fmt(e.a) + '.';
          } else {
            s += e.b !== e.oldB ? ' and β = min(' + fmt(e.oldB) + ', ' + fmt(e.v) + ') = ' + b(fmt(e.b)) + '.'
                                : '; β stays ' + fmt(e.b) + '.';
          }
          if (e.cutNoop) s += ' Now α ≥ β, but this was the last child, so there is nothing left to prune.';
          else if (e.a < e.b && !e.last) s += ' Still α < β, so the next child must be searched.';
        } else {
          s += '.';
        }
        if (e.last && !e.cutNoop) s += ' That was ' + n.label + '’s last child.';
        return s;
      }
      case 'prune': {
        var what = e.skipped.length === e.leaves ? leavesTxt(e.leaves)
                 : plural(e.skipped.length, 'subtree') + ' (' + leavesTxt(e.leaves) + ')';
        var src = e.src ? nodes[e.src.n] : null;
        if (isMax) {
          s = b('Prune!') + ' At MAX node ' + n.label + ', α = ' + fmt(e.a) + ' ≥ β = ' + fmt(e.b) + ': ';
          s += src ? 'MIN at ' + src.label + ' can already hold MAX to ' + fmt(e.b) + ' (via ' + shortName(tree, e.src.via) + ')'
                   : 'MIN higher up can already hold MAX to ' + fmt(e.b);
          s += ', so it will never let play reach here.';
        } else {
          s = b('Prune!') + ' At MIN node ' + n.label + ', β = ' + fmt(e.b) + ' ≤ α = ' + fmt(e.a) + ': ';
          s += src ? 'MAX at ' + src.label + ' already has a move worth ' + fmt(e.a) + ' (via ' + shortName(tree, e.src.via) + ')'
                   : 'MAX higher up already has a move worth ' + fmt(e.a);
          s += ', so it will never let play reach here.';
        }
        return s + ' Skipping ' + b(what) + '.';
      }
      case 'done': {
        var pv = e.pv.map(function (id) { var x = nodes[id]; return x.kind === 'leaf' ? fmt(x.value) : x.label; }).join(' → ');
        s = b('Search complete.') + ' Root ' + n.label + ' = ' + b(fmt(e.v)) + ', so MAX plays towards ' + shortName(tree, e.pv[1]) + '. Principal variation: ' + b(pv) + '. ';
        if (useAB) {
          if (stats.self.pruned === 0) {
            s += 'Alpha-beta evaluated all ' + stats.self.total + ' leaves: with this move ordering no branch could be skipped. It still got exactly the same root value as minimax.';
          } else {
            s += 'Alpha-beta evaluated ' + stats.self.evaluated + ' of ' + stats.self.total + ' leaves (' + stats.self.pruned + ' pruned) and got exactly the same root value as minimax, which needs all ' + stats.self.total + '.';
          }
        } else if (stats.other.evaluated >= stats.self.total) {
          s += 'Minimax evaluated all ' + stats.self.total + ' leaves, and with this move ordering alpha-beta prunes nothing: it also evaluates all ' + stats.self.total + '.';
        } else {
          s += 'Minimax evaluated all ' + stats.self.total + ' leaves. Alpha-beta finds the same value with only ' + stats.other.evaluated + '.';
        }
        return s;
      }
    }
    return '';
  }

  /* ------------------------------------------------------------------ */
  /* Snapshots: replay the trace into a list of full display states      */
  /* ------------------------------------------------------------------ */
  function descendants(tree, id, out) {
    out.push(id);
    tree.nodes[id].children.forEach(function (c) { descendants(tree, c, out); });
    return out;
  }

  function snapshots(tree, run, useAB, other) {
    var nodes = tree.nodes;
    var st = {
      nodes: nodes.map(function () { return { s: 'idle', v: null, a: null, b: null, lo: null, hi: null }; }),
      edges: nodes.map(function () { return 'idle'; }),  /* edge into node i from its parent */
      cur: -1, stack: [], evaluated: 0, pruned: 0, pv: [], done: false,
      caption: 'Press ' + b('Step') + ' (or →) to start the search at the root. ' +
               (useAB ? 'Alpha-beta will skip leaves that cannot change the answer.' : 'Plain minimax will look at every leaf.')
    };
    var out = [JSON.parse(JSON.stringify(st))];
    var stats = { self: run, other: other };

    run.events.forEach(function (e) {
      var ns = st.nodes[e.n];
      switch (e.t) {
        case 'enter':
          ns.s = 'open'; ns.v = nodes[e.n].kind === 'max' ? -INF : INF; ns.a = e.alpha; ns.b = e.beta;
          st.edges[e.n] = 'walk';
          st.stack.push(e.n);
          break;
        case 'leaf':
          ns.s = 'done'; ns.v = nodes[e.n].value; ns.lo = ns.hi = ns.v;
          st.edges[e.n] = 'walk';
          st.evaluated++;
          break;
        case 'update':
          var cs = st.nodes[e.c], r = run.result[e.c];
          cs.s = 'done'; cs.lo = r.lo; cs.hi = r.hi; cs.v = r.v;
          ns.v = e.v; ns.a = e.a; ns.b = e.b;
          if (st.stack[st.stack.length - 1] === e.c) st.stack.pop();
          break;
        case 'prune':
          e.skipped.forEach(function (sid) {
            descendants(tree, sid, []).forEach(function (d) { st.nodes[d].s = 'pruned'; st.edges[d] = 'pruned'; });
            st.edges[sid] = 'cut';
          });
          st.pruned += e.leaves;
          break;
        case 'done':
          var rr = run.result[0];
          ns.s = 'done'; ns.v = rr.v; ns.lo = rr.lo; ns.hi = rr.hi;
          st.stack = []; st.pv = e.pv; st.done = true;
          break;
      }
      st.cur = e.n;
      st.caption = caption(tree, e, useAB, stats);
      /* Infinity does not survive JSON, so copy by hand. */
      out.push({
        nodes: st.nodes.map(function (x) { return { s: x.s, v: x.v, a: x.a, b: x.b, lo: x.lo, hi: x.hi }; }),
        edges: st.edges.slice(), cur: st.cur, stack: st.stack.slice(), evaluated: st.evaluated,
        pruned: st.pruned, pv: st.pv.slice(), done: st.done, caption: st.caption
      });
    });
    return out;
  }

  var Core = { PRESETS: PRESETS, randomSpec: randomSpec, buildTree: buildTree, search: search,
               minimaxValue: minimaxValue, snapshots: snapshots, fmt: fmt, fmtRange: fmtRange };

  /* Node (tests) gets the core only. */
  if (typeof document === 'undefined') {
    if (typeof module === 'object' && module.exports) module.exports = Core;
    return;
  }

  /* ================================================================== */
  /* UI                                                                  */
  /* ================================================================== */
  var rootEl = document.getElementById('ab-stepper');
  if (!rootEl) return;

  var SVGNS = 'http://www.w3.org/2000/svg';
  var SPEEDS = [1600, 1100, 750, 450, 240];          /* ms per step, slider 1..5 */
  var SPEED_LABELS = ['Slow', 'Relaxed', 'Normal', 'Fast', 'Very fast'];
  var SCISSORS = '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>';

  function q(sel) { return rootEl.querySelector(sel); }
  var els = {
    preset: q('[data-abs-preset]'), random: q('[data-abs-random]'), blurb: q('[data-abs-blurb]'),
    modes: Array.prototype.slice.call(rootEl.querySelectorAll('input[name="abs-mode"]')),
    scroll: q('[data-abs-scroll]'), svg: q('[data-abs-svg]'), caption: q('[data-abs-caption]'),
    reset: q('[data-abs-reset]'), back: q('[data-abs-back]'), play: q('[data-abs-play]'), step: q('[data-abs-step]'),
    speed: q('[data-abs-speed]'), speedVal: q('[data-abs-speed-val]'),
    stepNo: q('[data-abs-stepno]'), leaves: q('[data-abs-leaves]'), compare: q('[data-abs-compare]')
  };

  var reducedQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  function reduced() { return !!(reducedQuery && reducedQuery.matches); }

  var state = { spec: null, tree: null, useAB: true, runs: null, snaps: [], i: 0, timer: null, playing: false, view: null };

  /* ------------------------------------------------------------------ */
  /* SVG construction (once per tree); steps only toggle classes / text   */
  /* ------------------------------------------------------------------ */
  function el(name, attrs, parent) {
    var x = document.createElementNS(SVGNS, name);
    for (var k in attrs) { if (Object.prototype.hasOwnProperty.call(attrs, k)) x.setAttribute(k, attrs[k]); }
    if (parent) parent.appendChild(x);
    return x;
  }

  function layout(tree) {
    var leafGap = Math.max(36, Math.min(72, 640 / tree.leafCount));
    var left = 64, right = 28, top = 58, levelGap = tree.depth >= 3 ? 96 : 112;
    var width = Math.round(left + tree.leafCount * leafGap + right);
    var pos = [];
    (function place(id) {
      var n = tree.nodes[id];
      if (n.kind === 'leaf') {
        pos[id] = { x: left + (n.leafIndex + 0.5) * leafGap, y: top + n.depth * levelGap };
      } else {
        n.children.forEach(place);
        var first = pos[n.children[0]], last = pos[n.children[n.children.length - 1]];
        pos[id] = { x: (first.x + last.x) / 2, y: top + n.depth * levelGap };
      }
    })(0);
    return { pos: pos, width: width, height: top + tree.depth * levelGap + 34, top: top, levelGap: levelGap, left: left };
  }

  function buildSvg() {
    var tree = state.tree, L = layout(tree), svg = els.svg;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute('viewBox', '0 0 ' + L.width + ' ' + L.height);
    svg.style.setProperty('--abs-w', L.width + 'px');
    svg.setAttribute('aria-label', 'Game tree with ' + tree.leafCount + ' leaves. Root ' + tree.nodes[0].label + ' is MAX; layers alternate MAX and MIN.');

    /* Layer labels down the left edge. */
    var gLayers = el('g', { 'class': 'abs-layers' }, svg);
    for (var d = 0; d <= tree.depth; d++) {
      var y = L.top + d * L.levelGap;
      el('line', { x1: 8, x2: L.width - 8, y1: y, y2: y, 'class': 'abs-layer-rule' }, gLayers);
      var t = el('text', { x: 10, y: y - 6, 'class': 'abs-layer-label' }, gLayers);
      t.textContent = d === tree.depth ? 'LEAF' : (d % 2 === 0 ? 'MAX' : 'MIN');
    }

    var gEdges = el('g', { 'class': 'abs-edges' }, svg);
    var gCuts = el('g', { 'class': 'abs-cuts' }, svg);
    var gNodes = el('g', { 'class': 'abs-nodes' }, svg);
    var view = { edges: [], cuts: [], nodes: [], values: [], windows: [], L: L };

    tree.nodes.forEach(function (n) {
      var p = L.pos[n.id];
      if (n.parent >= 0) {
        var pp = L.pos[n.parent];
        var y1 = pp.y + 18, y2 = n.kind === 'leaf' ? p.y - 12 : p.y - 26;
        view.edges[n.id] = el('line', { x1: pp.x, y1: y1, x2: p.x, y2: y2, 'class': 'abs-edge' }, gEdges);
        /* Scissors marker, shown on the edge into a pruned child. */
        var mx = pp.x + (p.x - pp.x) * 0.5, my = y1 + (y2 - y1) * 0.5;
        var cut = el('g', { 'class': 'abs-cut', transform: 'translate(' + (mx - 11) + ' ' + (my - 11) + ')' }, gCuts);
        el('circle', { cx: 11, cy: 11, r: 11, 'class': 'abs-cut-bg' }, cut);
        var sc = el('g', { transform: 'translate(3 3) scale(.6667)', 'class': 'abs-cut-icon' }, cut);
        sc.innerHTML = SCISSORS;
        view.cuts[n.id] = cut;
      }
      var g = el('g', { 'class': 'abs-node is-' + n.kind, transform: 'translate(' + p.x + ' ' + p.y + ')' }, gNodes);
      var label;
      if (n.kind === 'leaf') {
        el('rect', { x: -15, y: -12, width: 30, height: 24, rx: 6, 'class': 'abs-halo-rect' }, g);
        el('rect', { x: -15, y: -12, width: 30, height: 24, rx: 6, 'class': 'abs-shape' }, g);
        label = el('text', { x: 0, y: 4.5, 'class': 'abs-val', 'text-anchor': 'middle' }, g);
        label.textContent = fmt(n.value);
        el('line', { x1: -11, x2: 11, y1: 0, y2: 0, 'class': 'abs-strike' }, g);
      } else {
        el('circle', { cx: 0, cy: 0, r: 30, 'class': 'abs-halo' }, g);
        var pts = n.kind === 'max' ? '0,-25 -25,18 25,18' : '-25,-18 25,-18 0,25';
        el('polygon', { points: pts, 'class': 'abs-shape' }, g);
        label = el('text', { x: 0, y: n.kind === 'max' ? 10 : 2, 'class': 'abs-val', 'text-anchor': 'middle' }, g);
        var name = el('text', { x: -29, y: n.kind === 'max' ? 6 : -3, 'class': 'abs-name', 'text-anchor': 'end' }, g);
        name.textContent = n.label;
        /* [alpha, beta] pill above the node: the node's current window. It starts
           as the window passed down from the parent and is updated as children
           return (MAX raises alpha, MIN lowers beta), so it is always the window
           the next child receives. */
        var w = el('g', { 'class': 'abs-win', transform: 'translate(0 ' + (n.kind === 'max' ? -40 : -44) + ')' }, g);
        el('rect', { x: -33, y: -10, width: 66, height: 18, rx: 9, 'class': 'abs-win-bg' }, w);
        var wt = el('text', { x: 0, y: 3.5, 'text-anchor': 'middle', 'class': 'abs-win-text' }, w);
        view.windows[n.id] = { g: w, t: wt };
      }
      var title = el('title', {}, g);
      title.textContent = n.kind === 'leaf' ? 'Leaf, value ' + fmt(n.value) : (n.kind.toUpperCase() + ' node ' + n.label);
      view.nodes[n.id] = g;
      view.values[n.id] = label;
    });
    state.view = view;
  }

  /* ------------------------------------------------------------------ */
  /* Render one snapshot                                                 */
  /* ------------------------------------------------------------------ */
  function render() {
    var snap = state.snaps[state.i], tree = state.tree, view = state.view;
    var onStack = {}, onPv = {};
    snap.stack.forEach(function (id) { onStack[id] = true; });
    snap.pv.forEach(function (id) { onPv[id] = true; });

    tree.nodes.forEach(function (n) {
      var s = snap.nodes[n.id], g = view.nodes[n.id];
      g.setAttribute('class', 'abs-node is-' + n.kind + ' st-' + s.s +
        (onStack[n.id] ? ' is-open' : '') + (snap.cur === n.id ? ' is-current' : '') + (onPv[n.id] ? ' is-pv' : ''));
      if (n.kind !== 'leaf') {
        var txt = '';
        if (s.s === 'open') txt = fmt(s.v);
        else if (s.s === 'done') txt = fmtRange(s.lo, s.hi);
        view.values[n.id].textContent = txt;
        var w = view.windows[n.id];
        var showWin = state.useAB && (s.s === 'open' || s.s === 'done') && s.a !== null;
        w.g.setAttribute('class', 'abs-win' + (showWin ? ' is-on' : ''));
        w.t.textContent = showWin ? win(s.a, s.b) : '';
      }
      if (n.parent >= 0) {
        var e = snap.edges[n.id];
        view.edges[n.id].setAttribute('class', 'abs-edge ed-' + e +
          (onStack[n.id] || (snap.cur === n.id && !snap.done) ? ' is-path' : '') + (onPv[n.id] && onPv[n.parent] ? ' is-pv' : ''));
        view.cuts[n.id].setAttribute('class', 'abs-cut' + (e === 'cut' ? ' is-on' : ''));
      }
    });

    els.caption.innerHTML = snap.caption;
    var last = state.snaps.length - 1;
    els.stepNo.textContent = 'Step ' + state.i + ' / ' + last;
    els.leaves.innerHTML = 'Leaves evaluated: <strong>' + snap.evaluated + ' / ' + tree.leafCount + '</strong>' +
      (state.useAB ? ', pruned: <strong>' + snap.pruned + '</strong>' : '');
    els.back.disabled = state.i === 0;
    els.step.disabled = state.i === last;
    rootEl.classList.toggle('is-finished', snap.done);
    keepInView(snap.cur);
  }

  /* On narrow screens the tree scrolls sideways: keep the current node visible. */
  function keepInView(id) {
    var sc = els.scroll;
    if (id < 0 || sc.scrollWidth <= sc.clientWidth + 2) return;
    var L = state.view.L, scale = els.svg.getBoundingClientRect().width / L.width;
    var x = L.pos[id].x * scale, pad = 60;
    if (x < sc.scrollLeft + pad || x > sc.scrollLeft + sc.clientWidth - pad) {
      var to = Math.max(0, x - sc.clientWidth / 2);
      if (sc.scrollTo) sc.scrollTo({ left: to, behavior: reduced() ? 'auto' : 'smooth' });
      else sc.scrollLeft = to;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Model changes                                                       */
  /* ------------------------------------------------------------------ */
  function compute() {
    var mm = search(state.tree, false), ab = search(state.tree, true);
    /* Self-check: alpha-beta must agree with minimax at the root. */
    if (ab.value !== mm.value || ab.value !== minimaxValue(state.tree)) {
      if (window.console) console.error('[stepper] alpha-beta and minimax disagree', ab.value, mm.value);
    }
    state.runs = { mm: mm, ab: ab };
    els.compare.innerHTML = 'This tree: minimax evaluates <strong>' + mm.evaluated + '</strong> leaves, alpha-beta <strong>' +
      ab.evaluated + '</strong> (' + ab.pruned + ' pruned). Both return <strong>' + fmt(ab.value) + '</strong>.';
  }

  function rebuildSnaps() {
    var r = state.runs, self = state.useAB ? r.ab : r.mm, other = state.useAB ? r.mm : r.ab;
    state.snaps = snapshots(state.tree, self, state.useAB, other);
    state.i = 0;
  }

  function loadSpec(spec) {
    pause();
    state.spec = spec;
    state.tree = buildTree(spec);
    compute();
    buildSvg();
    rebuildSnaps();
    els.scroll.scrollLeft = 0;
    render();
  }

  function selectPreset(key) {
    if (key === 'random') {
      els.blurb.textContent = 'A fresh random tree: depth 3, two or three moves per node, leaf values 0–20.';
      loadSpec(randomSpec());
    } else {
      els.blurb.textContent = PRESETS[key].blurb;
      loadSpec(PRESETS[key].tree);
    }
  }

  function setMode(useAB) {
    pause();
    state.useAB = useAB;
    rootEl.classList.toggle('is-minimax', !useAB);
    rebuildSnaps();
    render();
  }

  /* ------------------------------------------------------------------ */
  /* Playback                                                            */
  /* ------------------------------------------------------------------ */
  function go(i) {
    state.i = Math.max(0, Math.min(state.snaps.length - 1, i));
    render();
  }
  function stepFwd() { if (state.i < state.snaps.length - 1) go(state.i + 1); else pause(); }
  function stepBack() { pause(); go(state.i - 1); }
  function delay() { return SPEEDS[(parseInt(els.speed.value, 10) || 3) - 1]; }

  function tick() {
    state.timer = null;
    if (!state.playing) return;
    stepFwd();
    if (state.i >= state.snaps.length - 1) { pause(); return; }
    state.timer = setTimeout(tick, delay());
  }
  function play() {
    if (state.playing) return;
    if (state.i >= state.snaps.length - 1) go(0);
    state.playing = true;
    /* Avoid flooding screen readers while autoplaying; captions are announced again on pause. */
    els.caption.setAttribute('aria-live', 'off');
    updatePlayBtn();
    stepFwd();
    state.timer = setTimeout(tick, delay());
  }
  function pause() {
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    if (!state.playing) return;
    state.playing = false;
    els.caption.setAttribute('aria-live', 'polite');
    updatePlayBtn();
  }
  function togglePlay() { if (state.playing) pause(); else play(); }
  function updatePlayBtn() {
    els.play.setAttribute('aria-pressed', state.playing ? 'true' : 'false');
    els.play.querySelector('[data-when="play"]').hidden = state.playing;
    els.play.querySelector('[data-when="pause"]').hidden = !state.playing;
    els.play.querySelector('[data-abs-play-label]').textContent = state.playing ? 'Pause' : 'Play';
  }
  function updateSpeedLabel() { els.speedVal.textContent = SPEED_LABELS[(parseInt(els.speed.value, 10) || 3) - 1]; }

  /* ------------------------------------------------------------------ */
  /* Wiring                                                              */
  /* ------------------------------------------------------------------ */
  els.preset.addEventListener('change', function () { selectPreset(els.preset.value); });
  els.random.addEventListener('click', function () { els.preset.value = 'random'; selectPreset('random'); });
  els.modes.forEach(function (r) {
    r.addEventListener('change', function () { if (r.checked) setMode(r.value === 'ab'); });
  });
  els.step.addEventListener('click', function () { pause(); stepFwd(); });
  els.back.addEventListener('click', stepBack);
  els.play.addEventListener('click', togglePlay);
  els.reset.addEventListener('click', function () { pause(); go(0); });
  els.speed.addEventListener('input', updateSpeedLabel);

  /* Keyboard: only while focus is inside the widget, and never steal keys from
     its own controls (Space on a button clicks it, arrows move sliders/radios). */
  rootEl.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var tag = (e.target.tagName || '').toLowerCase();
    /* On one of the stepper's own buttons, ←/→/Home/End still step (a button has
       no use for them); Space and Enter keep pressing the button. */
    var navKey = e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === 'Home' || e.key === 'End';
    if (tag === 'button' && !(navKey && rootEl.contains(e.target))) return;
    if (tag === 'input' || tag === 'select' || tag === 'textarea' || tag === 'a') return;
    if (e.key === 'ArrowRight') { e.preventDefault(); pause(); stepFwd(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); stepBack(); }
    else if (e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'Home') { e.preventDefault(); pause(); go(0); }
    else if (e.key === 'End') { e.preventDefault(); pause(); go(state.snaps.length - 1); }
  });
  /* Clicking the tree or caption focuses the widget so the keys work straight away. */
  els.scroll.addEventListener('mousedown', function () { rootEl.focus({ preventScroll: true }); });

  updateSpeedLabel();
  selectPreset(els.preset.value || 'textbook');
})();
