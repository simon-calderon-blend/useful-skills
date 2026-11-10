# Validation baseline (blend-portal)

Regenerated 2026-11-10 (after the font and dark decisions) with `scripts/validate_portal.py`. Slug check used `references/verified-slugs.txt`: each slug was confirmed with the blend-share MCP `check_path` (`available:false, path already taken` = exists). `list_shares` only lists the user's own shares, so it was not used. Output below is literal.

## `examples/tabs`
```
== blend-web-core validate.py --kind portal ==
validate: examples/tabs/index.html  kind=portal
 1 palette      PASS 16 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 97 KB (limit 2048 KB for 'portal', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-portal checks ==
P1 links        PASS 4 share slug(s) linked, all relative links resolve, no .blend360.app
P2 slugs        PASS all 4 linked slug(s) exist in the list (10 known)
P3 tabs         PASS 3 tabs/3 panels: roles, aria-selected/controls/labelledby, arrow keys
P4 logo/image   PASS logo present; no base64 image over 100 KB
P5 hex          PASS no #003059, #00ECEC or #0d5666
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: PASS
exit=0
```

## `examples/anchors`
```
== blend-web-core validate.py --kind portal ==
validate: examples/anchors/index.html  kind=portal
 1 palette      PASS 16 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 96 KB (limit 2048 KB for 'portal', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-portal checks ==
P1 links        PASS 4 share slug(s) linked, all relative links resolve, no .blend360.app
P2 slugs        PASS all 4 linked slug(s) exist in the list (10 known)
P3 tabs         PASS no tabs in this page (anchors/sidebar variant); nothing to check
P4 logo/image   PASS logo present; no base64 image over 100 KB
P5 hex          PASS no #003059, #00ECEC or #0d5666
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: PASS
exit=0
```

## `examples/sidebar`
```
== blend-web-core validate.py --kind portal ==
validate: examples/sidebar/index.html  kind=portal
 1 palette      PASS 16 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 236 KB (limit 2048 KB for 'portal', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-portal checks ==
P1 links        PASS 1 share slug(s) linked, all relative links resolve, no .blend360.app
P2 slugs        PASS all 1 linked slug(s) exist in the list (10 known)
P3 tabs         PASS no tabs in this page (anchors/sidebar variant); nothing to check
P4 logo/image   PASS logo present; no base64 image over 100 KB
P5 hex          PASS no #003059, #00ECEC or #0d5666
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: PASS
exit=0
```

## `examples/dark` (anchors variant, built with --dark)
```
== blend-web-core validate.py --kind portal ==
validate: examples/dark/index.html  kind=portal
 1 palette      PASS 16 brand hex, 1 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 99 KB (limit 2048 KB for 'portal', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-portal checks ==
P1 links        PASS 4 share slug(s) linked, all relative links resolve, no .blend360.app
P2 slugs        PASS all 4 linked slug(s) exist in the list (10 known)
P3 tabs         PASS no tabs in this page (anchors/sidebar variant); nothing to check
P4 logo/image   PASS logo present; no base64 image over 100 KB
P5 hex          PASS no #003059, #00ECEC or #0d5666
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: PASS
exit=0
```

## `share: spark`
```
== blend-web-core validate.py --kind portal ==
validate: /home/simoncl20/Work/blend/bld/blend-share-files/spark/index.html  kind=portal
 1 palette      PASS 7 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 191 KB (limit 2048 KB for 'portal', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-portal checks ==
P1 links        WARN links outside share.blend360.com (confirm they are intended): blend360.atlassian.net x3, claude.ai x1, curly-adventure-p3oggnr.pages.github.io x1, github.com x11, improved-fiesta-k5o87zn.pages.github.io x1
P2 slugs        PASS all 2 linked slug(s) exist in the list (10 known)
P3 tabs         PASS 4 tabs/4 panels: roles, aria-selected/controls/labelledby, arrow keys
P4 logo/image   PASS logo present; no base64 image over 100 KB
P5 hex          PASS no #003059, #00ECEC or #0d5666
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: WARN
exit=0
```

