/* blend-guide runtime: TOC scrollspy, copy buttons, optional theme toggle, course progress and quizzes.
   Works without localStorage: every access is wrapped in try/catch. */
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var cfg = {}; try { cfg = JSON.parse($('#g-config').textContent); } catch (e) {}

  function store(key) {
    return {
      get: function () { try { return JSON.parse(localStorage.getItem(key)) || {}; } catch (e) { return {}; } },
      set: function (v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch (e) {} }
    };
  }

  /*THEME*/

  /* phones: the contents start collapsed so the title is the first thing read (open without JS) */
  var tocd = $('.g-toc details'); if (tocd && window.matchMedia && matchMedia('(max-width: 59.99rem)').matches) tocd.removeAttribute('open');

  /* copy buttons */
  $$('.g-code .copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var txt = $('pre', b.closest('.g-code')).innerText;
      var ok = function () { b.textContent = 'Copied'; b.setAttribute('data-done', ''); setTimeout(function () { b.textContent = 'Copy'; b.removeAttribute('data-done'); }, 2000); };
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(txt).then(ok, function () {}); }
      else { var ta = document.createElement('textarea'); ta.value = txt; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); ok(); } catch (e) {} document.body.removeChild(ta); }
    });
  });

  /* where am I: the last section whose top has passed a quarter of the viewport; the first at load, the last at the bottom */
  var links = $$('.g-toc a[href^="#"]');
  var targets = links.map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); });
  function spy() {
    var line = window.innerHeight * 0.25, cur = 0;
    targets.forEach(function (t, i) { if (t && t.getBoundingClientRect().top <= line) cur = i; });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) cur = links.length - 1;
    links.forEach(function (a, i) { a.classList.toggle('active', i === cur); if (i === cur) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current'); });
  }
  if (links.length) {
    var tick = false;
    window.addEventListener('scroll', function () { if (!tick) { tick = true; requestAnimationFrame(function () { tick = false; spy(); }); } }, { passive: true });
    window.addEventListener('resize', spy); spy();
  }

  /* course: quizzes + progress */
  if (cfg.mode !== 'course') return;
  var st = store(cfg.key), state = st.get(); state.quiz = state.quiz || {};
  var mods = $$('[data-mod]');
  function modDone(m) { var qs = $$('[data-quiz]', m); return qs.length > 0 && qs.every(function (q) { return state.quiz[q.getAttribute('data-quiz')] === true; }); }
  function refresh() {
    var n = 0;
    mods.forEach(function (m) {
      var d = modDone(m); if (d) n++;
      var li = $('.g-toc [data-for="' + m.id + '"]'); if (li) li.classList.toggle('done', d);
      var mk = $('.g-modmark', m); if (mk) { mk.textContent = d ? 'Done' : ''; mk.className = 'g-modmark b-chip' + (d ? ' ok' : ''); mk.hidden = !d; }
    });
    var f = $('.g-progress .fill'); if (f) f.style.transform = 'scaleX(' + (mods.length ? n / mods.length : 0) + ')';
    var s = $('.g-progress small'); if (s) s.textContent = n + ' of ' + mods.length + ' modules completed';
  }
  $$('[data-quiz]').forEach(function (host) {
    var id = host.getAttribute('data-quiz'), ans = parseInt(host.getAttribute('data-answer'), 10);
    var opts = $$('.opt', host), fb = $('.fb', host), retry = $('.retry', host);
    function mark(sel) {
      opts.forEach(function (o, i) { o.disabled = true; o.classList.toggle('right', i === ans); o.classList.toggle('wrong', i === sel && sel !== ans); });
      fb.hidden = false; fb.textContent = (sel === ans ? 'Correct. ' : 'Not quite. ') + host.getAttribute('data-why');
      retry.hidden = sel === ans;
    }
    opts.forEach(function (o, i) { o.addEventListener('click', function () {
      state.quiz[id] = (i === ans); st.set(state); mark(i); refresh(); }); });
    retry.addEventListener('click', function () {
      delete state.quiz[id]; st.set(state);
      opts.forEach(function (o) { o.disabled = false; o.classList.remove('right', 'wrong'); }); fb.hidden = true; retry.hidden = true; refresh(); });
    if (state.quiz[id] === true) mark(ans);
  });
  var rs = $('.g-reset'); if (rs) rs.addEventListener('click', function () { state = { quiz: {} }; st.set(state); location.reload(); });
  refresh();
})();
