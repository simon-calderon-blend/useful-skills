# Component recipes

Vocabulary shared with `blend-documents/references/components.md` (Report or analysis).

| Part | Rule | Docx twin |
|---|---|---|
| Masthead | logo left, eyebrow right, 2px cyan rule, h1 max 22ch, standfirst, meta (status, date, audience) | cover |
| Executive summary | first block after the title; navy band; verdict sentence, 1 paragraph, 2 to 4 KPIs with caption | summary + `kpis` + `key` callout |
| KPI tile | big value, label, caption with target or baseline | `kpis` |
| Finding | id, title, severity chip, text, evidence, recommendation; left border follows severity | callout/table |
| Severity | critical, high = `.bad`; medium = `.warn`; low = neutral; info = `.info`. Chips use `--state-*` only | warning callout |
| Evidence | table, code, quote or figure directly under the claim; never a finding without one | table or chart with caption |
| Table | `th` navy with white text, numeric columns right, caption above | `table` |
| Code | dark block, mono, caption below, `tabindex=0` so it scrolls by keyboard | `code` |
| Callout | note (cyan border), key (navy border, mist fill), warning (amber) | callout note/key/warning |
| Recommendations | numbered, with priority chip and owner; decision requested goes in a `key` callout | numbered recommendations |
| Appendix | after the main flow, `Appendix A` prefix, page break in print | landscape appendix |

Audience: internal reports may name teams and tools; client-ready reports drop internal chatter and say "Prepared
for the client". ADRES and client material is internal: no real data, ARNs or secrets in the page.

Print: `@page` A4 with 16/14 mm margins; header, TOC hidden; findings, tables, callouts avoid page breaks; scorecard
shrinks to fit one page (check on the real content: it is not guaranteed for long scorecards).
