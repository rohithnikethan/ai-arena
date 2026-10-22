/* AI Arena: Arena page (AI vs AI, step-through, best-of-N series). */
(function () {
  'use strict';
  var A = window.Arena;
  var $ = A.$;

  var view = new BoardView($('#board'), { interactive: false });
  var minds = {
    a: new MindPanel($('#mind-a'), { title: 'Agent A', subtitle: 'Mind of agent A', compact: true, owner: '<span class="mini-disc p1" data-owner-disc></span>', placeholder: 'Agent A\'s reasoning appears here when it moves.' }),
    b: new MindPanel($('#mind-b'), { title: 'Agent B', subtitle: 'Mind of agent B', compact: true, owner: '<span class="mini-disc p2" data-owner-disc></span>', placeholder: 'Agent B\'s reasoning appears here when it moves.' })
  };
  var pickers = {
    a: new A.AgentPicker($('#picker-a'), { type: 'alphabeta', storeKey: 'arena-a', label: 'Agent', onChange: onAgentChange }),
    b: new A.AgentPicker($('#picker-b'), { type: 'mcts', storeKey: 'arena-b', label: 'Agent', onChange: onAgentChange })
  };

  var btnPlay = $('#btn-play'), btnStep = $('#btn-step'), btnReset = $('#btn-reset');
  var speed = $('#speed'), bestOf = $('#best-of');
  var statusEl = $('#status');

  var S = {
    board: A.emptyBoard(),
    moves: 0,
    game: 0,           // index of current game in series
    over: false,
    playing: false,
    busy: false,
    token: 0,
    loopId: 0,
    score: { a: 0, b: 0, d: 0 },
    seriesDone: false,
    autoPlayed: false  // has Play been pressed in this series? (Resume vs Continue)
  };

  function colourOf(side) {
    // A is Red (moves first) in even-numbered games; colours swap every game
    var aRed = S.game % 2 === 0;
    return side === 'a' ? (aRed ? 1 : 2) : (aRed ? 2 : 1);
  }
  function sideOf(player) { return colourOf('a') === player ? 'a' : 'b'; }
  function toMove() { return S.moves % 2 === 0 ? 1 : 2; }
  function seriesLength() { return Number(bestOf.value) || 1; }
  function delay() { return Number(speed.value) || 0; }

  function setStatus(kind, text) {
    var cls = { think: 'is-think', red: 'is-red', yellow: 'is-yellow', good: 'is-good', bad: 'is-bad' }[kind] || '';
    statusEl.className = 'pill ' + cls;
    statusEl.innerHTML = (kind === 'think' ? '<span class="spinner"></span>' : '<span class="dot"></span>') + A.escapeHtml(text);
  }

  function updateLabels() {
    ['a', 'b'].forEach(function (side) {
      var p = colourOf(side);
      var label = pickers[side].label();
      $('#' + side + '-disc').className = 'mini-disc p' + p;
      $('#' + side + '-colour').textContent = (p === 1 ? 'Red · first' : 'Yellow');
      $('#score-' + side + '-name').textContent = (side === 'a' ? 'A · ' : 'B · ') + label;
      minds[side].setTitle((side === 'a' ? 'A · ' : 'B · ') + label, p === 1 ? 'Plays Red this game' : 'Plays Yellow this game');
      var od = minds[side].root.querySelector('[data-owner-disc]');
      if (od) od.className = 'mini-disc p' + p;
    });
  }

  function updateScore(bumpKey) {
    $('#score-a').textContent = S.score.a;
    $('#score-b').textContent = S.score.b;
    $('#score-d').textContent = S.score.d;
    if (bumpKey) {
      var el = $('#score-' + bumpKey);
      el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump');
    }
    var n = seriesLength();
    var played = S.score.a + S.score.b + S.score.d;
    $('#series-label').textContent = n === 1 ? 'Single game' : (S.seriesDone ? 'Series over · ' + played + ' played' : 'Game ' + Math.min(S.game + 1, n) + ' of ' + n);
    $('#series-bar').style.width = (Math.min(1, played / n) * 100) + '%';
  }

  /* "Resume" only after a real pause; a series advanced with Step alone says
     "Continue"; a fresh board says "Play". */
  function playLabel() {
    if (S.seriesDone) return 'Play again';
    if (!S.moves && !S.game) return 'Play';
    return S.autoPlayed ? 'Resume' : 'Continue';
  }

  function updateControls() {
    btnPlay.innerHTML = S.playing
      ? '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="6" y="4.5" width="4" height="15" rx="1"/><rect x="14" y="4.5" width="4" height="15" rx="1"/></svg><span>Pause</span>'
      : '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M7 4.5v15l12-7.5z"/></svg><span>' + playLabel() + '</span>';
    btnPlay.setAttribute('aria-pressed', S.playing ? 'true' : 'false');
    btnStep.disabled = S.playing || S.busy;
    pickers.a.setDisabled(S.playing);
    pickers.b.setDisabled(S.playing);
    bestOf.disabled = S.playing;
    $('#move-count').textContent = 'Move ' + S.moves;
  }

  function startGame() {
    S.board = A.emptyBoard();
    S.moves = 0;
    S.over = false;
    view.render(S.board);
    minds.a.reset('Agent A\'s reasoning appears here when it moves.');
    minds.b.reset('Agent B\'s reasoning appears here when it moves.');
    updateLabels();
    updateScore();
    updateControls();
    setStatus('', 'Game ' + (S.game + 1) + ' ready');
  }

  function resetSeries(silent) {
    S.token++;
    S.playing = false;
    S.busy = false;
    S.game = 0;
    S.score = { a: 0, b: 0, d: 0 };
    S.seriesDone = false;
    S.autoPlayed = false;
    startGame();
    setStatus('', 'Press Play to start');
    if (!silent) A.toast('Scoreboard cleared. Press Play to begin.', { timeout: 2200 });
  }

  function onAgentChange() {
    updateLabels();
    if (S.moves > 0 || S.game > 0 || S.score.a + S.score.b + S.score.d > 0) {
      resetSeries(true);
      A.toast('Agents changed, so the series restarted.', { timeout: 2600 });
    }
  }

  function clinched() {
    var n = seriesLength(), need = Math.floor(n / 2) + 1;
    var played = S.score.a + S.score.b + S.score.d;
    return S.score.a >= need || S.score.b >= need || played >= n;
  }

  function finishGame(state) {
    S.over = true;
    view.setWinning(state.winning_cells || []);
    var winnerSide = state.winner ? sideOf(state.winner) : null;
    if (winnerSide) S.score[winnerSide]++; else S.score.d++;
    var label = winnerSide ? (winnerSide.toUpperCase() + ' · ' + pickers[winnerSide].label()) : null;
    setStatus(winnerSide ? (state.winner === 1 ? 'red' : 'yellow') : '', winnerSide ? label + ' wins' : 'Draw');
    if (clinched()) {
      S.seriesDone = true;
      S.playing = false;
      var msg;
      if (S.score.a === S.score.b) msg = 'Series tied ' + S.score.a + '–' + S.score.b + (S.score.d ? ' with ' + S.score.d + ' draw' + (S.score.d > 1 ? 's' : '') : '') + '.';
      else {
        var w = S.score.a > S.score.b ? 'a' : 'b';
        msg = (w === 'a' ? 'Agent A' : 'Agent B') + ' (' + pickers[w].label() + ') takes the series ' + Math.max(S.score.a, S.score.b) + '–' + Math.min(S.score.a, S.score.b) + '.';
      }
      if (seriesLength() > 1) A.toast(msg, { type: 'success', title: 'Series complete', icon: 'trophy', timeout: 6000 });
    }
    updateScore(winnerSide || 'd');
    updateControls();
  }

  /* Play one move. Resolves true if a move was played. */
  function stepMove() {
    if (S.over || S.busy) return Promise.resolve(false);
    var token = S.token;
    var player = toMove();
    var side = sideOf(player);
    var cfg = pickers[side].getConfig();
    S.busy = true;
    updateControls();
    setStatus('think', (side === 'a' ? 'A' : 'B') + ' · ' + pickers[side].label() + ' is thinking');
    minds[side].thinking(pickers[side].label());
    return A.api('/api/move', { board: A.cloneBoard(S.board), player: player, agent: Object.assign({ trace: true }, cfg) }, { errorTitle: 'Agent ' + side.toUpperCase() + ' could not move' })
      .then(function (res) {
        if (token !== S.token) return false;
        var row = A.dropRow(S.board, res.column);
        S.board = res.board_after;
        S.moves++;
        minds[side].show(res, { type: cfg.type, player: player, iterations: cfg.iterations });
        return view.render(S.board, { animate: [row, res.column] }).then(function () {
          if (token !== S.token) return false;
          S.busy = false;
          var st = res.state_after;
          if (st.winner || st.draw) finishGame(st);
          else setStatus(toMove() === 1 ? 'red' : 'yellow', (sideOf(toMove()) === 'a' ? 'A' : 'B') + ' to move');
          updateControls();
          return true;
        });
      })
      .catch(function (err) {
        if (token !== S.token) return false;
        S.busy = false;
        S.playing = false;
        minds[side].error(err && err.message);
        setStatus('bad', 'Stopped after an error');
        updateControls();
        return false;
      });
  }

  function nextGameIfNeeded() {
    if (!S.over) return false;
    if (S.seriesDone) { resetSeries(true); return true; }
    S.game++;
    startGame();
    return true;
  }

  // Each Play press starts a new loop id; older loops exit, so Pause/Play
  // spam can never leave two loops racing (which spun forever on S.busy).
  function loop(id) {
    var token = S.token;
    if (!S.playing || token !== S.token || id !== S.loopId) return;
    var p;
    if (S.over) {
      p = A.sleep(Math.max(1200, delay() * 2)).then(function () {
        if (!S.playing || token !== S.token || id !== S.loopId) return;
        nextGameIfNeeded();
      });
    } else {
      p = stepMove().then(function (moved) {
        if (!moved) return;
        return A.sleep(S.over ? 0 : delay());
      });
    }
    p.then(function () {
      if (id !== S.loopId) return;
      if (S.playing && token === S.token && !(S.over && S.seriesDone)) loop(id);
      else updateControls();
    });
  }

  btnPlay.addEventListener('click', function () {
    if (S.playing) {
      S.playing = false;
      updateControls();
      setStatus('', 'Paused');
      return;
    }
    if (S.seriesDone) resetSeries(true);
    else if (S.over) { S.game++; startGame(); }
    S.playing = true;
    S.autoPlayed = true;
    updateControls();
    var id = ++S.loopId;
    if (!S.busy) loop(id);
    else {
      // a step is in flight: resume the loop once it lands
      var wait = setInterval(function () { if (!S.busy) { clearInterval(wait); if (S.playing) loop(id); } }, 80);
    }
  });

  btnStep.addEventListener('click', function () {
    if (S.playing || S.busy) return;
    if (S.over) { nextGameIfNeeded(); return; }
    stepMove();
  });

  btnReset.addEventListener('click', function () { resetSeries(false); });

  speed.addEventListener('input', function () {
    $('#speed-value').textContent = (delay() / 1000).toFixed(1) + ' s';
    A.store.set('arena-speed', delay());
  });
  bestOf.addEventListener('change', function () {
    A.store.set('arena-bestof', bestOf.value);
    if (S.seriesDone || S.score.a + S.score.b + S.score.d > 0) resetSeries(true);
    updateScore();
  });

  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || A.isTypingTarget(e.target, { allowSelect: e.key !== ' ' })) return;
    if (e.key === ' ' && e.target === document.body) { e.preventDefault(); btnPlay.click(); }
    else if (e.key === 's' || e.key === 'S') { btnStep.click(); }
    else if (e.key === 'n' || e.key === 'N') { resetSeries(false); }
  });

  // restore preferences
  var savedSpeed = A.store.get('arena-speed', null);
  if (savedSpeed != null) speed.value = savedSpeed;
  $('#speed-value').textContent = (delay() / 1000).toFixed(1) + ' s';
  var savedBest = A.store.get('arena-bestof', null);
  if (savedBest && bestOf.querySelector('option[value="' + savedBest + '"]')) bestOf.value = savedBest;
  A.initRanges(document);
  resetSeries(true);
})();
