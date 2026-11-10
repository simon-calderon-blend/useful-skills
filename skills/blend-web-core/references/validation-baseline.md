# Validation baseline

validate.py re-run on 2026-11-10 (after the font/dark decisions) against the canonical shares. Check 9 (render) is SKIP: Playwright is not installed. Statuses are the script output; they show where the canon itself deviates.

```
validate: /home/simoncl20/Work/blend/bld/blend-share-files/ai-evaluation-workshop/index.html  kind=presentation
 1 palette      WARN 42 off-palette hex (limit 20); first: #00B8B8, #1D1717, #2A2230, #2B1E1A, #2E1F1B, #35231F, #5E5F66, #5E9A7C
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 467 KB (limit 2048 KB for 'presentation', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  WARN 1 e-mail address(es) in the page; confirm they may be public

validate: /home/simoncl20/Work/blend/bld/blend-share-files/knowledge-work-transformation/index.html  kind=presentation
 1 palette      PASS 9 brand hex, 1 derived/off-palette
 2 font         FAIL font stack does not start from PP Telegraf
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         PASS logo SVG (572x110) present
 5 contrast     WARN cyan/turquoise as text where the rule has no dark background (verify): .eyebrow; .s-cover h1 span; .s-problem h2 em; .s-harness h2 em
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 60 KB (limit 2048 KB for 'presentation', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

validate: /home/simoncl20/Work/blend/bld/blend-share-files/blend-spark-harness-engineering/index.html  kind=presentation
 1 palette      PASS 6 brand hex, 6 derived/off-palette
 2 font         WARN PP Telegraf declared but neither embedded nor Montserrat fallback
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         FAIL official Blend logo SVG missing (assets/logo.svg)
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 3 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 73 KB (limit 2048 KB for 'presentation', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

validate: /home/simoncl20/Work/blend/bld/blend-share-files/blend-events/index.html  kind=dashboard
 1 palette      PASS 7 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 191 KB (limit 2048 KB for 'dashboard', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

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

```
