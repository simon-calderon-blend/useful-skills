# Validation baseline (regenerated 2026-11-10, after the font/dark decisions)

Verbatim output of `python3 -I scripts/validate_api.py <dir>` (lines cut at 400 chars). Core check 2 now passes only with PP Telegraf embedded; check 7 reads "optional by decision". Caveats that matter for reading it:

- **Canonical API shares**: `adr-claim-settlement-api` and `adres-siniestros-gateway-api` are internal ADRES shares (structure
  reference only). They are not downloaded under `blend-share-files/`; I read their `index.html` through the blend-share MCP.
  Their vendored `swagger-ui` bundle/css and `openapi.json` were NOT downloaded (1.5 MB each, signed URLs), so the copies in
  the scratchpad contain only an abbreviated `index.html` (banner text shortened, structure/CSS/JS options kept as is).
  Consequence: core check 6 reports "missing local" and my A1/A5/A7/A8 fail for lack of files, not because of the canon's
  content. The informative signals are checks 1, 2, 4 (no Blend palette, no embedded PP Telegraf, no logo) and A6.
- Core validate.py is run on `index.html`, not on the folder (see validate_api.py docstring).
- `openapi-spec-validator` is not installed here: A1 only validates minimal structure and says so (WARN).
- A7/A8 ran in headless chromium (CLI, `--dump-dom` probe), because the chrome-devtools MCP browser was locked by another
  session. The same probe reads `getComputedStyle('.swagger-ui .info .title').color`.

## Example: examples/orders-api (single page, status current, light)
```
== blend-web-core validate.py (--kind api) on index.html ==
validate: examples/orders-api/index.html  kind=api
 1 palette      PASS 16 brand hex, 3 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 92 KB (limit 3072 KB for 'api', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-api-spec checks ==
A1  spec openapi.json        WARN  7 operations; minimal structure only (openapi-spec-validator not installed, so full schema validation did NOT run)
A2  $refs openapi.json       PASS  24 refs, all resolve locally
A3  examples openapi.json    PASS  all 7 operations have request and 2xx response examples
A1  inline == file           PASS  embedded spec equals openapi.json
A4  secrets                  PASS  no JWT/AWS key/ARN/token patterns in html or spec (regex only; read the spec for real client data)
A5  pinned local swagger     PASS  swagger-ui-dist 5.34.1 local, no unpkg/@5/@latest
A6  fixed options            PASS  deepLinking:true, docExpansion:'list', supportedSubmitMethods:[], validatorUrl:null
A7  .info .title color       PASS  computed rgb(5, 48, 87) (expected rgb(5, 48, 87)); css rule ok
A8  render                   PASS  7 operation blocks, 0 uncaught script errors, horizontal overflow 0px (headless chromium, 1280 px)
A9  folder weight            PASS  1942 KB total including vendor (warn >3072, fail >5120)

RESULT: WARN
exit=0
```

## Example: examples/orders-api-compare (comparator, light)
```
== blend-web-core validate.py (--kind api) on index.html ==
validate: examples/orders-api-compare/index.html  kind=api
 1 palette      PASS 16 brand hex, 3 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 82 KB (limit 3072 KB for 'api', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-api-spec checks ==
A1  spec openapi-proposed.json WARN  8 operations; minimal structure only (openapi-spec-validator not installed, so full schema validation did NOT run)
A2  $refs openapi-proposed.json PASS  26 refs, all resolve locally
A3  examples openapi-proposed.json PASS  all 8 operations have request and 2xx response examples
A1  spec openapi.json        WARN  7 operations; minimal structure only (openapi-spec-validator not installed, so full schema validation did NOT run)
A2  $refs openapi.json       PASS  24 refs, all resolve locally
A3  examples openapi.json    PASS  all 7 operations have request and 2xx response examples
A4  secrets                  PASS  no JWT/AWS key/ARN/token patterns in html or spec (regex only; read the spec for real client data)
A5  pinned local swagger     PASS  swagger-ui-dist 5.34.1 local, no unpkg/@5/@latest
A6  fixed options            PASS  deepLinking:true, docExpansion:'list', supportedSubmitMethods:[], validatorUrl:null
A7  .info .title color       PASS  computed rgb(5, 48, 87) (expected rgb(5, 48, 87)); css rule ok
A8  render                   PASS  7 operation blocks, 0 uncaught script errors, horizontal overflow 0px (headless chromium, 1280 px)
A9  folder weight            PASS  2118 KB total including vendor (warn >3072, fail >5120)

RESULT: WARN
exit=0
```

