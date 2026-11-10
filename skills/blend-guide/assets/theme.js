/* blend-guide optional dark toggle: appended only when built with --dark. Needs the helpers of guide.js, so it is concatenated inside its IIFE scope. */
  /* theme toggle (only rendered when the page was built with --dark) */
  var tb = $('.g-theme');
  if (tb) {
    var ts = store(cfg.themeKey || 'blend-guide-theme');
    var apply = function (t) { if (t) document.documentElement.setAttribute('data-theme', t); };
    apply(ts.get().t);
    tb.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme') ||
        (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = cur === 'dark' ? 'light' : 'dark'; apply(next); ts.set({ t: next });
    });
  }

