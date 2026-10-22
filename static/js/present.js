/* AI Arena: presentation mode (/present). Keyboard, click, swipe, hash deep links,
   full screen, speaker notes. Loaded only on the /present page. */
(function () {
  'use strict';

  var deck = document.querySelector('[data-deck]');
  if (!deck) return;

  var A = window.Arena || {};
  var stage = deck.querySelector('[data-stage]');
  var slides = Array.prototype.slice.call(stage.querySelectorAll('.slide'));
  var total = slides.length;
  var current = -1;

  var el = {
    progress: deck.querySelector('[data-progress]'),
    count: deck.querySelector('[data-count]'),
    stageCount: deck.querySelector('[data-stage-count]'),
    title: deck.querySelector('[data-slide-title]'),
    prev: deck.querySelector('[data-prev]'),
    next: deck.querySelector('[data-next]'),
    notes: deck.querySelector('[data-notes]'),
    notesBody: deck.querySelector('[data-notes-body]'),
    notesTitle: deck.querySelector('[data-notes-title]'),
    notesNext: deck.querySelector('[data-notes-next]'),
    notesToggle: deck.querySelector('[data-notes-toggle]'),
    notesClose: deck.querySelector('[data-notes-close]'),
    fullscreen: deck.querySelector('[data-fullscreen]'),
    announce: deck.querySelector('[data-announce]')
  };

  function titleOf(i) { return slides[i] ? slides[i].getAttribute('data-title') || ('Slide ' + (i + 1)) : ''; }
  function isTyping(t) { return A.isTypingTarget ? A.isTypingTarget(t) : /^(input|textarea|select)$/i.test((t && t.tagName) || ''); }

  /* ------------------------------------------------------------------ */
  /* Slide changes                                                      */
  /* ------------------------------------------------------------------ */
  function go(index, opts) {
    opts = opts || {};
    index = Math.max(0, Math.min(total - 1, index));
    if (index === current && !opts.force) { syncHash(); return; }
    current = index;

    slides.forEach(function (s, i) {
      var active = i === index;
      s.classList.toggle('is-active', active);
      s.classList.toggle('is-past', i < index);
      s.setAttribute('aria-hidden', active ? 'false' : 'true');
      if ('inert' in s) s.inert = !active;
      if (active) {
        var inner = s.querySelector('.slide-inner');
        if (inner) inner.scrollTop = 0;
      }
    });

    var label = (index + 1) + ' / ' + total;
    el.count.textContent = label;
    if (el.stageCount) el.stageCount.textContent = label;
    el.title.textContent = titleOf(index);
    el.progress.style.width = (total > 1 ? (index / (total - 1)) * 100 : 100) + '%';
    el.prev.disabled = index === 0;
    el.next.disabled = index === total - 1;
    document.title = titleOf(index) + ' (' + label + ') · AI Arena';
    renderNotes();

    syncHash();
    if (!opts.silent && el.announce) {
      el.announce.textContent = 'Slide ' + (index + 1) + ' of ' + total + ': ' + titleOf(index);
    }
  }
  /* Keep the URL on the slide actually shown, even after an out-of-range or
     malformed hash (#99, #abc) that resolves to the current slide. */
  function syncHash() {
    var hash = '#' + (current + 1);
    if (location.hash !== hash) {
      try { history.replaceState(null, '', hash); } catch (e) { location.hash = hash; }
    }
  }
  function next() { go(current + 1); }
  function prev() { go(current - 1); }

  function indexFromHash() {
    var m = /^#(\d+)$/.exec(location.hash || '');
    return m ? parseInt(m[1], 10) - 1 : null;
  }

  /* ------------------------------------------------------------------ */
  /* Speaker notes                                                      */
  /* ------------------------------------------------------------------ */
  function notesOpen() { return !el.notes.hidden; }
  function renderNotes() {
    if (!notesOpen()) return;
    var src = slides[current].querySelector('.slide-notes');
    el.notesBody.innerHTML = src ? src.innerHTML : '<p class="faint">No notes for this slide.</p>';
    el.notesTitle.textContent = titleOf(current);
    el.notesNext.textContent = current < total - 1 ? titleOf(current + 1) : 'end of deck';
  }
  function setNotes(open) {
    el.notes.hidden = !open;
    deck.classList.toggle('is-notes', open);
    el.notesToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    renderNotes();
  }

  /* ------------------------------------------------------------------ */
  /* Full screen (Fullscreen API, with a CSS-only fallback)             */
  /* ------------------------------------------------------------------ */
  var root = document.documentElement;
  var pseudoFs = false;
  var SVG_OPEN = '<svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';
  var ICON_MAX = SVG_OPEN + '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>';
  var ICON_MIN = SVG_OPEN + '<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>';
  var FS_BLOCKED = 'Full screen is blocked here — Press F11, or open this page in its own browser tab';
  function fsElement() { return document.fullscreenElement || document.webkitFullscreenElement || null; }
  function fsSupported() {
    if (A.fullscreen && A.fullscreen.supported) return A.fullscreen.supported();
    return !!(root.requestFullscreen || root.webkitRequestFullscreen) && !!(document.fullscreenEnabled || document.webkitFullscreenEnabled);
  }
  function syncFs() {
    var real = !!fsElement();
    var on = real || pseudoFs;
    deck.classList.toggle('is-fs', on);
    deck.classList.toggle('is-pseudo-fs', pseudoFs && !real);
    var label, title;
    if (real) { label = 'Exit full screen'; title = 'Exit full screen (F or Esc)'; }
    else if (pseudoFs) { label = 'Exit expanded view'; title = 'Exit expanded view (F or Esc)'; }
    else if (fsSupported()) { label = 'Full screen'; title = 'Full screen (F)'; }
    else { label = 'Expand slides'; title = 'Expand slides (F). Full screen is blocked here'; }
    el.fullscreen.setAttribute('aria-pressed', on ? 'true' : 'false');
    el.fullscreen.setAttribute('aria-label', label);
    el.fullscreen.setAttribute('title', title);
    var want = on ? 'min' : 'max';
    if (el.fullscreen.getAttribute('data-icon') !== want) {
      el.fullscreen.innerHTML = on ? ICON_MIN : ICON_MAX;
      el.fullscreen.setAttribute('data-icon', want);
    }
    poke();
  }
  /* Real full screen is unavailable (iframe without allow="fullscreen", some
     embedded previews, iPhone Safari) or was refused: expand the deck to fill
     the page instead and say why it did not go full screen. */
  function pseudoOn() { pseudoFs = true; syncFs(); }
  function fallbackFs() {
    pseudoOn();
    if (A.toast) A.toast(FS_BLOCKED, { type: 'info', title: 'Expanded the slides instead', icon: 'info', timeout: 6500 });
  }
  function enterFs() {
    /* Shared helper (common.js): requests full screen, and on failure shows the
       "Full screen is blocked here" toast and calls onFallback. */
    if (A.fullscreen && A.fullscreen.toggle) { A.fullscreen.toggle(root, { onFallback: pseudoOn }); return; }
    if (fsSupported()) {
      var req = root.requestFullscreen || root.webkitRequestFullscreen;
      try {
        var p = req.call(root);
        if (p && p.catch) p.catch(fallbackFs);
        return;
      } catch (e) { /* fall through to the fallback */ }
    }
    fallbackFs();
  }
  function exitFs() {
    if (fsElement()) {
      var exit = document.exitFullscreen || document.webkitExitFullscreen;
      if (exit) { try { var q = exit.call(document); if (q && q.catch) q.catch(function () {}); } catch (e) { /* ignore */ } }
    }
    pseudoFs = false;
    syncFs();
  }
  function toggleFs() { if (fsElement() || pseudoFs) exitFs(); else enterFs(); }
  document.addEventListener('fullscreenchange', syncFs);
  document.addEventListener('webkitfullscreenchange', syncFs);

  /* Hide the control bar while the mouse is idle in full screen. */
  var idleTimer = null;
  function poke() {
    deck.classList.remove('is-idle');
    clearTimeout(idleTimer);
    if (deck.classList.contains('is-fs')) {
      idleTimer = setTimeout(function () { deck.classList.add('is-idle'); }, 2500);
    }
  }
  deck.addEventListener('pointermove', poke, { passive: true });

  /* ------------------------------------------------------------------ */
  /* Keyboard (this listener only exists on /present)                   */
  /* ------------------------------------------------------------------ */
  document.addEventListener('keydown', function (e) {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    if (isTyping(e.target)) return;
    var key = e.key;
    var onControl = e.target && e.target.closest && e.target.closest('a, button');
    poke();

    switch (key) {
      case 'ArrowRight': case 'PageDown':
        e.preventDefault(); next(); break;
      case 'ArrowLeft': case 'PageUp':
        e.preventDefault(); prev(); break;
      case ' ': case 'Spacebar':
        if (onControl) return; /* let Space press the focused button */
        e.preventDefault(); if (e.shiftKey) prev(); else next(); break;
      case 'Home':
        e.preventDefault(); go(0); break;
      case 'End':
        e.preventDefault(); go(total - 1); break;
      case 'f': case 'F':
        e.preventDefault(); toggleFs(); break;
      case 's': case 'S':
        e.preventDefault(); setNotes(!notesOpen()); break;
      case 'Escape':
        if (pseudoFs || fsElement()) exitFs();
        if (notesOpen()) setNotes(false);
        break;
      default:
        return;
    }
  });

  /* ------------------------------------------------------------------ */
  /* Click / tap the left or right edge of the stage                    */
  /* ------------------------------------------------------------------ */
  var EDGE = 0.16;
  var suppressClickUntil = 0;
  function edgeOf(clientX) {
    var r = stage.getBoundingClientRect();
    if (!r.width) return 0;
    var x = (clientX - r.left) / r.width;
    return x < EDGE ? -1 : x > 1 - EDGE ? 1 : 0;
  }
  function interactive(t) { return !!(t && t.closest && t.closest('a, button, input, select, textarea, label, summary, [data-no-nav]')); }

  stage.addEventListener('click', function (e) {
    if (Date.now() < suppressClickUntil || interactive(e.target)) return;
    var sel = window.getSelection ? String(window.getSelection()) : '';
    if (sel) return;
    var side = edgeOf(e.clientX);
    if (side < 0) prev(); else if (side > 0) next();
  });
  stage.addEventListener('mousemove', function (e) {
    var side = interactive(e.target) ? 0 : edgeOf(e.clientX);
    stage.classList.toggle('hint-prev', side < 0 && current > 0);
    stage.classList.toggle('hint-next', side > 0 && current < total - 1);
  });
  stage.addEventListener('mouseleave', function () { stage.classList.remove('hint-prev', 'hint-next'); });

  /* ------------------------------------------------------------------ */
  /* Swipe                                                              */
  /* ------------------------------------------------------------------ */
  var touch = null;
  stage.addEventListener('touchstart', function (e) {
    if (e.touches.length !== 1) { touch = null; return; }
    touch = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
  }, { passive: true });
  stage.addEventListener('touchend', function (e) {
    if (!touch || !e.changedTouches.length) return;
    var dx = e.changedTouches[0].clientX - touch.x;
    var dy = e.changedTouches[0].clientY - touch.y;
    var dt = Date.now() - touch.t;
    touch = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.4 && dt < 900) {
      suppressClickUntil = Date.now() + 450;
      if (dx < 0) next(); else prev();
    }
  }, { passive: true });

  /* ------------------------------------------------------------------ */
  /* Buttons, hash, init                                                */
  /* ------------------------------------------------------------------ */
  el.prev.addEventListener('click', prev);
  el.next.addEventListener('click', next);
  el.notesToggle.addEventListener('click', function () { setNotes(!notesOpen()); });
  el.notesClose.addEventListener('click', function () { setNotes(false); });
  el.fullscreen.addEventListener('click', toggleFs);

  window.addEventListener('hashchange', function () {
    var i = indexFromHash();
    if (i !== null) go(i); else syncHash(); /* #abc, #-3: back to the shown slide */
  });

  /* The demo slide tells you how to get back to it. */
  Array.prototype.forEach.call(deck.querySelectorAll('[data-here]'), function (node) {
    var slide = node.closest('.slide');
    var n = slides.indexOf(slide) + 1;
    node.textContent = location.host + location.pathname + '#' + n;
  });

  var start = indexFromHash();
  go(start === null ? 0 : start, { force: true, silent: true });
  syncFs();
  deck.classList.add('is-ready');
})();
