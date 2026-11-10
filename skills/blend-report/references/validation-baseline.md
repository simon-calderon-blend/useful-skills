# Validation baseline

Generated 2026-11-10 by running `scripts/validate_report.py` (core validate.py `--kind report` plus checks R1-R6), after the core change that embeds PP Telegraf by default. Output is literal; no check was loosened to make the canon pass. Core check 9 (render) is SKIP because Playwright is not installed; 1280 and 390 px were checked with chrome-devtools instead (see README).

Reading the canon rows: the two canonical shares were written before these checks existed. Their FAILs are real gaps against the extension (no `@media print`, th not navy, no summary block, no TOC in persona), not validator bugs, with one caveat: R1 is a heading/id heuristic, so persona's hero standfirst (a de facto summary) is not recognized.

## `examples/report-simple.html`

```
$ python3 scripts/validate_report.py examples/report-simple.html
== blend-web-core validate.py --kind report ==
validate: examples/report-simple.html  kind=report
 1 palette      PASS 16 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 94 KB (limit 2048 KB for 'report', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-report checks (variant=simple) ==
core  PASS 0 FAIL, 0 WARN in the core checks (see above)
R1    PASS summary before first table/finding: 'Executive summary'
R2    PASS 3 findings, all with severity chip and evidence
R3    PASS 3 tables with header row; th rule uses navy
R4    PASS @media print and @page present
R5    PASS 5 h2 sections; TOC with 5 working anchors
R6    PASS no status color outside blend-web-core tokens (ok/warn/bad/info)

RESULT: PASS
exit=0
```

## `examples/report-sidebar.html`

```
$ python3 scripts/validate_report.py examples/report-sidebar.html
== blend-web-core validate.py --kind report ==
validate: examples/report-sidebar.html  kind=report
 1 palette      PASS 16 brand hex, 1 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 97 KB (limit 2048 KB for 'report', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-report checks (variant=sidebar) ==
core  PASS 0 FAIL, 0 WARN in the core checks (see above)
R1    PASS summary before first table/finding: 'Executive summary'
R2    PASS 3 findings, all with severity chip and evidence
R3    PASS 3 tables with header row; th rule uses navy
R4    PASS @media print and @page present
R5    PASS 6 h2 sections; TOC with 6 working anchors
R6    PASS no status color outside blend-web-core tokens (ok/warn/bad/info)

RESULT: PASS
exit=0
```

## `examples/report-scorecard.html`

```
$ python3 scripts/validate_report.py examples/report-scorecard.html
== blend-web-core validate.py --kind report ==
validate: examples/report-scorecard.html  kind=report
 1 palette      PASS 16 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 90 KB (limit 2048 KB for 'report', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-report checks (variant=scorecard) ==
core  PASS 0 FAIL, 0 WARN in the core checks (see above)
R1    PASS summary before first table/finding: 'Executive summary'
R2    PASS 2 findings, all with severity chip and evidence
R3    PASS scorecard without tables (score bars are the evidence)
R4    PASS @media print and @page present
R5    PASS 3 h2 sections; TOC not required (scorecard)
R6    PASS no status color outside blend-web-core tokens (ok/warn/bad/info)

RESULT: PASS
exit=0
```

## `persona-grounding-experiment/index.html`

```
$ python3 scripts/validate_report.py /home/simoncl20/Work/blend/bld/blend-share-files/persona-grounding-experiment/index.html
== blend-web-core validate.py --kind report ==
validate: /home/simoncl20/Work/blend/bld/blend-share-files/persona-grounding-experiment/index.html  kind=report
 1 palette      PASS 6 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    FAIL lang, viewport
 4 logo         PASS logo SVG (572x110) present
 5 contrast     WARN cyan/turquoise as text where the rule has no dark background (verify): .stat__figure; .ledger__value
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 139 KB (limit 2048 KB for 'report', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-report checks (variant=simple) ==
core  FAIL 1 FAIL, 1 WARN in the core checks (see above)
R1    FAIL no executive summary / verdict heading before the first table or finding
R2    WARN no finding blocks (class 'finding' / 'r-finding') found; severity/evidence not checkable
R3    FAIL 2 tables, but no CSS rule paints th with navy #053057 (background: var(--blend-navy))
R4    FAIL @media print missing
R5    FAIL 8 h2 sections but no <nav> TOC with 3+ anchor links
R6    PASS no status color outside blend-web-core tokens (ok/warn/bad/info)

RESULT: FAIL
exit=1
```

## `ai-native-workbench/index.html`

```
$ python3 scripts/validate_report.py /home/simoncl20/Work/blend/bld/blend-share-files/ai-native-workbench/index.html
== blend-web-core validate.py --kind report ==
validate: /home/simoncl20/Work/blend/bld/blend-share-files/ai-native-workbench/index.html  kind=report
 1 palette      PASS 8 brand hex, 1 derived/off-palette
 2 font         FAIL font stack does not start from PP Telegraf
 3 structure    FAIL h1 count=3
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 107 KB (limit 2048 KB for 'report', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-report checks (variant=simple) ==
core  FAIL 2 FAIL, 0 WARN in the core checks (see above)
R1    FAIL no executive summary / verdict heading before the first table or finding
R2    WARN no finding blocks (class 'finding' / 'r-finding') found; severity/evidence not checkable
R3    FAIL 5 tables, but no CSS rule paints th with navy #053057 (background: var(--blend-navy))
R4    WARN @page missing
R5    PASS 21 h2 sections; TOC with 16 working anchors
R6    PASS no status color outside blend-web-core tokens (ok/warn/bad/info)

RESULT: FAIL
exit=1
```

