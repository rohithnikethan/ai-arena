/* AI Arena: Lab page (tournaments + pruning experiment, Chart.js). */
(function () {
  'use strict';
  var A = window.Arena;
  var $ = A.$;
  var hasChart = typeof window.Chart !== 'undefined';
  var C = { a: '#9d41d2', b: '#0d9488', draw: '#878c91', minimax: '#0d9488' };
  /* Pruning chart series. Minimax = teal solid, alpha-beta = light purple dashed,
     alpha-beta + ordering = brand purple, thick and solid. The purples are picked
     per theme so both keep >= 3:1 against the page and stay far apart in lightness.
     The note under the chart in lab.html describes exactly these styles. */
  function pruneColors() {
    var light = A.theme() === 'light';
    return { ab: light ? '#b756f2' : '#e9d5ff', abo: light ? '#6a1b9a' : '#b756f2' };
  }
  var charts = {};

  var pickA = new A.AgentPicker($('#lab-a'), { type: 'alphabeta', storeKey: 'lab-a', label: 'Agent A' });
  var pickB = new A.AgentPicker($('#lab-b'), { type: 'greedy', storeKey: 'lab-b', label: 'Agent B' });

  /* ---------------- theming ---------------- */
  function theme() {
    return {
      text: A.cssVar('--text-2') || '#c3b5d3',
      faint: A.cssVar('--text-3') || '#9a8aab',
      grid: A.cssVar('--border') || 'rgba(217,204,255,.09)',
      tipBg: A.cssVar('--tooltip-bg') || '#1a0f25',
      tipText: A.cssVar('--text') || '#f6f0fc',
      bg: A.cssVar('--bg') || '#0e0714'
    };
  }
  function applyDefaults() {
    if (!hasChart) return;
    var t = theme();
    Chart.defaults.font.family = 'Montserrat, system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = t.text;
    Chart.defaults.borderColor = t.grid;
    Chart.defaults.animation.duration = A.reducedMotion() ? 0 : 700;
    var tip = Chart.defaults.plugins.tooltip;
    tip.backgroundColor = t.tipBg;
    tip.titleColor = t.tipText;
    tip.bodyColor = t.text;
    tip.borderColor = t.grid;
    tip.borderWidth = 1;
    tip.padding = 10;
    tip.cornerRadius = 10;
    tip.titleFont = { weight: '600' };
    tip.bodyFont = { family: 'JetBrains Mono, monospace', size: 11.5 };
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxHeight = 8;
  }
  function rethemeChart(ch) {
    var t = theme();
    Object.keys(ch.options.scales || {}).forEach(function (k) {
      var s = ch.options.scales[k];
      if (s.ticks) s.ticks.color = t.text;
      if (s.grid) s.grid.color = t.grid;
      if (s.title) s.title.color = t.faint;
      if (s.border) s.border.color = t.grid;
    });
    var tip = ch.options.plugins && ch.options.plugins.tooltip;
    if (tip) { tip.backgroundColor = t.tipBg; tip.titleColor = t.tipText; tip.bodyColor = t.text; tip.borderColor = t.grid; }
    var leg = ch.options.plugins && ch.options.plugins.legend;
    if (leg && leg.labels) leg.labels.color = t.text;
    var pc = pruneColors();
    ch.data.datasets.forEach(function (d) {
      if (d._themeBorder) d.borderColor = t.bg;
      if (d._pruneKey === 'alphabeta_nodes') d.borderColor = d.backgroundColor = pc.ab;
      if (d._pruneKey === 'alphabeta_ordered_nodes') d.borderColor = d.backgroundColor = pc.abo;
    });
    ch.update('none');
  }
  document.addEventListener('themechange', function () {
    applyDefaults();
    Object.keys(charts).forEach(function (k) { if (charts[k]) rethemeChart(charts[k]); });
  });
  applyDefaults();

  function setChart(key, canvasId, config) {
    if (!hasChart) return null;
    if (charts[key]) charts[key].destroy();
    var canvas = document.getElementById(canvasId);
    var empty = canvas.parentNode.querySelector('[data-empty]');
    if (empty) empty.hidden = true;
    charts[key] = new Chart(canvas, config);
    rethemeChart(charts[key]);
    return charts[key];
  }
  function loading(cardIds, on) {
    cardIds.forEach(function (id) { document.getElementById(id).classList.toggle('is-loading', on); });
  }
  function scaleOpts(extra) {
    var t = theme();
    return Object.assign({ grid: { color: t.grid }, border: { color: t.grid }, ticks: { color: t.text } }, extra || {});
  }

  if (!hasChart) {
    A.toast('Chart.js could not be loaded (offline?). Tables will still show the numbers.', { type: 'error', title: 'Charts unavailable', timeout: 8000 });
  }

  /* ---------------- cancellable requests ---------------- */
  /* One AbortController per running job. Cancelling (or leaving the page) aborts
     the fetch so the UI resets at once; the Flask request itself is synchronous
     and finishes its search on the server, but its answer is simply discarded. */
  var jobs = {};
  function startJob(key, cancelBtn, runBtn) {
    var ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    jobs[key] = ctl || true;
    if (ctl && cancelBtn) {
      cancelBtn.hidden = false;
      if (runBtn) runBtn.hidden = true;
      cancelBtn.focus();
    }
    return jobs[key];
  }
  function endJob(key, ctl, cancelBtn, runBtn) {
    if (jobs[key] !== ctl) return false; /* a newer job owns the UI */
    jobs[key] = null;
    if (cancelBtn) {
      var hadFocus = document.activeElement === cancelBtn;
      cancelBtn.hidden = true;
      if (runBtn) { runBtn.hidden = false; if (hadFocus) runBtn.focus(); }
    }
    return true;
  }
  function cancelJob(key) { if (jobs[key] && jobs[key].abort) jobs[key].abort(); }
  function signalOf(ctl) { return ctl && ctl.signal ? ctl.signal : undefined; }
  function isAbort(err) { return !!(err && err.name === 'AbortError'); }
  window.addEventListener('pagehide', function () { Object.keys(jobs).forEach(cancelJob); });

  /* ---------------- tournament ---------------- */
  var gamesInput = $('#games');
  var openingInput = $('#opening-plies');
  /* Range inputs remembered across reloads (A.store guards localStorage). */
  function bindRange(input, outId, storeKey, fmt) {
    if (!input) return;
    var saved = A.store.get(storeKey, null);
    if (saved != null && !isNaN(saved)) {
      var min = Number(input.min) || 0, max = Number(input.max), step = Number(input.step) || 1;
      var v = Math.max(min, Math.min(max, Number(saved)));
      input.value = String(min + Math.round((v - min) / step) * step);
    }
    var out = $(outId);
    var sync = function () { if (out) out.textContent = fmt ? fmt(Number(input.value)) : input.value; };
    input.addEventListener('input', sync);
    input.addEventListener('change', function () { A.store.set(storeKey, Number(input.value)); });
    sync();
  }
  bindRange(gamesInput, '#games-value', 'lab-games');
  bindRange(openingInput, '#opening-plies-value', 'lab-opening-plies', function (n) { return n ? n + ' ply' : 'off'; });

  var matchBtn = $('#btn-match'), matchCancel = $('#btn-match-cancel');
  var MATCH_CARDS = ['card-doughnut', 'card-time', 'card-nodes'];
  if (matchCancel) matchCancel.addEventListener('click', function () { cancelJob('match'); });

  $('#match-form').addEventListener('submit', function (e) {
    e.preventDefault();
    if (jobs.match) return;
    var cfgA = pickA.getConfig(), cfgB = pickB.getConfig();
    var labelA = 'A · ' + pickA.label(), labelB = 'B · ' + pickB.label();
    var games = Number(gamesInput.value);
    var body = { agent_a: cfgA, agent_b: cfgB, games: games };
    if (openingInput) body.opening_plies = Number(openingInput.value);
    A.setLoading(matchBtn, true);
    pickA.setDisabled(true); pickB.setDisabled(true); gamesInput.disabled = true;
    if (openingInput) openingInput.disabled = true;
    loading(MATCH_CARDS, true);
    var ctl = startJob('match', matchCancel, matchBtn);
    var t0 = performance.now();
    A.api('/api/match', body, { errorTitle: 'Tournament failed', signal: signalOf(ctl) })
      .then(function (res) {
        if (jobs.match !== ctl) return;
        var wall = performance.now() - t0;
        renderMatch(res, labelA, labelB, wall);
        A.toast(res.games + ' games played in ' + A.fmtMs(wall) + '.', { type: 'success', title: 'Tournament complete' });
      })
      .catch(function (err) {
        if (isAbort(err) && jobs.match === ctl) A.toast('Tournament cancelled. The previous results are unchanged.', { type: 'info', title: 'Cancelled' });
        /* other errors: A.api already showed a toast */
      })
      .then(function () {
        if (!endJob('match', ctl, matchCancel, matchBtn)) return;
        A.setLoading(matchBtn, false);
        pickA.setDisabled(false); pickB.setDisabled(false); gamesInput.disabled = false;
        if (openingInput) openingInput.disabled = false;
        A.initRanges(document);
        loading(MATCH_CARDS, false);
      });
  });

  function pct(n, d) { return d ? Math.round(n / d * 100) + '%' : '0%'; }

  function renderMatch(res, labelA, labelB, wall) {
    var g = res.games || 0;
    $('#sum-a').textContent = res.a_wins + ' · ' + pct(res.a_wins, g);
    $('#sum-b').textContent = res.b_wins + ' · ' + pct(res.b_wins, g);
    $('#sum-d').textContent = res.draws + ' · ' + pct(res.draws, g);
    $('#sum-t').textContent = A.fmtMs(wall);
    var nameA = (res.a && res.a.label) ? 'A · ' + res.a.label : labelA;
    var nameB = (res.b && res.b.label) ? 'B · ' + res.b.label : labelB;

    setChart('doughnut', 'chart-doughnut', {
      type: 'doughnut',
      data: {
        labels: [nameA + ' wins', nameB + ' wins', 'Draws'],
        datasets: [{ data: [res.a_wins, res.b_wins, res.draws], backgroundColor: [C.a, C.b, C.draw], borderColor: theme().bg, _themeBorder: true, borderWidth: 3, hoverOffset: 8 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '64%',
        plugins: {
          legend: { position: 'bottom', labels: { padding: 14, font: { size: 11 } } },
          tooltip: {
            /* A zero-width arc can still be hit at a segment boundary: never show "0 games". */
            filter: function (item) { return Number(item.raw) > 0; },
            callbacks: { label: function (c) { return ' ' + c.raw + ' game' + (c.raw === 1 ? '' : 's') + ' (' + pct(c.raw, g) + ')'; } }
          }
        }
      }
    });

    var barOpts = function (fmt, title, tickFmt) {
      return {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) { return ' ' + fmt(c.raw); } } } },
        scales: {
          x: scaleOpts({ grid: { display: false } }),
          y: scaleOpts({ beginAtZero: true, title: { display: true, text: title },
            ticks: { maxTicksLimit: 6, callback: tickFmt ? function (v, i, ticks) { return tickFmt(v, ticks); } : function (v) { return fmt(v); } } })
        }
      };
    };
    var names = [shorten(nameA), shorten(nameB)];
    setChart('time', 'chart-time', {
      type: 'bar',
      data: { labels: names, datasets: [{ data: [res.a.avg_time_ms, res.b.avg_time_ms], backgroundColor: [C.a, C.b], borderRadius: 8, maxBarThickness: 64 }] },
      options: barOpts(fmtMsPrecise, 'time per move', msTick)
    });
    setChart('nodes', 'chart-nodes', {
      type: 'bar',
      data: { labels: names, datasets: [{ data: [res.a.avg_nodes, res.b.avg_nodes], backgroundColor: [C.a, C.b], borderRadius: 8, maxBarThickness: 64 }] },
      options: barOpts(A.fmtCompact, 'nodes per move')
    });

    var rows = (res.results || []).map(function (r, i) {
      var firstName = r.first === 'a' ? 'Agent A' : 'Agent B';
      var winner = r.winner === 'draw' ? '<span class="result-chip faint">Draw</span>'
        : '<span class="result-chip"><span class="mini-disc" style="background:' + (r.winner === 'a' ? C.a : C.b) + '"></span>' + (r.winner === 'a' ? 'Agent A' : 'Agent B') + '</span>';
      var moves = (r.moves || []).map(function (c) { return c + 1; }).join(' ');
      var op = (r.opening || []).map(function (c) { return c + 1; }).join(' ');
      var opCell = op ? '<td class="mono" title="Random opening (columns 1 to 7); these moves also start the Moves list">' + A.escapeHtml(op) + '</td>' : '<td class="faint">none</td>';
      return '<tr><td>#' + (i + 1) + '</td><td>' + firstName + '</td>' + opCell + '<td>' + winner + '</td><td class="num">' + (r.length != null ? r.length : (r.moves || []).length) + '</td><td class="moves" title="' + A.escapeHtml(moves) + '">' + A.escapeHtml(moves) + '</td></tr>';
    });
    $('#match-table').innerHTML = rows.join('');
    $('#match-table-wrap').hidden = rows.length === 0;
  }
  /* Milliseconds with enough precision for tiny values (fast agents average a few
     microseconds per move): below 0.1 ms switch to µs, otherwise 3 significant digits. */
  function fmtMsPrecise(ms) {
    if (ms == null || isNaN(ms)) return '—';
    var a = Math.abs(ms);
    if (a === 0) return '0 ms';
    if (a < 0.1) return Number((ms * 1000).toPrecision(3)) + ' µs';
    if (a >= 100) return A.fmtMs(ms);
    return Number(ms.toPrecision(3)) + ' ms';
  }
  /* Axis ticks: one unit for the whole axis and just enough decimals to tell
     neighbouring ticks apart, so labels never repeat. */
  function msTick(v, ticks) {
    var vals = (ticks || []).map(function (t) { return t.value; });
    var maxV = Math.max.apply(null, vals.map(Math.abs).concat([Math.abs(v)]));
    var scale = 1, unit = ' ms';
    if (maxV < 0.1) { scale = 1000; unit = ' µs'; } else if (maxV >= 10000) { scale = 0.001; unit = ' s'; }
    var stepV = vals.length > 1 ? Math.abs(vals[1] - vals[0]) * scale : 1;
    var dec = 0;
    while (dec < 6 && stepV > 0 && Math.abs(Math.round(stepV * Math.pow(10, dec)) - stepV * Math.pow(10, dec)) > 1e-6 * Math.pow(10, dec)) dec++;
    var x = v * scale;
    return (x === 0 ? '0' : x.toFixed(dec)) + unit;
  }
  function shorten(s) { return s.length > 26 ? s.slice(0, 25) + '…' : s; }

  /* ---------------- pruning experiment ---------------- */
  var maxDepth = $('#max-depth');
  maxDepth.addEventListener('input', function () { $('#max-depth-value').textContent = maxDepth.value; });
  $('#max-depth-value').textContent = maxDepth.value;

  function midgameBoard() {
    var b = A.emptyBoard();
    [3, 3, 2, 4, 4, 2, 5, 3].forEach(function (c, i) { b[A.dropRow(b, c)][c] = i % 2 === 0 ? 1 : 2; });
    return b;
  }

  var pruneBtn = $('#btn-prune'), pruneCancel = $('#btn-prune-cancel');
  if (pruneCancel) pruneCancel.addEventListener('click', function () { cancelJob('prune'); });
  function positionRadios() { return Array.prototype.slice.call(document.querySelectorAll('input[name="position"]')); }

  $('#prune-form').addEventListener('submit', function (e) {
    e.preventDefault();
    if (jobs.prune) return;
    var btn = pruneBtn;
    var n = Number(maxDepth.value);
    var depths = [];
    for (var d = 1; d <= n; d++) depths.push(d);
    var body = { depths: depths };
    if (document.querySelector('input[name="position"]:checked').value === 'mid') body.board = midgameBoard();
    A.setLoading(btn, true);
    maxDepth.disabled = true;
    positionRadios().forEach(function (r) { r.disabled = true; });
    loading(['card-prune'], true);
    var ctl = startJob('prune', pruneCancel, btn);
    A.api('/api/compare-depth', body, { errorTitle: 'Experiment failed', signal: signalOf(ctl) })
      .then(function (rows) { if (jobs.prune === ctl) renderPrune(rows); })
      .catch(function (err) {
        if (isAbort(err) && jobs.prune === ctl) A.toast('Experiment cancelled. The previous results are unchanged.', { type: 'info', title: 'Cancelled' });
      })
      .then(function () {
        if (!endJob('prune', ctl, pruneCancel, btn)) return;
        A.setLoading(btn, false);
        maxDepth.disabled = false;
        positionRadios().forEach(function (r) { r.disabled = false; });
        A.initRanges(document);
        loading(['card-prune'], false);
      });
  });

  function num(v) { return v == null || isNaN(v) ? null : Number(v); }

  function renderPrune(rows) {
    if (!Array.isArray(rows) || !rows.length) {
      A.toast('The experiment returned no data.', { type: 'error' });
      return;
    }
    var labels = rows.map(function (r) { return 'd' + r.depth; });
    var ds = function (label, key, color, dash, width, point) {
      return {
        label: label, data: rows.map(function (r) { return num(r[key]); }),
        borderColor: color, backgroundColor: color, borderWidth: width || 2.5, tension: .3,
        pointRadius: 4, pointHoverRadius: 6, pointStyle: point || 'circle', borderDash: dash || [], spanGaps: false,
        _pruneKey: key
      };
    };
    var pc = pruneColors();
    setChart('prune', 'chart-prune', {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          ds('Minimax', 'minimax_nodes', C.minimax, null, 2.5, 'circle'),
          ds('Alpha-beta', 'alphabeta_nodes', pc.ab, [7, 5], 2.5, 'rectRot'),
          ds('Alpha-beta + ordering', 'alphabeta_ordered_nodes', pc.abo, null, 4, 'rect')
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          /* Each legend key is a short stroke (pointStyle 'line') drawn with the
             dataset's own colour, width and dash, so dashed vs solid shows in the
             legend too. Chart.js takes point styles (no dash) for legend items when
             usePointStyle is on, so copy the line styles over by hand. */
          legend: { position: 'bottom', labels: {
            padding: 16, usePointStyle: true, pointStyle: 'line', pointStyleWidth: 36, boxHeight: 10,
            generateLabels: function (chart) {
              return Chart.defaults.plugins.legend.labels.generateLabels(chart).map(function (item) {
                var d = chart.data.datasets[item.datasetIndex] || {};
                item.lineDash = d.borderDash || [];
                item.lineWidth = d.borderWidth;
                item.strokeStyle = d.borderColor;
                item.fillStyle = d.borderColor;
                return item;
              });
            }
          } },
          tooltip: { callbacks: { label: function (c) { return ' ' + c.dataset.label + ': ' + (c.raw == null ? 'not run' : A.fmtInt(c.raw) + ' nodes'); } } }
        },
        scales: {
          x: scaleOpts({ title: { display: true, text: 'search depth (plies)' }, grid: { display: false } }),
          y: scaleOpts({
            type: 'logarithmic', title: { display: true, text: 'nodes searched (log scale)' },
            ticks: { callback: function (v) { var l = Math.log10(v); return Math.abs(l - Math.round(l)) < 1e-9 ? A.fmtCompact(v) : ''; } }
          })
        }
      }
    });

    // table + callout
    var best = null;
    $('#prune-table').innerHTML = rows.map(function (r) {
      var mm = num(r.minimax_nodes), abo = num(r.alphabeta_ordered_nodes);
      var pruned = mm && abo != null ? (1 - abo / mm) : null;
      if (pruned != null) best = { depth: r.depth, pct: pruned, mm: mm, abo: abo, ab: num(r.alphabeta_nodes) };
      var cell = function (v, f) { return '<td class="num">' + (v == null ? '<span class="faint">—</span>' : f(v)) + '</td>'; };
      return '<tr><td>' + r.depth + '</td>' + cell(mm, A.fmtInt) + cell(num(r.alphabeta_nodes), A.fmtInt) + cell(abo, A.fmtInt) +
        cell(num(r.minimax_ms), A.fmtMs) + cell(num(r.alphabeta_ms), A.fmtMs) + cell(num(r.alphabeta_ordered_ms), A.fmtMs) +
        cell(pruned, function (p) { return (p * 100).toFixed(1) + '%'; }) + '</tr>';
    }).join('');
    $('#prune-table-wrap').hidden = false;

    if (best) {
      $('#prune-pct').textContent = (best.pct * 100).toFixed(best.pct > 0.99 ? 2 : 1) + '%';
      var speed = best.abo ? Math.round(best.mm / best.abo) : null;
      $('#prune-text').innerHTML = 'of the minimax tree is <strong>pruned</strong> at depth ' + best.depth +
        ': alpha-beta with ordering visits <strong>' + A.fmtInt(best.abo) + '</strong> nodes instead of <strong>' + A.fmtInt(best.mm) + '</strong>' +
        (speed ? ' (about <strong>' + speed.toLocaleString('en-US') + '×</strong> fewer)' : '') + '.' +
        (best.ab != null ? ' Without ordering it still needs ' + A.fmtInt(best.ab) + '.' : '');
    } else {
      $('#prune-pct').textContent = '—';
      $('#prune-text').textContent = 'Minimax data was not available for these depths.';
    }
  }

  A.initRanges(document);
})();
