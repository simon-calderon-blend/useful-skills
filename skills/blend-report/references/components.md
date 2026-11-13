# Component recipes

Vocabulary shared with `blend-documents/references/components.md` (Report or analysis).

| Part | Rule | Docx twin |
|---|---|---|
| Masthead | logo left, eyebrow right, 2px cyan rule, h1 max 22ch, standfirst, meta (status, date, audience) | cover |
| Executive summary | first block after the title; the only navy band; verdict sentence set largest, 1 paragraph in soft cyan, 2 to 4 KPIs with caption | summary + `kpis` + `key` callout |
| KPI figure | value with unit, label, caption with target or baseline; a row parted by hairlines, not cards | `kpis` |
| Finding | id, title, severity chip, text, evidence, recommendation; rows parted by hairlines, severity said by the chip (word + dot), no coloured side border | callout/table |
| Severity | critical, high = `.bad`; medium = `.warn`; low = neutral; info = `.info`. Chips use `--state-*` only | warning callout |
| Evidence | table, code, quote or figure directly under the claim, in a tinted well (no border); never a finding without one | table or chart with caption |
| Table | `th` navy with white text, numeric columns right, caption above | `table` |
| Code | dark block, mono, caption below, `tabindex=0` so it scrolls by keyboard | `code` |
| Callout | tinted well with a worded title: note (soft cyan tint), key (navy tint), warning (amber tint); no side stripe | callout note/key/warning |
| Recommendations | numbered rows in priority order, with priority chip and owner; decision requested goes in a `key` callout | numbered recommendations |
| Appendix | after the main flow, `Appendix A` prefix, page break in print | landscape appendix |

Audience: internal reports may name teams and tools; client-ready reports drop internal chatter and say "Prepared
for the client". ADRES and client material is internal: no real data, ARNs or secrets in the page.

Print: `@page` A4 with 16/14 mm margins; header, TOC hidden; findings, tables, callouts avoid page breaks; scorecard
shrinks to fit one page (check on the real content: it is not guaranteed for long scorecards).
