---
name: blend-dashboard
description: Builds self-contained Blend360 dashboards and data views as one HTML file for Blend Share, with KPI tiles, filter chips and search, SVG charts, and a sortable table with CSV export, all driven by an embedded JSON dataset. Includes a table-only mode and an optional light/dark theme. Use when the user wants a Blend dashboard, KPI board, tracker or data table page from JSON or CSV, or asks to check one with the validator. For static decks, reports or articles use the other blend-* skills.
---

# Blend dashboard

Builds on `blend-web-core` (tokens, components, logo, `validate.py`); nothing from it is copied.

## What it produces

One `index.html`, no build step: Blend header and logo, title with "Updated" date, KPI tiles, filter chips
and search, up to a handful of SVG charts (bar, hbar, line), a sticky sortable table with "Show more" and
**Export CSV**, a footer with source. Data lives in `const DATA = {meta, columns, rows, spec}`. Every chart has a
"Show as table" toggle. KPIs, charts and table all follow the active filters.

## Inputs to ask the user

Title, subtitle, cut-off date, source line; the data (CSV with header, or JSON list of objects); the KPIs
(`agg` = count, sum, avg, min, max, distinct, plus `field`, `decimals`, `prefix`, `suffix`); which categorical
columns become chips; which charts (type, `x`, `y` agg and field, optional `series` column); `mode`
(`dashboard`, or `table` for a plain tabular dataset); language; dark yes or no (default no); real or Illustrative.

## Flow

1. Write a spec JSON (see `examples/illustrative-dashboard.json`; `"csv": "file.csv"` instead of `"rows"` works,
   path relative to the spec).
2. `python3 scripts/build_dashboard.py spec.json out/index.html [--dark]`
3. `python3 scripts/validate_dashboard.py out/index.html`; fix every FAIL, read every WARN.
4. Look at it at 1280 and 390 px.

Data over about 1 MB: keep the page small and ask the user before moving rows to a CSV loaded by `fetch`
(the KPI check then reports WARN, since the data is not embedded).

## Rules

- Tokens come from blend-web-core (`:root` navy `#053057`, paper, ink). Cyan is never text on light.
- Charts: one series is navy (cyan in dark); 2 to 5 series use the fixed order blue `#2F6FA3`, teal `#00A3A3`,
  amber `#E39B2D`, violet `#8E6BBF`, red `#C8524B`, the set validated in
  `../blend-documents/references/charts.md`. More than 5 series: the builder refuses; fold into "Other".
  No dual axis, no title inside the SVG (heading is the card title), legend above when 2+ series, value labels
  only on single-series bars, last-point label on lines. Status colors (ok/warn/bad) only for status.
- Chart.js is optional and pinned: `https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js`. The
  bundled runtime does not need it.
- Dark is opt-in (`--dark` or `"dark": true`): adds `assets/dashboard-dark.css` and a theme toggle, with both
  `prefers-color-scheme` and `[data-theme]`. The page has its own `d-theme` button, so the core adds no second one. PP Telegraf is embedded by default.
- CSV export prefixes cells starting `= + - @` with `'` (formula injection). No PII: drop names, e-mails, IDs.
- ADRES/client dashboards are internal: use them for structure only, never their data.

## Reference shares

`blend-events` (`const DATA`, chips, calendar; canonical Blend look), `hackathon-anthropic-api-usage-tracker`
(tiles on navy, bar proportions, dark variant), `hackathon-map` (cdnjs d3 pinned), `pace-dashboard` (Chart.js 4.4.0
multi-tab; client-branded, so retheme: do not reuse its cream/gold), `hallazgos-criticos-prod` (ADRES, internal):
only the dual-theme pattern.

## Validation

`validate_dashboard.py` runs blend-web-core `validate.py --kind dashboard` and adds: D1 DATA parses, D2 every
`data-kpi` tile equals the value recomputed from the rows, D3 PII, D4 `<script src>` only cdnjs with exact version,
D5 chart rules. Results: [references/validation-baseline.md](references/validation-baseline.md). README: resolved decisions, open items and limits.
