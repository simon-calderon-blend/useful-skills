(function () {
  var KEY = 'blend-theme', root = document.documentElement;
  function get() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function set(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }
  function current() {
    return root.getAttribute('data-theme') ||
      (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }
  var saved = get();
  if (saved === 'light' || saved === 'dark') root.setAttribute('data-theme', saved);
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('[data-theme-toggle]');
    if (!b) return;
    var next = current() === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next); set(next);
    b.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
  });
})();
