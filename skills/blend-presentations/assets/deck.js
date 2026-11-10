/* blend-presentations runtime: keys, hash routing, touch, counter n/N, speaker notes (N), fullscreen (F). No dependencies. */
(function () {
  var deck = document.querySelector('.deck');
  var slides = Array.prototype.slice.call(deck.querySelectorAll('.slide'));
  var counter = document.getElementById('deck-counter');
  var bar = document.querySelector('.deck-progress');
  var notesBox = document.getElementById('deck-notes');
  var cur = -1;

  function fromHash() {
    var n = parseInt((location.hash || '').replace('#', ''), 10);
    return isNaN(n) ? 0 : Math.min(Math.max(n - 1, 0), slides.length - 1);
  }
  function show(i) {
    i = Math.min(Math.max(i, 0), slides.length - 1);
    if (i === cur) return;
    cur = i;
    slides.forEach(function (s, k) {
      s.classList.toggle('active', k === i);
      s.setAttribute('aria-hidden', k === i ? 'false' : 'true');
    });
    var dark = slides[i].classList.contains('dark');
    document.body.classList.toggle('on-dark', dark);
    counter.textContent = (i + 1) + ' / ' + slides.length;
    bar.style.width = ((i + 1) / slides.length * 100) + '%';
    if (location.hash !== '#' + (i + 1)) history.replaceState(null, '', '#' + (i + 1));
    renderNotes();
  }
  function renderNotes() {
    var n = slides[cur].querySelector('.notes');
    notesBox.querySelector('.text').textContent = n ? n.textContent.trim() : '';
  }
  function go(d) { show(cur + d); }
  function toggleNotes(force) {
    var open = typeof force === 'boolean' ? force : notesBox.hidden;
    notesBox.hidden = !open;
  }
  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
  }

  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case 'ArrowRight': case 'ArrowDown': case 'PageDown': case ' ': e.preventDefault(); go(1); break;
      case 'ArrowLeft': case 'ArrowUp': case 'PageUp': e.preventDefault(); go(-1); break;
      case 'Home': e.preventDefault(); show(0); break;
      case 'End': e.preventDefault(); show(slides.length - 1); break;
      case 'n': case 'N': toggleNotes(); break;
      case 'f': case 'F': fullscreen(); break;
      case 'Escape': toggleNotes(false); break;
    }
  });
  window.addEventListener('hashchange', function () { show(fromHash()); });
  var x0 = null, y0 = null;
  deck.addEventListener('touchstart', function (e) { x0 = e.changedTouches[0].clientX; y0 = e.changedTouches[0].clientY; }, { passive: true });
  deck.addEventListener('touchend', function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
    x0 = null;
  }, { passive: true });
  document.getElementById('deck-prev').addEventListener('click', function () { go(-1); });
  document.getElementById('deck-next').addEventListener('click', function () { go(1); });
  document.getElementById('deck-notes-btn').addEventListener('click', function () { toggleNotes(); });
  show(fromHash());
})();
