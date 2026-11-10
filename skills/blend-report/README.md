# blend-report

Report skill for Blend web documents. Created 2026-11-10 from the Reporte category of the share analysis
(`analisis-tipos-documento/informe-reporte-guia-curso.md`). Local only, not published.

## Files

- `SKILL.md` usage and decision table against `blend-documents`.
- `assets/report.css` report layer (loaded after the core CSS). No status colors defined here.
- `scripts/build_report.py` JSON spec to HTML; imports `blend_web.build` from `../blend-web-core`.
- `scripts/validate_report.py` core validator plus R1-R6.
- `examples/` three Illustrative specs and generated pages; `references/` spec, components, validation baseline.

## RESUELTO (user decisions, 2026-11-10; `../blend-web-core/README.md` governs)

- Dark mode stays OPTIONAL: `--dark` adds the core tokens-dark, the toggle (bottom-left, fixed) and `assets/report-dark.css` (score bars, inline code, key callout, info chip, table striping). Without `--dark` that file is not included.
- PP Telegraf embedded by default (+61 KB; `font="none"` for Montserrat). Packaging authorized by the user; license not verified independently.
- Logo: the core `assets/logo.svg`, colored with `--heading` (navy light, white dark). ok/warn/bad colors: accepted as derived from the Design System.

## PENDIENTE (specific to this skill)

| Item | What this skill does meanwhile | How to reverse |
|---|---|---|
| Severity to chip mapping | critical/high = bad, medium = warn, low = neutral, info = info (`--state-info`). A judgment call | edit `SEV` in `build_report.py` and the `data-sev` rules in `report.css` |
| Report language | Labels in es and en only | add a dict in `L` in `build_report.py` |

## Limits

- Core check 9 (render) needs Playwright, not installed here: SKIP. 1280 and 390 px were checked by hand in Chrome
  (no horizontal overflow on the three examples after fixing a grid min-width bug). Print layout was not rendered to
  PDF; `@page`/`@media print` exist and are checked only by presence.
- R1-R6 are regex heuristics: R1 looks for a summary heading or id before the first table/finding; R2 only sees
  blocks with class `finding`/`r-finding`; R3 reads CSS rules, not computed styles.
- The canonical shares fail several checks (see baseline): persona-grounding has no `<html>/<head>` (fragment), no
  print CSS and light-style tables; ai-native-workbench uses system-ui and 3 h1. The checks were not relaxed.
- No chart builder. Use `{"html": "<svg>..."}` blocks for figures, or blend-dashboard for charts.
- The generator escapes text and supports only `` `code` `` inline; there is no Markdown parser.
- `poc-apigw-sc-tls-report` could not be used as a validation baseline (not downloaded locally).
