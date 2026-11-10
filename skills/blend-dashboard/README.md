# blend-dashboard

Dashboards and data views for Blend Share. Created 2026-11-10 from the analysis of the dashboard shares
(`informe-dashboard-api.md`). Local only, not published.

## RESUELTO (user decisions, 2026-11-10; the core README governs)

- Dark mode stays OPTIONAL (`--dark` / `"dark": true`). The dashboard keeps its own `d-theme` button (and `dashboard.js` handler, key `blend-dash-theme`); the core detects a `<button>` with "theme" in the body and does not add a second one.
- PP Telegraf embedded by default (+61 KB; `font="none"` for Montserrat). Packaging authorized by the user; license not verified independently.
- Logo: the one in `blend-web-core/assets/logo.svg`. Status colors ok/warn/bad: accepted as derived from the Design System (no official guide).

## PENDIENTE (specific to this skill)

| Item | Meanwhile | Reverse |
|---|---|---|
| Series palette | The five hues of `blend-documents/references/charts.md` (validated on white). Not re-validated for dark or color-blind separation on the web | edit `--s1..--s5` in `assets/dashboard.css` |
| Dark series hues | `dashboard-dark.css` is opt-in; the series keep the same hues on dark (contrast 3.3 to 7.5 on `#1A1A1A`). Not re-validated for color-blind separation | delete `dashboard-dark.css` and the `--dark` branch |
| Chart.js | Allowed pinned at 4.4.0, but the runtime is hand-written SVG | none needed |
| Navy and paper | Web values (053057, F4F3F0), unlike docx | n/a |

## Limits

- The KPI check reads only `data-kpi` tiles with `agg` over `DATA.rows`; pages that build KPIs in JS or hold rows
  under another key (blend-events uses `events`) get WARN, not a pass.
- Charts: bar, hbar, line, aggregating with sum/avg/min/max/count/distinct. No stacked, donut, scatter, heatmap.
- Rows render client-side; CSV for the export is the filtered view, only columns in the spec.
- Pages above 1 MB of data are not split automatically.
- Core check 9 (render) is SKIP: no Playwright here. The example was checked by hand with chrome-devtools: the
  1280 view directly (the browser window was 3416 px wide and could not be resized) and 390 px inside a 390 px
  iframe; no horizontal overflow, filter, sort and table toggle worked.
- Not tested: CSV download itself (code path only), Safari/Firefox. Dark rendering was looked at in headless chromium with `data-theme="dark"` forced (2026-11-10).
