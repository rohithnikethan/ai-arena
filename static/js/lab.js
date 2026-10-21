/* AI Arena: Lab page (tournaments + pruning experiment, Chart.js). */
(function () {
  'use strict';
  var A = window.Arena;
  var $ = A.$;
  var hasChart = typeof window.Chart !== 'undefined';
  var C = { a: '#8b5cf6', b: '#22d3ee', draw: '#6b7280', minimax: '#f43f5e', ab: '#a78bfa', abo: '#22d3ee' };
  var charts = {};

  var pickA = new A.AgentPicker($('#lab-a'), { type: 'alphabeta', storeKey: 'lab-a', label: 'Agent A' });
  var pickB = new A.AgentPicker($('#lab-b'), { type: 'greedy', storeKey: 'lab-b', label: 'Agent B' });

  /* ---------------- theming ---------------- */
  function theme() {
    return {
      text: A.cssVar('--text-2') || '#a5aac2',
      faint: A.cssVar('--text-3') || '#6d7290',
      grid: A.cssVar('--border') || 'rgba(255,255,255,.08)',
      tipBg: A.cssVar('--tooltip-bg') || '#10131f',
      tipText: A.cssVar('--text') || '#eceef7',
      bg: A.cssVar('--bg') || '#07080e'
    };
  }
  function applyDefaults() {
    if (!hasChart) return;
    var t = theme();
    Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
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
    ch.data.datasets.forEach(function (d) { if (d._themeBorder) d.borderColor = t.bg; });
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

  /* ---------------- tournament ---------------- */
  var gamesInput = $('#games');
  gamesInput.addEventListener('input', function () { $('#games-value').textContent = gamesInput.value; });
  $('#games-value').textContent = gamesInput.value;

  $('#match-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var btn = $('#btn-match');
    var cfgA = pickA.getConfig(), cfgB = pickB.getConfig();
    var labelA = 'A · ' + pickA.label(), labelB = 'B · ' + pickB.label();
    var games = Number(gamesInput.value);
    A.setLoading(btn, true);
    pickA.setDisabled(true); pickB.setDisabled(true); gamesInput.disabled = true;
    loading(['card-doughnut', 'card-time', 'card-nodes'], true);
    var t0 = performance.now();
    A.api('/api/match', { agent_a: cfgA, agent_b: cfgB, games: games }, { errorTitle: 'Tournament failed' })
      .then(function (res) {
        var wall = performance.now() - t0;
        renderMatch(res, labelA, labelB, wall);
        A.toast(res.games + ' games played in ' + A.fmtMs(wall) + '.', { type: 'success', title: 'Tournament complete' });
      })
      .catch(function () { /* toast already shown */ })
      .then(function () {
        A.setLoading(btn, false);
        pickA.setDisabled(false); pickB.setDisabled(false); gamesInput.disabled = false;
        loading(['card-doughnut', 'card-time', 'card-nodes'], false);
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
          tooltip: { callbacks: { label: function (c) { return ' ' + c.raw + ' game' + (c.raw === 1 ? '' : 's') + ' (' + pct(c.raw, g) + ')'; } } }
        }
      }
    });

    var barOpts = function (fmt, title) {
      return {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) { return ' ' + fmt(c.raw); } } } },
        scales: {
          x: scaleOpts({ grid: { display: false } }),
          y: scaleOpts({ beginAtZero: true, title: { display: true, text: title }, ticks: { callback: function (v) { return fmt(v); } } })
        }
      };
    };
    var names = [shorten(nameA), shorten(nameB)];
    setChart('time', 'chart-time', {
      type: 'bar',
      data: { labels: names, datasets: [{ data: [res.a.avg_time_ms, res.b.avg_time_ms], backgroundColor: [C.a, C.b], borderRadius: 8, maxBarThickness: 64 }] },
      options: barOpts(A.fmtMs, 'ms per move')
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
      return '<tr><td>#' + (i + 1) + '</td><td>' + firstName + '</td><td>' + winner + '</td><td class="num">' + (r.length != null ? r.length : (r.moves || []).length) + '</td><td class="moves" title="' + A.escapeHtml(moves) + '">' + A.escapeHtml(moves) + '</td></tr>';
    });
    $('#match-table').innerHTML = rows.join('');
    $('#match-table-wrap').hidden = rows.length === 0;
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

  $('#prune-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var btn = $('#btn-prune');
    var n = Number(maxDepth.value);
    var depths = [];
    for (var d = 1; d <= n; d++) depths.push(d);
    var body = { depths: depths };
    if (document.querySelector('input[name="position"]:checked').value === 'mid') body.board = midgameBoard();
    A.setLoading(btn, true);
    maxDepth.disabled = true;
    loading(['card-prune'], true);
    A.api('/api/compare-depth', body, { errorTitle: 'Experiment failed' })
      .then(function (rows) { renderPrune(rows); })
      .catch(function () { /* toast already shown */ })
      .then(function () {
        A.setLoading(btn, false);
        maxDepth.disabled = false;
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
    var ds = function (label, key, color, dash) {
      return {
        label: label, data: rows.map(function (r) { return num(r[key]); }),
        borderColor: color, backgroundColor: color, borderWidth: 2.5, tension: .3,
        pointRadius: 4, pointHoverRadius: 6, borderDash: dash || [], spanGaps: false
      };
    };
    setChart('prune', 'chart-prune', {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          ds('Minimax', 'minimax_nodes', C.minimax),
          ds('Alpha-beta', 'alphabeta_nodes', C.ab, [6, 4]),
          ds('Alpha-beta + ordering', 'alphabeta_ordered_nodes', C.abo)
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { padding: 16 } },
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
