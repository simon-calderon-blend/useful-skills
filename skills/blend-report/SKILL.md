---
name: blend-report
description: Builds Blend360-branded HTML reports for Blend Share (analysis results, POC readouts, post-mortems, evaluations, scorecards) as one self-contained page with executive summary, KPI tiles, findings with severity chips and evidence, tables, code blocks, recommendations and appendices. Three variants - simple masthead, sidebar with TOC, one-page scorecard that prints. Builds on blend-web-core and ships validate_report.py. Use when the user wants a report, informe, post-mortem, evaluation or scorecard as a web page or Blend Share link; for an editable Word report use blend-documents instead.
---

# Blend report

Turns findings, evidence and metrics into one HTML report on the Blend web design system. Layer on top of
[blend-web-core](../blend-web-core/SKILL.md): tokens, components, logo and `blend_web.py` come from there, nothing is copied.

## blend-documents or blend-report?

| The user wants | Use |
|---|---|
| An editable Word file, something to hand over, sign or print from Word, a 10+ page formal deliverable | `blend-documents` (docx) |
| A page to open in the browser, a Blend Share URL, something that must be skimmable and linkable (anchors, TOC) | **this skill** |
| Both | Build the docx with `blend-documents`; build this page as the web twin, same section order and wording |

Same vocabulary in both (executive summary, KPIs, callouts note/key/warning, captions, numbered recommendations;
see `blend-documents/references/components.md`, "Report or analysis"). Differences: web navy is `#053057`
(docx is `#003059`, never use it here), and the web page uses chips ok/warn/bad for severity.

## Inputs to ask for

Title and one-line subtitle · audience (internal or client) · status and date (draft/final) · the verdict in one
sentence · metrics (2 to 4 KPIs with caption/target) · findings (id, severity critical|high|medium|low|info, text,
evidence, recommendation) · tables and code that back each claim · conclusions and recommendations (owner,
priority) · appendices · language (es/en). If a number or source is missing, ask; do not invent. Sample data is
labeled "Illustrative" (`"illustrative": true` adds the chip and footer text).

## Variants

| Variant | Use for | Layout |
|---|---|---|
| `simple` | most reports (up to about 6 sections) | masthead, title, inline contents box, summary, sections |
| `sidebar` | long reports, post-mortems, technical readouts | sticky TOC left (collapses to inline under 900 px) |
| `scorecard` | one-pager for execs, assessments, debriefs | tight spacing, score bars, two columns, `@page` A4 |

## Workflow

1. Write a JSON spec (schema in [references/spec.md](references/spec.md); working specs in `examples/*.json`).
2. `python3 scripts/build_report.py spec.json out/index.html [--variant sidebar] [--dark]`
3. `python3 scripts/validate_report.py out/index.html` (fix every FAIL, read every WARN).
4. Look at 1280 and 390 px, and print preview for the scorecard.

Rules and component recipes: [references/components.md](references/components.md). Executive summary always
comes first, before any table or finding; every finding has a severity chip and evidence; one claim per table or
figure, with a caption.

## Components (class names)

`r-hero` summary band (the one navy region; verdict is the largest text on the page) · `b-kpis/b-kpi` figure row
parted by hairlines · `r-finding` rows + `b-chip critical|high -> bad, medium -> warn, low -> neutral, info` ·
`r-evidence` tinted well · `b-table` (navy `th`) · `pre.r-code` · `b-callout` tinted (note/key/warn) ·
`ol.r-recs` numbered rows · `r-score` bars · `nav.r-toc` · `r-appendix`. Status colors are only
`--state-ok|warn|bad|info` from the core; this skill defines none.

## Design checklist (before delivery)

A report is a Read page. Run the core [delivery checklist](../blend-web-core/references/delivery-checklist.md), then:

- [ ] The verdict is one sentence and is the first thing read; the summary band is the only navy block.
- [ ] 2 to 4 KPIs, each with unit, label and a caption (target, baseline or period); none repeats a table cell-for-cell.
- [ ] Findings are rows parted by hairlines: no side stripes, no table boxed inside a card. Severity is a worded chip.
- [ ] Every table and figure has a caption that states its claim; numeric columns are listed in `num`.
- [ ] Section numbers stay (people cite them); one eyebrow, in the masthead.
- [ ] Recommendations are ordered by priority and each names an owner.
- [ ] Scorecard: fits one A4 page in print preview with the real content.

## Reference examples (shares)

- `persona-grounding-experiment`: closest to the brand. Masthead with logo, 2px cyan rule, standfirst, bands off-white/navy,
  stat and ledger in the closing band. Source of the `simple` look.
- `ai-native-workbench`: long document, sidebar plus right TOC, numbered figures, callouts. Source of `sidebar`.
- `snowflake-partnership-debrief-gls`: KPI row plus priority cards. Source of `scorecard`. Co-branded: keep only the structure.
- `poc-apigw-sc-tls-report` (ADRES, internal): structure only (TOC pills, evidence blocks, details). Read it with the
  blend-share MCP, never WebFetch; copy no content.

## Validation

`validate_report.py` runs the core `validate.py --kind report`, then R1 summary before first table or finding,
R2 every finding has severity and evidence, R3 tables have `th` and CSS paints them navy, R4 `@media print` and
`@page`, R5 TOC when more than 3 sections (not for scorecard), R6 status colors only from core tokens. Results on
the examples and two canonical shares: [references/validation-baseline.md](references/validation-baseline.md).
Decisions taken 2026-11-10 (dark optional, PP Telegraf embedded, logo, status colors) and what is still open: [README.md](README.md).
