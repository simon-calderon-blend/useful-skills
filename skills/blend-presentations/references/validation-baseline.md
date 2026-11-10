# Validation baseline

Literal output of `scripts/validate_presentation.py` (2026-11-10, after the core change that embeds PP Telegraf by default). Canon failures are left as they are; checks were not loosened.

```
$ python3 scripts/validate_presentation.py examples/index.html
== blend-web-core validate.py --kind presentation ==
validate: examples/index.html  kind=presentation
 1 palette      PASS 16 brand hex, 1 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 86 KB (limit 2048 KB for 'presentation', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== presentation checks ==
E1  interaction     PASS keydown(arrows,Home/End), hashchange, touch, reduced-motion, @media print present
E2  hex unique      PASS 17 unique hex (max 20)
E3  forbidden hex   PASS none
E4  overflow        PASS 5 slides, none overflow at 1280x720
E5  title/lang/aria PASS lang/title ok, 20 aria/role attrs, aria-live present
E6  slides/counter  PASS 5 .slide elements; n/N counter found; notes yes

RESULT: PASS
exit=0
```

```
$ python3 scripts/validate_presentation.py /home/simoncl20/Work/blend/bld/blend-share-files/ai-evaluation-workshop/index.html
== blend-web-core validate.py --kind presentation ==
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

== presentation checks ==
E1  interaction     FAIL missing: Home/End, touch, @media print
E2  hex unique      FAIL 49 unique hex (max 20)
E3  forbidden hex   PASS none
E4  overflow        FAIL 14/21 slides overflow at 1280x720: 1: scrollH 478>457 | 4: scrollH 477>457 | 5: scrollH 535>457; <div.lc-wheel> beyond viewport
E5  title/lang/aria PASS lang/title ok, 61 aria/role attrs, aria-live present
E6  slides/counter  PASS 21 .slide elements; n/N counter found; notes yes

RESULT: FAIL
exit=1
```

```
$ python3 scripts/validate_presentation.py /home/simoncl20/Work/blend/bld/blend-share-files/knowledge-work-transformation/index.html
== blend-web-core validate.py --kind presentation ==
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

== presentation checks ==
E1  interaction     FAIL missing: Home/End, hashchange, prefers-reduced-motion, @media print
E2  hex unique      PASS 10 unique hex (max 20)
E3  forbidden hex   PASS none
E4  overflow        FAIL 4/13 slides overflow at 1280x720: 1: <svg.> beyond viewport | 9: scrollH 622>577; <div.> beyond viewport | 10: scrollH 580>577; <div.team-text> beyond viewport
E5  title/lang/aria FAIL few aria/role attributes (0), no aria-live (counter)
E6  slides/counter  PASS 13 .slide elements; n/N counter found; notes no

RESULT: FAIL
exit=1
```
