/* AI Arena: Play page (human vs AI). */
(function () {
  'use strict';
  var A = window.Arena;
  var $ = A.$;

  var view = new BoardView($('#board'), { interactive: true, onColumn: humanMove });
  var mind = new MindPanel($('#mind'), {
    bars: $('#col-bars'),
    placeholder: 'Make a move and the AI will explain its reply here.'
  });
  var picker = new A.AgentPicker($('#agent-picker'), {
    type: 'alphabeta', storeKey: 'play-agent', label: 'Opponent',
    onChange: function () { updateNames(); }
  });

  var statusEl = $('#status');
  var historyEl = $('#history');
  var historyEmpty = $('#history-empty');
  var banner = $('#result-banner');
  var btnNew = $('#btn-new'), btnUndo = $('#btn-undo'), btnHint = $('#btn-hint');

  var S = {
    board: A.emptyBoard(),
    moves: [],          // [{col, row, player, by: 'human'|'ai'}]
    human: 1,
    over: false,
    busy: false,        // waiting for the AI or the server
    token: 0,           // invalidates stale AI responses
    controller: null,
    hinting: false
  };

  function aiPlayer() { return 3 - S.human; }
  function toMove() { return S.moves.length % 2 === 0 ? 1 : 2; }
  function colourName(p) { return p === 1 ? 'Red' : 'Yellow'; }

  function setStatus(kind, text) {
    var cls = { think: 'is-think', red: 'is-red', yellow: 'is-yellow', good: 'is-good', bad: 'is-bad' }[kind] || '';
    statusEl.className = 'pill ' + cls;
    statusEl.innerHTML = (kind === 'think' ? '<span class="spinner"></span>' : '<span class="dot"></span>') + A.escapeHtml(text);
  }

  function updateNames() {
    $('#ai-name').textContent = picker.label();
    $('#human-disc').className = 'mini-disc p' + S.human;
    $('#ai-disc').className = 'mini-disc p' + aiPlayer();
  }

  function updateTurnUI() {
    var turn = toMove();
    $('#tag-human').classList.toggle('is-turn', !S.over && turn === S.human);
    $('#tag-ai').classList.toggle('is-turn', !S.over && turn === aiPlayer());
    view.setTurn(S.human);
    view.setLocked(S.over || S.busy || turn !== S.human);
    btnUndo.disabled = !S.moves.some(function (m) { return m.by === 'human'; });
    btnHint.disabled = S.over || S.busy || turn !== S.human;
    if (S.over) return;
    if (S.busy && turn === aiPlayer()) setStatus('think', 'AI is thinking');
    else if (turn === S.human) setStatus(S.human === 1 ? 'red' : 'yellow', 'Your move');
    else setStatus('think', 'AI to move');
  }

  function renderHistory() {
    historyEl.innerHTML = S.moves.map(function (m, i) {
      return '<li><span class="h-num">' + (i + 1) + '.</span><span class="mini-disc p' + m.player + '"></span>' +
        '<span class="h-who">' + (m.by === 'human' ? 'You' : A.escapeHtml(m.label || 'AI')) + '</span>' +
        '<span class="h-col">col ' + (m.col + 1) + '</span></li>';
    }).join('');
    historyEmpty.hidden = S.moves.length > 0;
    $('#move-count').textContent = S.moves.length + (S.moves.length === 1 ? ' move' : ' moves');
    historyEl.scrollTop = historyEl.scrollHeight;
  }

  function rebuildBoard() {
    var b = A.emptyBoard();
    S.moves.forEach(function (m) { b[m.row][m.col] = m.player; });
    return b;
  }

  function cancelPending() {
    S.token++;
    if (S.controller) { try { S.controller.abort(); } catch (e) { /* ignore */ } }
    S.controller = null;
    S.busy = false;
  }

  function showResult(state) {
    S.over = true;
    var text, kind;
    if (state.winner === S.human) { text = 'You win! Four in a row.'; kind = 'good'; }
    else if (state.winner) { text = 'The AI wins this one.'; kind = 'bad'; }
    else { text = "It's a draw: the board is full."; kind = ''; }
    setStatus(kind, state.winner === S.human ? 'You win' : state.winner ? 'AI wins' : 'Draw');
    $('#result-text').innerHTML = A.icon(state.winner === S.human ? 'trophy' : state.winner ? 'cpu' : 'info', 18) + A.escapeHtml(text);
    banner.classList.add('is-visible');
    view.setWinning(state.winning_cells || []);
    if (state.winner === S.human) {
      A.confetti();
      A.toast('Nicely played: you beat ' + picker.label() + '.', { type: 'success', title: 'Victory', icon: 'trophy' });
    }
    updateTurnUI();
  }

  function newGame(silent) {
    cancelPending();
    view.clearHint();
    S.board = A.emptyBoard();
    S.moves = [];
    S.over = false;
    S.human = document.querySelector('input[name="first"]:checked').value === 'ai' ? 2 : 1;
    banner.classList.remove('is-visible');
    view.render(S.board);
    mind.reset(S.human === 1 ? 'You play Red and move first. Make a move and the AI will explain its reply here.'
      : 'The AI plays Red and moves first. Watch its reasoning appear here.');
    updateNames();
    renderHistory();
    updateTurnUI();
    if (!silent) A.toast('New game against ' + picker.label() + '.', { timeout: 2200 });
    if (toMove() === aiPlayer()) aiMove();
  }

  function humanMove(col) {
    if (S.over) { view.shake(); A.toast('The game is over. Press N for a new game.', { timeout: 2500 }); return; }
    if (S.busy || toMove() !== S.human) { view.shake(); return; }
    var row = A.dropRow(S.board, col);
    if (row === -1) { view.shake(); A.toast('Column ' + (col + 1) + ' is full.', { type: 'error', title: 'Illegal move', timeout: 2500 }); return; }
    view.clearHint();
    var token = ++S.token;
    S.busy = true;
    updateTurnUI();
    var before = A.cloneBoard(S.board);
    A.api('/api/apply', { board: before, column: col }, { errorTitle: 'Move rejected' }).then(function (res) {
      if (token !== S.token) return;
      S.board = res.board;
      S.moves.push({ col: col, row: row, player: S.human, by: 'human' });
      renderHistory();
      return view.render(S.board, { animate: [row, col] }).then(function () {
        if (token !== S.token) return;
        S.busy = false;
        var st = res.state;
        if (st.winner || st.draw) { showResult(st); return; }
        aiMove();
      });
    }).catch(function () {
      if (token !== S.token) return;
      S.busy = false;
      view.shake();
      updateTurnUI();
    });
  }

  function aiMove() {
    if (S.over) return;
    var token = ++S.token;
    var cfg = picker.getConfig();
    var label = picker.label();
    S.busy = true;
    updateTurnUI();
    mind.thinking(label);
    S.controller = window.AbortController ? new AbortController() : null;
    var started = performance.now();
    var player = aiPlayer();
    var body = { board: A.cloneBoard(S.board), player: player, agent: Object.assign({ trace: true }, cfg) };
    A.api('/api/move', body, { signal: S.controller && S.controller.signal, errorTitle: 'The AI could not move' })
      .then(function (res) {
        // keep the spinner visible briefly so fast agents still feel deliberate
        var wait = Math.max(0, 380 - (performance.now() - started));
        return A.sleep(A.reducedMotion() ? 0 : wait).then(function () { return res; });
      })
      .then(function (res) {
        if (token !== S.token) return;
        var col = res.column;
        var row = A.dropRow(S.board, col);
        S.board = res.board_after;
        S.moves.push({ col: col, row: row, player: player, by: 'ai', label: label });
        mind.show(res, { type: cfg.type, player: player, iterations: cfg.iterations });
        renderHistory();
        return view.render(S.board, { animate: [row, col] }).then(function () {
          if (token !== S.token) return;
          S.busy = false;
          S.controller = null;
          var st = res.state_after;
          if (st.winner || st.draw) showResult(st);
          else updateTurnUI();
        });
      })
      .catch(function (err) {
        if (token !== S.token || (err && err.name === 'AbortError')) return;
        S.busy = false;
        S.controller = null;
        mind.error(err && err.message);
        setStatus('bad', 'AI error');
        view.setLocked(true);
        A.toast('Press N to restart, or U to undo your last move.', { title: 'Game paused', timeout: 5000 });
      });
  }

  function undo() {
    var lastHuman = -1;
    for (var i = S.moves.length - 1; i >= 0; i--) { if (S.moves[i].by === 'human') { lastHuman = i; break; } }
    if (lastHuman === -1) { A.toast('Nothing to undo yet.', { timeout: 2000 }); return; }
    cancelPending();
    view.clearHint();
    var removed = S.moves.length - lastHuman;
    S.moves = S.moves.slice(0, lastHuman);
    S.board = rebuildBoard();
    S.over = false;
    banner.classList.remove('is-visible');
    view.render(S.board, { last: S.moves.length ? [S.moves[S.moves.length - 1].row, S.moves[S.moves.length - 1].col] : null });
    mind.reset('Took back ' + (removed > 1 ? 'your move and the AI\'s reply' : 'your move') + '. Your turn again.');
    renderHistory();
    updateTurnUI();
    if (toMove() === aiPlayer()) aiMove();
  }

  function hint() {
    if (S.over || S.busy || toMove() !== S.human || S.hinting) {
      if (!S.hinting) A.toast(S.over ? 'The game is over.' : 'Wait for your turn to ask for a hint.', { timeout: 2200 });
      return;
    }
    S.hinting = true;
    A.setLoading(btnHint, true);
    var token = S.token;
    A.api('/api/move', { board: A.cloneBoard(S.board), player: S.human, agent: { type: 'alphabeta', depth: 7, trace: false } }, { errorTitle: 'Hint unavailable' })
      .then(function (res) {
        if (token !== S.token) return;
        view.hint(res.column, 4000);
        view.focusColumn(res.column);
        A.toast(res.explanation || ('Alpha-beta suggests column ' + (res.column + 1) + '.'), { title: 'Hint: column ' + (res.column + 1), icon: 'bulb', timeout: 6000 });
      })
      .catch(function () { /* toast already shown */ })
      .then(function () {
        S.hinting = false;
        A.setLoading(btnHint, false);
        updateTurnUI();
      });
  }

  btnNew.addEventListener('click', function () { newGame(); });
  $('#btn-again').addEventListener('click', function () { newGame(); });
  btnUndo.addEventListener('click', undo);
  btnHint.addEventListener('click', hint);
  document.querySelectorAll('input[name="first"]').forEach(function (r) {
    r.addEventListener('change', function () {
      A.store.set('play-first', r.value);
      newGame(true);
      A.toast(r.value === 'ai' ? 'New game: the AI moves first as Red.' : 'New game: you move first as Red.', { timeout: 2500 });
    });
  });

  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || A.isTypingTarget(e.target)) return;
    var k = e.key;
    if (k >= '1' && k <= '7') { e.preventDefault(); humanMove(Number(k) - 1); }
    else if (k === 'u' || k === 'U') { e.preventDefault(); undo(); }
    else if (k === 'n' || k === 'N') { e.preventDefault(); newGame(); }
    else if (k === 'h' || k === 'H') { e.preventDefault(); hint(); }
  });

  // restore "who moves first"
  var savedFirst = A.store.get('play-first', 'human');
  var radio = document.querySelector('input[name="first"][value="' + (savedFirst === 'ai' ? 'ai' : 'human') + '"]');
  if (radio) radio.checked = true;
  A.initRanges(document);
  newGame(true);
})();