## Example: examples/orders-api-dark (single page, --dark)
```
== blend-web-core validate.py (--kind api) on index.html ==
validate: examples/orders-api-dark/index.html  kind=api
 1 palette      PASS 16 brand hex, 5 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     WARN cyan/turquoise as text where the rule has no dark background (verify): :root:not([data-theme="light"]) .b-api-t; :root:not([data-theme="light"]) .swagger; :root:not([data-theme="light"]) .swagger
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 100 KB (limit 3072 KB for 'api', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-api-spec checks ==
A1  spec openapi.json        WARN  7 operations; minimal structure only (openapi-spec-validator not installed, so full schema validation did NOT run)
A2  $refs openapi.json       PASS  24 refs, all resolve locally
A3  examples openapi.json    PASS  all 7 operations have request and 2xx response examples
A1  inline == file           PASS  embedded spec equals openapi.json
A4  secrets                  PASS  no JWT/AWS key/ARN/token patterns in html or spec (regex only; read the spec for real client data)
A5  pinned local swagger     PASS  swagger-ui-dist 5.34.1 local, no unpkg/@5/@latest
A6  fixed options            PASS  deepLinking:true, docExpansion:'list', supportedSubmitMethods:[], validatorUrl:null
A7  .info .title color       PASS  computed rgb(5, 48, 87) (expected rgb(5, 48, 87)); css rule ok
A8  render                   PASS  7 operation blocks, 0 uncaught script errors, horizontal overflow 0px (headless chromium, 1280 px)
A9  folder weight            PASS  1950 KB total including vendor (warn >3072, fail >5120)

RESULT: WARN
exit=0
```

## Canon 1: adr-claim-settlement-api (abbreviated copy, see caveat)
```
== blend-web-core validate.py (--kind api) on index.html ==
validate: canon/adr-claim-settlement-api/index.html  kind=api
 1 palette      FAIL no Blend token hex found at all
 2 font         FAIL font stack does not start from PP Telegraf
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         FAIL official Blend logo SVG missing (assets/logo.svg)
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    FAIL missing local: ./swagger-ui.min.css, ./swagger-ui-bundle.min.js
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 1 KB (limit 3072 KB for 'api', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-api-spec checks ==
A1  spec                     FAIL  no openapi.json/yaml and no inline #spec
A4  secrets                  PASS  no JWT/AWS key/ARN/token patterns in html or spec (regex only; read the spec for real client data)
A5  pinned local swagger     FAIL  vendor bundle/css missing; vendor/VERSION is not an exact 5.x.y
A6  fixed options            PASS  deepLinking:true, docExpansion:'list', supportedSubmitMethods:[], validatorUrl:null
A7  .info .title color       FAIL  computed none (expected rgb(5, 48, 87)); css rule NOT found
A8  render                   FAIL  0 operation blocks, 1 uncaught script errors, horizontal overflow 0px (headless chromium, 1280 px)
A9  folder weight            PASS  1 KB total including vendor (warn >3072, fail >5120)

RESULT: FAIL
exit=1
```

## Canon 2: adres-siniestros-gateway-api (abbreviated copy, see caveat)
```
== blend-web-core validate.py (--kind api) on index.html ==
validate: canon/adres-siniestros-gateway-api/index.html  kind=api
 1 palette      PASS 1 brand hex, 2 derived/off-palette
 2 font         FAIL font stack does not start from PP Telegraf
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         FAIL official Blend logo SVG missing (assets/logo.svg)
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    FAIL missing local: vendor/swagger-ui.css, vendor/swagger-ui-bundle.js
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 1 KB (limit 3072 KB for 'api', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)

== blend-api-spec checks ==
A1  spec                     FAIL  no openapi.json/yaml and no inline #spec
A4  secrets                  PASS  no JWT/AWS key/ARN/token patterns in html or spec (regex only; read the spec for real client data)
A5  pinned local swagger     FAIL  vendor bundle/css missing; vendor/VERSION is not an exact 5.x.y
A6  fixed options            FAIL  missing/changed: index.html:validatorUrl
A7  .info .title color       FAIL  computed none (expected rgb(5, 48, 87)); css rule NOT found
A8  render                   FAIL  0 operation blocks, 1 uncaught script errors, horizontal overflow 0px (headless chromium, 1280 px)
A9  folder weight            PASS  1 KB total including vendor (warn >3072, fail >5120)

RESULT: FAIL
exit=1
```

## Reading the baseline

- Examples: no FAIL. WARN on A1 is the missing `openapi-spec-validator`. The `--dark` example has a core check 5 WARN: the heuristic sees cyan text in dark-layer rules whose own block has no background (the dark page provides it); it was looked at by eye (README, Known limits).
- Canons (abbreviated copies, no vendor files or spec): FAIL as expected; checks 2 and 4 show they use no PP Telegraf and no Blend logo, and the missing-file FAILs (6, A1, A5, A8) come from the copies, not from the canon.

## Design pass 2026-11-13

The runs above predate the design pass and show 10 core checks. The core validator now has check 11 "craft"
(warnings only) and the examples were regenerated. Results on the regenerated examples:

| Target | Exit | FAIL | WARN | Warnings |
|---|---|---|---|---|
| `orders-api/` | 0 | 0 | 1 | A1  spec openapi.json        WARN  7 operations; minimal structure onl |
| `orders-api-dark/` | 0 | 0 | 2 | 5 contrast     WARN cyan/turquoise as text where the rule has no dark ; A1  spec openapi.json        WARN  7 operations; minimal structure onl |
| `orders-api-compare/` | 0 | 0 | 2 | A1  spec openapi-proposed.json WARN  8 operations; minimal structure o; A1  spec openapi.json        WARN  7 operations; minimal structure onl |

The canonical shares were not re-run; expect check 11 to warn on them (side stripes, uppercase labels, text under 12px).
