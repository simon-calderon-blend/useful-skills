# Validation baseline

Regenerated 2026-11-10 (after the font and dark decisions) with `python3 -I scripts/validate_guide.py <path> --kind guide` (literal output, lines cut at 400 chars). Check 9 (render) is SKIP: Playwright is not installed; the examples were looked at with chrome-devtools instead (see README). The canon is not edited and no check was loosened: where it fails, the share deviates from the Blend rules or the check does not fit that kind of artifact.

```
validate_guide: /home/simoncl20/Work/blend/bld/useful-skills/skills/blend-guide/examples/guide  kind=guide
--- blend-web-core validate.py ---
validate: /home/simoncl20/Work/blend/bld/useful-skills/skills/blend-guide/examples/guide/index.html  kind=guide
 1 palette      PASS 16 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 86 KB (limit 2048 KB for 'guide', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
--- guide checks ---
G1   one h1           PASS 1 page(s), one h1 each
G2   links/anchors    PASS all internal links and #anchors resolve
G3   toc              PASS TOC present wherever there are more than 3 sections
G4   code lang        PASS 4 code block(s), all with a language
RESULT: PASS
exit code: 0

validate_guide: /home/simoncl20/Work/blend/bld/useful-skills/skills/blend-guide/examples/course  kind=guide
--- blend-web-core validate.py ---
validate: /home/simoncl20/Work/blend/bld/useful-skills/skills/blend-guide/examples/course/index.html  kind=guide
 1 palette      PASS 16 brand hex, 1 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 89 KB (limit 2048 KB for 'guide', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
--- guide checks ---
G1   one h1           PASS 1 page(s), one h1 each
G2   links/anchors    PASS all internal links and #anchors resolve
G3   toc              PASS TOC present wherever there are more than 3 sections
G4   code lang        PASS 1 code block(s), all with a language
G6a  storage key      PASS all localStorage access inside try/catch; key blend-course-working-with-data-safely-v1
G6b  quiz per module  PASS 3 modules, each with at least one quiz
RESULT: PASS
exit code: 0

validate_guide: /home/simoncl20/Work/blend/bld/blend-share-files/ds-best-practices  kind=guide
--- blend-web-core validate.py ---
validate: /home/simoncl20/Work/blend/bld/blend-share-files/ds-best-practices/index.html  kind=guide
 1 palette      WARN 62 off-palette hex (limit 20); first: #011627, #034AD8, #042038, #078662, #081019, #0969DA, #0B1620, #110011
 2 font         WARN PP Telegraf declared but not embedded: it only renders if installed, otherwise Montserrat/system (use blend_web.py --font embed)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         FAIL official Blend logo SVG missing (assets/logo.svg)
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    FAIL missing local: /ds-best-practices/favicon.svg, /ds-best-practices/_astro/print.DNXP8c50.css, /ds-best-practices/_astro/common.CgUl-Mqs.css, /ds-best-practices/_astro/Code.DYJou4gb.css
 7 dark         PASS both blocks present
 8 weight       FAIL 6057 KB (limit 2048 KB for 'guide', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
--- guide checks ---
G1   one h1           PASS 37 page(s), one h1 each
G2   links/anchors    PASS all internal links and #anchors resolve
G3   toc              PASS TOC present wherever there are more than 3 sections
G4   code lang        PASS 0 code block(s), all with a language
G5   theme            WARN no blend-theme.css (built site); tokens found in common.CgUl-Mqs.css
RESULT: FAIL
exit code: 1

validate_guide: /home/simoncl20/Work/blend/bld/blend-share-files/welcome  kind=guide
--- blend-web-core validate.py ---
validate: /home/simoncl20/Work/blend/bld/blend-share-files/welcome/index.html  kind=guide
 1 palette      PASS 8 brand hex, 16 derived/off-palette
 2 font         FAIL font stack does not start from PP Telegraf
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         FAIL official Blend logo SVG missing (assets/logo.svg)
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 3 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 54 KB (limit 2048 KB for 'guide', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
--- guide checks ---
G1   one h1           PASS 1 page(s), one h1 each
G2   links/anchors    FAIL 13 unresolved, first: index.html:/discovery; index.html:/discovery; index.html:/upload; index.html:/synthetic-studio-docs
G3   toc              FAIL 1 page(s) with >3 sections and no TOC: index.html
G4   code lang        FAIL 1/1 code block(s) without a language
RESULT: FAIL
exit code: 1

validate_guide: /home/simoncl20/Work/blend/bld/useful-skills/skills/blend-guide/assets/starlight  kind=guide
G5   theme            PASS blend-theme.css defines the --blend-* tokens, accent #075089 / #00c6c6
G5b  customCss        PASS astro.config loads blend-theme.css
RESULT: PASS
exit code: 0
```

## Reading the canon results

- **ds-best-practices (Starlight build, FAIL):** the failures come from core checks that assume a single self-contained page, not from the guide checks. Check 4: the build uses the Blend *symbol* SVG, not the 572x110 wordmark. Check 6: absolute `/ds-best-practices/_astro/...` URLs do not resolve against the folder, because the share is served under that base path (the guide check G2 does strip the base, so its links resolve). Check 8: 6057 KB, over the 5120 KB hard limit (Starlight sites are 6-7 MB with mermaid and Pagefind). Check 2 is now a WARN (PP Telegraf declared, not embedded). Check 1 WARN: Starlight/Expressive Code add 62 off-palette hex. G5 WARN: the build has no `blend-theme.css`; the tokens live in `common.*.css`. G1-G3 pass over 37 pages. Treat the weight and logo FAILs as "not applicable to Starlight sites"; they are left as the script reports them.
- **welcome (single page, FAIL):** it is a landing page, not a document guide. Font stack starts from Montserrat (check 2: FAIL), no 572x110 logo (check 4), and its links point to other shares (`/discovery`, `/upload`...), so G2 cannot resolve them standalone. It has more than 3 sections without a TOC (G3) and one `<pre>` without language (G4).
- **Examples:** both pass every check; only check 9 is SKIP. The guide example is built light, the course example with `--dark` (G6a now reports the course key, not the core theme key).
- **Source project** (`assets/starlight`): G5 and G5b pass; the core validator is skipped because there is no HTML yet.

## Design pass 2026-11-13

The runs above predate the design pass and show 10 core checks. The core validator now has check 11 "craft"
(warnings only) and the examples were regenerated. Results on the regenerated examples:

| Target | Exit | FAIL | WARN | Warnings |
|---|---|---|---|---|
| `guide/` | 0 | 0 | 0 | none |
| `course/` | 0 | 0 | 0 | none |

The canonical shares were not re-run; expect check 11 to warn on them (side stripes, uppercase labels, text under 12px).
