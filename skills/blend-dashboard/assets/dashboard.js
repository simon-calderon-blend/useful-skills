/* Blend dashboard runtime. Reads const DATA = {meta, columns, rows, spec}. No dependencies. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var COLS = DATA.columns, ROWS = DATA.rows, SPEC = DATA.spec || {};
  var colBy = {}; COLS.forEach(function (c) { colBy[c.key] = c; });
  var state = { chips: {}, q: "", sortKey: null, sortDir: 1, shown: 0 };
  var PAGE = (SPEC.table && SPEC.table.page_size) || 25;
  if (SPEC.table && SPEC.table.sort) { state.sortKey = SPEC.table.sort.key; state.sortDir = SPEC.table.sort.dir === "asc" ? 1 : -1; }
  var NS = "http://www.w3.org/2000/svg";
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function fmt(v, dec, pre, suf) {
    return (pre || "") + Number(v).toLocaleString("en-US", { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 }) + (suf || "");
  }
  function agg(rows, kind, field) {
    if (kind === "count") return rows.length;
    if (kind === "distinct") { var s = {}; rows.forEach(function (r) { s[r[field]] = 1; }); return Object.keys(s).length; }
    var v = rows.map(function (r) { return Number(r[field]); }).filter(function (x) { return !isNaN(x); });
    if (!v.length) return 0;
    if (kind === "sum") return v.reduce(function (a, b) { return a + b; }, 0);
    if (kind === "avg") return v.reduce(function (a, b) { return a + b; }, 0) / v.length;
    if (kind === "min") return Math.min.apply(null, v);
    if (kind === "max") return Math.max.apply(null, v);
    return 0;
  }
  function filtered() {
    var q = state.q.toLowerCase();
    return ROWS.filter(function (r) {
      for (var k in state.chips) { var set = state.chips[k]; if (Object.keys(set).length && !set[r[k]]) return false; }
      if (q) { var hit = COLS.some(function (c) { return String(r[c.key]).toLowerCase().indexOf(q) >= 0; }); if (!hit) return false; }
      return true;
    });
  }
  /* KPIs: tiles are pre-rendered by the generator; recomputed on the filtered rows */
  function renderKpis(rows) {
    document.querySelectorAll("[data-kpi]").forEach(function (el) {
      var v = agg(rows, el.dataset.agg, el.dataset.field);
      $(".v", el).textContent = fmt(v, +el.dataset.decimals || 0, el.dataset.prefix, el.dataset.suffix);
    });
    var c = $("#d-count"); if (c) c.textContent = rows.length + " of " + ROWS.length + " rows";
  }
  /* Table */
  function sorted(rows) {
    if (!state.sortKey) return rows;
    var k = state.sortKey, num = colBy[k].type === "num", d = state.sortDir;
    return rows.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      if (num) return (Number(x) - Number(y)) * d;
      return String(x).localeCompare(String(y)) * d;
    });
  }
  function cell(c, v) {
    if (c.type === "num" && v !== "" && v !== null) return '<td class="num">' + esc(fmt(v, c.decimals, c.prefix, c.suffix)) + "</td>";
    return "<td>" + esc(v === null ? "" : v) + "</td>";
  }
  function renderTable(rows) {
    var tb = $("#d-table"); if (!tb) return;
    rows = sorted(rows);
    var n = Math.max(state.shown, PAGE), part = rows.slice(0, n);
    $("thead tr", tb).querySelectorAll("th").forEach(function (th) {
      th.setAttribute("aria-sort", th.dataset.key === state.sortKey ? (state.sortDir > 0 ? "ascending" : "descending") : "none");
    });
    $("tbody", tb).innerHTML = part.map(function (r) { return "<tr>" + COLS.map(function (c) { return cell(c, r[c.key]); }).join("") + "</tr>"; }).join("") ||
      '<tr><td colspan="' + COLS.length + '" class="d-empty">No rows match the filters.</td></tr>';
    var more = $("#d-more"); more.hidden = rows.length <= n;
    more.textContent = "Show " + Math.min(PAGE, rows.length - n) + " more";
  }
  /* CSV export of the filtered, sorted rows. Cells that start with = + - @ are prefixed with a quote. */
  function csvCell(v) {
    var s = v === null || v === undefined ? "" : String(v);
    if (/^[=+\-@]/.test(s) && isNaN(Number(s))) s = "'" + s;
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function exportCsv() {
    var rows = sorted(filtered());
    var out = [COLS.map(function (c) { return csvCell(c.label); }).join(",")].concat(rows.map(function (r) {
      return COLS.map(function (c) { return csvCell(r[c.key]); }).join(",");
    })).join("\r\n");
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + out], { type: "text/csv;charset=utf-8" }));
    a.download = (DATA.meta.slug || "data") + ".csv";
    document.body.appendChild(a); a.click(); a.remove();
  }
  /* Charts: hand-written SVG. bar / hbar / line, up to 5 series, one axis, no title inside the figure. */
  function el(tag, attrs, txt) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (txt !== undefined) e.textContent = txt;
    return e;
  }
  function aggregate(ch, rows) {
    var xs = [], sers = [], cells = {};
    rows.forEach(function (r) {
      var x = r[ch.x], s = ch.series ? r[ch.series] : "_";
      if (xs.indexOf(x) < 0) xs.push(x);
      if (sers.indexOf(s) < 0) sers.push(s);
      (cells[x + "\u0000" + s] = cells[x + "\u0000" + s] || []).push(r);
    });
    if (ch.type === "line") xs.sort();
    var data = sers.map(function (s) {
      return xs.map(function (x) { var c = cells[x + "\u0000" + s]; return c ? agg(c, ch.y.agg, ch.y.field) : 0; });
    });
    return { xs: xs, sers: sers, data: data };
  }
  function niceMax(m) { if (m <= 0) return 1; var p = Math.pow(10, Math.floor(Math.log10(m))), f = m / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
  function drawChart(ch, rows, card) {
    var box = $(".plot", card), leg = $(".d-legend", card), tbl = $(".alt", card);
    box.innerHTML = ""; leg.innerHTML = "";
    var A = aggregate(ch, rows);
    if (!A.xs.length) { box.innerHTML = '<div class="d-empty">No data for the current filters.</div>'; tbl.innerHTML = ""; return; }
    var multi = A.sers.length > 1, dec = ch.decimals || 0;
    var color = function (i) { return multi ? "var(--s" + (i + 1) + ")" : "var(--chart-one)"; };
    if (multi) leg.innerHTML = A.sers.map(function (s, i) { return '<span><i style="background:' + color(i) + '"></i>' + esc(s) + "</span>"; }).join("");
    var all = [].concat.apply([], A.data), max = niceMax(Math.max.apply(null, all)), horiz = ch.type === "hbar";
    var W = 640, H = horiz ? Math.max(180, 34 * A.xs.length + 30) : 300;
    var m = horiz ? { l: 110, r: 50, t: 8, b: 24 } : { l: 52, r: 24, t: 14, b: 34 };
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": ch.heading + (ch.unit ? " (" + ch.unit + ")" : "") });
    var ticks = [0, .25, .5, .75, 1];
    ticks.forEach(function (t) {
      var v = max * t, lab = fmt(v, dec);
      if (horiz) { var x = m.l + pw * t; svg.appendChild(el("line", { x1: x, x2: x, y1: m.t, y2: m.t + ph, class: "grid" })); svg.appendChild(el("text", { x: x, y: H - 6, "text-anchor": "middle" }, lab)); }
      else { var y = m.t + ph - ph * t; svg.appendChild(el("line", { x1: m.l, x2: m.l + pw, y1: y, y2: y, class: "grid" })); svg.appendChild(el("text", { x: m.l - 6, y: y + 4, "text-anchor": "end" }, lab)); }
    });
    var n = A.xs.length, band = (horiz ? ph : pw) / n, k = A.sers.length, gap = band * .22, bw = (band - gap) / k;
    var maxLab = horiz ? 16 : Math.max(4, Math.floor(band / 6.5));
    function short(s) { s = String(s); return s.length > maxLab ? s.slice(0, maxLab - 1) + "…" : s; }
    var every = !horiz && band < 54 ? Math.ceil(54 / band) : 1;
    A.xs.forEach(function (x, i) {
      if (i % every === 0) {
        if (horiz) svg.appendChild(el("text", { x: m.l - 8, y: m.t + band * i + band / 2 + 4, "text-anchor": "end" }, short(x)));
        else svg.appendChild(el("text", { x: m.l + band * i + band / 2, y: H - 14, "text-anchor": "middle" }, short(x)));
      }
    });
    if (ch.type === "line") {
      A.data.forEach(function (d, si) {
        var pts = d.map(function (v, i) { return [m.l + band * i + band / 2, m.t + ph - ph * v / max]; });
        svg.appendChild(el("polyline", { points: pts.map(function (p) { return p.join(","); }).join(" "), fill: "none", stroke: color(si), "stroke-width": 2, "stroke-linejoin": "round" }));
        pts.forEach(function (p, i) { var c = el("circle", { cx: p[0], cy: p[1], r: 3, fill: color(si) }); c.appendChild(el("title", {}, A.sers[si] + " / " + A.xs[i] + ": " + fmt(d[i], dec))); svg.appendChild(c); });
        if (k <= 4) { var lp = pts[pts.length - 1]; svg.appendChild(el("text", { x: Math.min(lp[0], W - m.r), y: lp[1] - 8, "text-anchor": "end" }, fmt(d[d.length - 1], dec))); }
      });
    } else {
      A.data.forEach(function (d, si) {
        d.forEach(function (v, i) {
          var len = (horiz ? pw : ph) * v / max, r;
          if (horiz) r = el("rect", { x: m.l, y: m.t + band * i + gap / 2 + bw * si, width: Math.max(len, 0), height: bw, fill: color(si), rx: 2 });
          else r = el("rect", { x: m.l + band * i + gap / 2 + bw * si, y: m.t + ph - len, width: bw, height: Math.max(len, 0), fill: color(si), rx: 2 });
          r.appendChild(el("title", {}, (multi ? A.sers[si] + " / " : "") + A.xs[i] + ": " + fmt(v, dec)));
          svg.appendChild(r);
          if (!multi) {
            if (horiz) svg.appendChild(el("text", { x: m.l + len + 5, y: m.t + band * i + band / 2 + 4 }, fmt(v, dec)));
            else if (n <= 12) svg.appendChild(el("text", { x: m.l + band * i + band / 2, y: m.t + ph - len - 5, "text-anchor": "middle" }, fmt(v, dec)));
          }
        });
      });
    }
    box.appendChild(svg);
    tbl.innerHTML = '<div class="b-table-wrap"><table class="b-table"><thead><tr><th>' + esc(colBy[ch.x].label) + "</th>" +
      A.sers.map(function (s) { return '<th class="num">' + esc(multi ? s : (ch.unit || ch.y.field || "count")) + "</th>"; }).join("") + "</tr></thead><tbody>" +
      A.xs.map(function (x, i) { return "<tr><td>" + esc(x) + "</td>" + A.data.map(function (d) { return '<td class="num">' + fmt(d[i], dec) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table></div>";
  }
  function renderCharts(rows) {
    (SPEC.charts || []).forEach(function (ch) { var card = document.getElementById("chart-" + ch.id); if (card) drawChart(ch, rows, card); });
  }
  function update() { var rows = filtered(); renderKpis(rows); renderCharts(rows); renderTable(rows); }

  /* Wiring */
  document.querySelectorAll("[data-chip-col]").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.dataset.chipCol, v = b.dataset.chipVal, set = (state.chips[k] = state.chips[k] || {});
      if (set[v]) delete set[v]; else set[v] = 1;
      b.setAttribute("aria-pressed", set[v] ? "true" : "false"); state.shown = 0; update();
    });
  });
  var q = $("#d-search"); if (q) q.addEventListener("input", function () { state.q = q.value; state.shown = 0; update(); });
  var th = document.querySelectorAll("#d-table th[data-key]");
  th.forEach(function (h) {
    function go() { var k = h.dataset.key; state.sortDir = state.sortKey === k ? -state.sortDir : 1; state.sortKey = k; update(); }
    h.addEventListener("click", go);
    h.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  $("#d-more").addEventListener("click", function () { state.shown = Math.max(state.shown, PAGE) + PAGE; renderTable(filtered()); });
  $("#d-csv").addEventListener("click", exportCsv);
  document.querySelectorAll(".tgl").forEach(function (b) {
    b.addEventListener("click", function () {
      var card = b.closest(".d-chart"), on = $(".alt", card).hidden;
      $(".alt", card).hidden = !on; $(".plot", card).hidden = on; $(".d-legend", card).hidden = on;
      b.textContent = on ? "Show chart" : "Show as table"; b.setAttribute("aria-pressed", on);
    });
  });
  var tt = $("#d-theme");
  if (tt) tt.addEventListener("click", function () {
    var cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var nxt = cur === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = nxt;
    try { localStorage.setItem("blend-dash-theme", nxt); } catch (e) {}
  });
  try { var t0 = localStorage.getItem("blend-dash-theme"); if (t0 && tt) document.documentElement.dataset.theme = t0; } catch (e) {}
  update();
})();
