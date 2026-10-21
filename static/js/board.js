/* AI Arena: Connect Four board view (rendering, drop animation, ghost preview). */
(function () {
  'use strict';
  var A = window.Arena;
  var ROWS = A.ROWS, COLS = A.COLS;

  /**
   * new BoardView(root, {interactive, onColumn, ghost, labels})
   * root: an element that becomes a .board-wrap.
   */
  function BoardView(root, opts) {
    opts = opts || {};
    this.root = root;
    this.interactive = !!opts.interactive;
    this.onColumn = opts.onColumn || function () {};
    this.ghostEnabled = opts.ghost !== false;
    this.turnPlayer = 1;
    this.locked = false;
    this.board = A.emptyBoard();
    this.hoverCol = null;
    this._hintTimer = null;
    this._build(opts.labels !== false);
  }

  BoardView.prototype._build = function (labels) {
    var self = this;
    this.root.classList.add('board-wrap');
    var html = '';
    html += '<div class="board-ghost" aria-hidden="true"' + (this.ghostEnabled ? '' : ' style="visibility:hidden"') + '>';
    for (var c = 0; c < COLS; c++) html += '<div class="ghost-slot"><div class="disc is-ghost p1"></div></div>';
    html += '</div>';
    html += '<div class="board' + (this.interactive ? ' is-interactive' : '') + '">';
    for (c = 0; c < COLS; c++) {
      var tag = this.interactive ? 'button type="button"' : 'div';
      html += '<' + tag + ' class="board-col" data-col="' + c + '"' + (this.interactive ? ' aria-label="Drop a disc in column ' + (c + 1) + '"' : '') + '>';
      for (var r = 0; r < ROWS; r++) html += '<div class="cell" data-r="' + r + '" data-c="' + c + '"></div>';
      html += this.interactive ? '</button>' : '</div>';
    }
    html += '</div>';
    if (labels) {
      html += '<div class="board-labels" aria-hidden="true">';
      for (c = 0; c < COLS; c++) html += '<span>' + (c + 1) + '</span>';
      html += '</div>';
    }
    this.root.innerHTML = html;
    this.boardEl = this.root.querySelector('.board');
    this.cols = Array.prototype.slice.call(this.root.querySelectorAll('.board-col'));
    this.ghosts = Array.prototype.slice.call(this.root.querySelectorAll('.disc.is-ghost'));
    this.slots = Array.prototype.slice.call(this.root.querySelectorAll('.ghost-slot'));
    this.cells = [];
    for (var rr = 0; rr < ROWS; rr++) {
      this.cells.push([]);
      for (var cc = 0; cc < COLS; cc++) this.cells[rr].push(this.cols[cc].children[rr]);
    }
    if (this.interactive) {
      this.cols.forEach(function (colEl, i) {
        colEl.addEventListener('mouseenter', function () { self._hover(i); });
        colEl.addEventListener('mouseleave', function () { self._hover(null); });
        colEl.addEventListener('focus', function () { self._hover(i); });
        colEl.addEventListener('blur', function () { self._hover(null); });
        colEl.addEventListener('click', function () { self.onColumn(i); });
        colEl.addEventListener('keydown', function (e) {
          if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault();
            var next = (i + (e.key === 'ArrowLeft' ? -1 : 1) + COLS) % COLS;
            self.cols[next].focus();
          }
        });
      });
    }
  };

  BoardView.prototype._hover = function (col) {
    this.hoverCol = col;
    var self = this;
    this.ghosts.forEach(function (g, i) {
      var show = self.ghostEnabled && !self.locked && i === col && A.dropRow(self.board, i) !== -1;
      g.classList.toggle('is-visible', show);
      g.classList.toggle('p1', self.turnPlayer === 1);
      g.classList.toggle('p2', self.turnPlayer === 2);
    });
  };

  BoardView.prototype.setTurn = function (player) {
    this.turnPlayer = player;
    this._hover(this.hoverCol);
  };

  BoardView.prototype.setLocked = function (locked) {
    this.locked = !!locked;
    this.root.classList.toggle('is-locked', this.locked);
    this._hover(this.hoverCol);
  };

  BoardView.prototype._discEl = function (r, c) {
    return this.cells[r][c].querySelector('.disc');
  };

  /**
   * Render a board. opts: {animate: [r, c], last: [r, c], winning: [[r,c],...]}
   * Returns a Promise resolved when the drop animation finishes.
   */
  BoardView.prototype.render = function (board, opts) {
    opts = opts || {};
    this.board = A.cloneBoard(board);
    var animate = opts.animate || null;
    var last = opts.last || animate;
    var duration = 0;
    for (var r = 0; r < ROWS; r++) {
      for (var c = 0; c < COLS; c++) {
        var v = board[r][c];
        var cell = this.cells[r][c];
        var disc = cell.querySelector('.disc');
        if (!v) {
          if (disc) cell.removeChild(disc);
          continue;
        }
        if (!disc) {
          disc = document.createElement('div');
          cell.appendChild(disc);
        }
        disc.className = 'disc p' + v;
        if (animate && animate[0] === r && animate[1] === c && !A.reducedMotion()) {
          duration = this._animateDrop(disc, r, c);
        }
        if (last && last[0] === r && last[1] === c) disc.classList.add('is-last');
      }
    }
    this.setWinning(opts.winning || []);
    this._hover(this.hoverCol);
    var self = this;
    return new Promise(function (resolve) { setTimeout(resolve, duration); }).then(function () { return self; });
  };

  BoardView.prototype._animateDrop = function (disc, r, c) {
    var cellRect = this.cells[r][c].getBoundingClientRect();
    var from;
    if (this.ghostEnabled) {
      var slotRect = this.slots[c].getBoundingClientRect();
      from = slotRect.top - cellRect.top;
    } else {
      var boardRect = this.boardEl.getBoundingClientRect();
      from = boardRect.top - cellRect.top - cellRect.height;
    }
    var ms = Math.round(380 + (r + 1) * 45);
    disc.style.setProperty('--drop-from', from + 'px');
    disc.style.setProperty('--drop-ms', ms + 'ms');
    disc.classList.remove('is-dropping');
    void disc.offsetWidth; // restart animation
    disc.classList.add('is-dropping');
    setTimeout(function () { disc.classList.remove('is-dropping'); }, ms + 30);
    return ms;
  };

  BoardView.prototype.setWinning = function (cells) {
    var has = cells && cells.length > 0;
    this.boardEl.classList.toggle('has-win', has);
    var self = this;
    this.root.querySelectorAll('.disc.is-win').forEach(function (d) { d.classList.remove('is-win'); });
    if (has) {
      cells.forEach(function (rc) {
        var d = self._discEl(rc[0], rc[1]);
        if (d) d.classList.add('is-win');
      });
    }
  };

  BoardView.prototype.shake = function () {
    var el = this.boardEl;
    el.classList.remove('is-shaking');
    void el.offsetWidth;
    el.classList.add('is-shaking');
    setTimeout(function () { el.classList.remove('is-shaking'); }, 450);
  };

  BoardView.prototype.hint = function (col, ms) {
    this.clearHint();
    if (col == null || !this.cols[col]) return;
    this.cols[col].classList.add('is-hint');
    var self = this;
    this._hintTimer = setTimeout(function () { self.clearHint(); }, ms || 3500);
  };
  BoardView.prototype.clearHint = function () {
    if (this._hintTimer) clearTimeout(this._hintTimer);
    this._hintTimer = null;
    this.cols.forEach(function (c) { c.classList.remove('is-hint'); });
  };

  BoardView.prototype.focusColumn = function (col) {
    if (this.cols[col] && this.interactive) this.cols[col].focus({ preventScroll: true });
  };

  window.BoardView = BoardView;
})();
