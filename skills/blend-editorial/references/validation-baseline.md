# Validation baseline

Run 2026-11-10 with scripts/validate_editorial.py after the core change that embeds PP Telegraf by default. E8 and core check 9 are SKIP (Playwright not installed); 375 px was measured by hand with chrome-devtools (see README). Output is literal; the canon was not loosened to pass. Reading: critical-7 passes the editorial checks (body 16px default, 62ch paragraphs) and only warns on the font (declared but not embedded). synthetic-studio-engagement-model is a dense one-pager-style page (13.5px body, 1.5 line-height, no CTA button), so it fails E1, E2, E3 and E5: those are real deviations from the article/landing rules, not validator bugs. <shares> below is `/home/simoncl20/Work/blend/bld/blend-share-files`.

```
$ python3 scripts/validate_editorial.py examples/article.html --kind article
validate: examples/article.html  kind=article
 1 palette      PASS 16 brand hex, 1 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 82 KB (limit 2048 KB for 'article', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
-- editorial checks
E1 prose measure   PASS .b-prose=68ch
E2 line-height     PASS 1.70 (min 1.6)
E3 body font       PASS 17.0px (min 16)
E4 single h1       PASS 1 h1
E5 CTA             PASS not required for article (1 found)
E6 @page           PASS n/a (not a one-pager)
E7 co-branding     PASS n/a (no client)
E8 375px           SKIP run with --render (Playwright) or measure with chrome-devtools at 375 px
exit=0
```

```
$ python3 scripts/validate_editorial.py examples/one-pager.html --kind one-pager --client --pages 2
validate: examples/one-pager.html  kind=one-pager
 1 palette      PASS 16 brand hex, 1 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 83 KB (limit 500 KB for 'one-pager', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
-- editorial checks
E1 prose measure   PASS .b-prose=68ch
E2 line-height     PASS 1.70 (min 1.6)
E3 body font       PASS 17.0px (min 16)
E4 single h1       PASS 1 h1
E5 CTA             PASS 2 CTA link(s)
E6 @page           PASS @page size 8.5in 11in, 2 sheet(s)
E7 co-branding     PASS topbar Blend x client, alts ok, footer confidential
E8 375px           SKIP run with --render (Playwright) or measure with chrome-devtools at 375 px
exit=0
```

```
$ python3 scripts/validate_editorial.py examples/landing.html --kind landing
validate: examples/landing.html  kind=landing
 1 palette      PASS 16 brand hex, 1 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 82 KB (limit 3072 KB for 'landing', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
-- editorial checks
E1 prose measure   PASS .b-prose=68ch
E2 line-height     PASS 1.70 (min 1.6)
E3 body font       PASS 17.0px (min 16)
E4 single h1       PASS 1 h1
E5 CTA             PASS 2 CTA link(s)
E6 @page           PASS n/a (not a one-pager)
E7 co-branding     PASS n/a (no client)
E8 375px           SKIP run with --render (Playwright) or measure with chrome-devtools at 375 px
exit=0
```

```
$ validate_editorial.py <shares>/critical-7/index.html --kind article
validate: <shares>/critical-7/index.html  kind=article
 1 palette      PASS 8 brand hex, 0 derived/off-palette
 2 font         WARN PP Telegraf declared but neither embedded nor Montserrat fallback
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 80 KB (limit 2048 KB for 'article', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
-- editorial checks
E1 prose measure   PASS .about p=62ch
E2 line-height     PASS 1.65 (min 1.6)
E3 body font       WARN no explicit body font-size (browser default 16px assumed)
E4 single h1       PASS 1 h1
E5 CTA             PASS not required for article (2 found)
E6 @page           PASS n/a (not a one-pager)
E7 co-branding     PASS n/a (no client)
E8 375px           SKIP run with --render (Playwright) or measure with chrome-devtools at 375 px
exit=0
```

```
$ validate_editorial.py <shares>/synthetic-studio-engagement-model/index.html --kind landing
validate: <shares>/synthetic-studio-engagement-model/index.html  kind=landing
 1 palette      PASS 7 brand hex, 1 derived/off-palette
 2 font         WARN PP Telegraf declared but neither embedded nor Montserrat fallback
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 25 KB (limit 3072 KB for 'landing', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
-- editorial checks
E1 prose measure   FAIL no max-width on a prose/article container
E2 line-height     FAIL 1.50 (min 1.6)
E3 body font       FAIL 13.5px (min 16)
E4 single h1       PASS 1 h1
E5 CTA             FAIL no a/button with btn|cta class and href/mailto
E6 @page           PASS n/a (not a one-pager)
E7 co-branding     PASS n/a (no client)
E8 375px           SKIP run with --render (Playwright) or measure with chrome-devtools at 375 px
exit=1
```

## Design pass 2026-11-13

The runs above predate the design pass and show 10 core checks. The core validator now has check 11 "craft"
(warnings only) and the examples were regenerated. Results on the regenerated examples:

| Target | Exit | FAIL | WARN | Warnings |
|---|---|---|---|---|
| `article.html` | 0 | 0 | 0 | none |
| `landing.html` | 0 | 0 | 0 | none |
| `one-pager.html` | 0 | 0 | 0 | none |

The canonical shares were not re-run; expect check 11 to warn on them (side stripes, uppercase labels, text under 12px).
