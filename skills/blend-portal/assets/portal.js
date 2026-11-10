/* blend-portal behaviour: search, filter chips, tabs (ARIA), expandable rows, anchors scrollspy, sidebar router.
   Vanilla JS, no dependencies. All content is already in the HTML; this only enhances it. */
(function () {
  'use strict';
  var root = document.querySelector('[data-portal]');
  if (!root) return;
  var variant = root.getAttribute('data-variant');
  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }

  function setHdr() { var h = $('.b-header'); if (h) document.documentElement.style.setProperty('--p-hdr', h.offsetHeight + 'px'); }
  setHdr(); window.addEventListener('resize', setHdr);

  /* ---- search + filters ---- */
  var state = { q: '', type: {}, status: {} };
  function any(o) { return Object.keys(o).length > 0; }
  function filtering() { return !!state.q || any(state.type) || any(state.status); }
  function match(el) {
    if (state.q && el.getAttribute('data-search').indexOf(state.q) < 0) return false;
    if (any(state.type) && !state.type[el.getAttribute('data-type')]) return false;
    if (any(state.status) && !state.status[el.getAttribute('data-status')]) return false;
    return true;
  }
  function apply() {
    var total = 0, shown = 0;
    $$('[data-item]').forEach(function (el) {
      var ok = match(el); el.hidden = !ok;
      if (el.hasAttribute('data-counted')) { total++; if (ok) shown++; }
    });
    $$('[data-group]').forEach(function (g) {
      var id = g.getAttribute('data-group');
      var c = $$('[data-counted]', g).filter(function (e) { return !e.hidden; }).length;
      var n = $('[data-count]', g); if (n) n.textContent = c;
      var none = $('.p-none', g); if (none) none.hidden = c > 0;
      $$('[data-tabcount="' + id + '"]').forEach(function (t) { t.textContent = c; });
      if (variant === 'anchors') {
        var empty = c === 0 && filtering(); g.hidden = empty;
        $$('[data-navfor="' + id + '"]').forEach(function (a) { a.hidden = empty; });
      }
    });
    var s = $('#p-status');
    if (s) s.textContent = shown + ' of ' + total + ' resources' + (filtering() ? ' match' : '');
    var clr = $('#p-clear'); if (clr) clr.hidden = !filtering();
  }
  var q = $('#p-q');
  if (q) q.addEventListener('input', function () { state.q = q.value.trim().toLowerCase(); apply(); });
  $$('[data-filter]').forEach(function (b) {
    b.addEventListener('click', function () {
      var k = b.getAttribute('data-filter'), v = b.getAttribute('data-value');
      var on = b.getAttribute('aria-pressed') !== 'true';
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on) state[k][v] = true; else delete state[k][v];
      apply();
    });
  });
  var clear = $('#p-clear');
  if (clear) clear.addEventListener('click', function () {
    state = { q: '', type: {}, status: {} }; if (q) q.value = '';
    $$('[data-filter]').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
    apply();
  });

  /* ---- expandable rows ---- */
  root.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target.closest('.p-toggle') : null;
    if (!t) return;
    var open = t.getAttribute('aria-expanded') !== 'true';
    t.setAttribute('aria-expanded', open ? 'true' : 'false');
    var d = document.getElementById(t.getAttribute('aria-controls')); if (d) d.hidden = !open;
  });

  /* ---- tabs (WAI-ARIA tabs pattern, automatic activation) ---- */
  var tabs = $$('[role="tab"]');
  function selectTab(t, focus, push) {
    tabs.forEach(function (x) {
      var on = x === t;
      x.setAttribute('aria-selected', on ? 'true' : 'false'); x.tabIndex = on ? 0 : -1;
      var p = document.getElementById(x.getAttribute('aria-controls')); if (p) p.hidden = !on;
    });
    if (focus) t.focus();
    if (push && history.replaceState) history.replaceState(null, '', '#' + t.getAttribute('data-gid'));
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { selectTab(t, false, true); });
    t.addEventListener('keydown', function (e) {
      var j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
      else if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = tabs.length - 1;
      if (j !== null) { e.preventDefault(); selectTab(tabs[j], true, true); }
    });
  });
  if (tabs.length) {
    var want = location.hash.slice(1);
    var hit = tabs.filter(function (t) { return t.getAttribute('data-gid') === want; })[0];
    if (hit) selectTab(hit, false, false);
  }

  /* ---- anchors: scrollspy ---- */
  if (variant === 'anchors' && 'IntersectionObserver' in window) {
    var links = $$('[data-navfor]');
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        links.forEach(function (a) {
          if (a.getAttribute('data-navfor') === en.target.getAttribute('data-group')) a.setAttribute('aria-current', 'true');
          else a.removeAttribute('aria-current');
        });
      });
    }, { rootMargin: '-25% 0px -65% 0px' });
    $$('[data-group]').forEach(function (g) { io.observe(g); });
  }

  /* ---- sidebar + iframe: #/slug router ---- */
  if (variant === 'sidebar') {
    var navs = $$('a.p-nav'), home = $('#p-home'), frame = $('#p-frame'), out = $('#p-linkout'),
        crumb = $('#p-crumb'), newtab = $('#p-newtab'), outlink = $('#p-outlink'), outtitle = $('#p-outtitle');
    var route = function () {
      var m = /^#\/(.+)$/.exec(location.hash), a = null;
      if (m) a = navs.filter(function (n) { return n.getAttribute('data-id') === decodeURIComponent(m[1]); })[0] || null;
      navs.forEach(function (n) { if (n === a) n.setAttribute('aria-current', 'page'); else n.removeAttribute('aria-current'); });
      home.hidden = !!a; frame.hidden = true; out.hidden = true; newtab.hidden = !a;
      if (!a) { crumb.textContent = 'Overview'; frame.removeAttribute('src'); document.title = root.getAttribute('data-title'); return; }
      var title = a.getAttribute('data-title'), href = a.getAttribute('data-href');
      crumb.textContent = title; document.title = title + ' | ' + root.getAttribute('data-title');
      newtab.href = href;
      if (a.getAttribute('data-embed') === '1') {
        frame.title = title; if (frame.getAttribute('src') !== href) frame.src = href; frame.hidden = false;
      } else { outtitle.textContent = title; outlink.href = href; out.hidden = false; frame.removeAttribute('src'); }
      document.body.classList.remove('p-navopen');
    };
    window.addEventListener('hashchange', route); route();
    var mb = $('#p-menu'), sc = $('#p-scrim');
    if (mb) mb.addEventListener('click', function () { document.body.classList.toggle('p-navopen'); mb.setAttribute('aria-expanded', document.body.classList.contains('p-navopen') ? 'true' : 'false'); });
    if (sc) sc.addEventListener('click', function () { document.body.classList.remove('p-navopen'); });
  }
  apply();
})();