## `share: ai-native-program-hub`
```
== blend-web-core validate.py --kind portal ==
validate: /home/simoncl20/Work/blend/bld/blend-share-files/ai-native-program-hub/index.html  kind=portal
 1 palette      WARN 111 off-palette hex (limit 20); first: #008B93, #00AEB6, #00DFE6, #03233F, #04172B, #050505, #071F3A, #087356
 2 font         WARN PP Telegraf declared but not embedded: it only renders if installed, otherwise Montserrat/system (use blend_web.py --font embed)
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         FAIL official Blend logo SVG missing (assets/logo.svg)
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 13 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       FAIL 134247 KB (limit 2048 KB for 'portal', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  WARN 6 e-mail address(es) in the page; confirm they may be public

== blend-portal checks ==
P1 links        WARN links outside share.blend360.com (confirm they are intended): eulerapp.com x1, myapplications.microsoft.com x1, partners.openai.com x2, www.blend360.com x1
P2 slugs        PASS all 5 linked slug(s) exist in the list (10 known)
P3 tabs         FAIL role=tablist has no role=tab children
P4 logo/image   FAIL Blend logo SVG (viewBox 0 0 572 110) not present
P5 hex          PASS no #003059, #00ECEC or #0d5666
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: FAIL
exit=1
```

## Extra (known deviation): aiesofferinghub, no slug list
```
== blend-web-core validate.py --kind portal ==
validate: /home/simoncl20/Work/blend/bld/blend-share-files/aiesofferinghub/index.html  kind=portal
 1 palette      FAIL forbidden: #00ECEC (cyan off-token), #0E2841 (Design System content navy, use only inside a product theme), #003059 (docx navy, not for web)
 2 font         FAIL font stack does not start from PP Telegraf
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         FAIL official Blend logo SVG missing (assets/logo.svg)
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 2035 KB (limit 2048 KB for 'portal', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  WARN 3 e-mail address(es) in the page; confirm they may be public

== blend-portal checks ==
P1 links        FAIL relative links with no file: AIES_Offerings_Hub.html
P2 slugs        SKIP no --slugs-file/--shares-dir. Check these with blend-share check_path: semanticlayeraccelerator
P3 tabs         PASS no tabs in this page (anchors/sidebar variant); nothing to check
P4 logo/image   FAIL base64 image over 100 KB (use the inline SVG logo, not a bitmap): index.html: 166 KB, index.html: 166 KB
P5 hex          FAIL forbidden: #003059 (docx navy), #00ECEC (off-token cyan)
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: FAIL

real	0m0.264s
user	0m0.218s
sys	0m0.046s
exit=1
```

## Negative test: bad manifest, then bad page
```
$ build_portal.py bad.json (a .blend360.app url)
build_portal: manifest errors
item 'Spark': .blend360.app is rejected, use https://share.blend360.com/<slug>/ (https://share.blend360.app/spark/)
build exit=1

$ validate_portal.py on a built page edited to add a .blend360.app link, a missing slug and #003059
== blend-portal checks ==
P1 links        FAIL `.blend360.app` links (use https://share.blend360.com/<slug>/): https://share.blend360.app/spark/
P2 slugs        FAIL slug(s) not found: no-such-slug
P3 tabs         PASS 3 tabs/3 panels: roles, aria-selected/controls/labelledby, arrow keys
P4 logo/image   PASS logo present; no base64 image over 100 KB
P5 hex          FAIL forbidden: #003059 (docx navy)
P6 a11y         PASS search labelled, iframes titled, one h1

RESULT: FAIL
exit=1
```

## Reading the baseline

- Examples (tabs, anchors, sidebar, dark): PASS on every core and portal check, including core 2 (PP Telegraf embedded). Check 9 (render) is SKIP everywhere (no Playwright); the tabs example and the dark one (data-theme forced to dark in a copy) were looked at in headless chromium at 1280 px.
- spark: WARN only, for P1 links to Atlassian, GitHub, claude.ai and two github.io hosts (not Blend shares).
- ai-native-program-hub: FAIL, as the canon stands. No Blend logo SVG (core 4 and P4), tab strip without `role="tab"`/panels (P3), many off-palette hex, folder weight over 5 MB from child files, and core 2 WARN (PP Telegraf declared but not embedded). Not loosened.
- aiesofferinghub (deviation): the `#003059`/`#00ECEC` palette and a 166 KB inline image are caught (P4, P5) plus a relative link to a missing file (P1). The wrapper no longer has a timeout: the core validator now finishes on this 2 MB page in well under a second (the run took 0.26 s), so the old 60 s workaround was removed after being tested.
- Negative test: a `.blend360.app` URL is rejected by the builder (exit 1) and by P1 on a built page; a missing slug fails P2; `#003059` fails P5.
