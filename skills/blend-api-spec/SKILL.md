---
name: blend-api-spec
description: Builds a publishable Blend360-themed API documentation folder (Swagger UI from an OpenAPI 3.x spec) for Blend Share, with a pinned local Swagger UI bundle, the Blend logo header, hidden Swagger topbar, navy titles, a Blend method-chip palette, a current/proposed status banner and an optional current-vs-proposed comparator. Includes validate_api.py. Use when the user wants to publish, theme or check an OpenAPI/Swagger page, or says "documentacion de API", "swagger", "contrato propuesto/vigente". Builds on blend-web-core.
---

# Blend API spec (OpenAPI / Swagger UI)

Today the 6 API shares use Swagger UI with no Blend theme, 3 of them from a floating `unpkg ...@5`. This skill produces a
folder you can upload as a share, with a fixed Swagger UI version served locally.

## Produces

`OUT/index.html` (header with logo, status banner, themed Swagger UI) + `OUT/openapi.json` (the spec, downloadable) +
`OUT/vendor/` (`swagger-ui-bundle.js`, `swagger-ui.css`, `LICENSE`, `NOTICE`, `VERSION`; swagger-ui-dist 5.34.1).
The spec is also embedded in the page as `<script type="application/json" id="spec">`, so it works from `file://`.
Comparator mode adds `actual.html`, `propuesta.html` and `openapi-proposed.json`; `index.html` becomes a shell with the
toggle Side by side / Current / Proposed (structure borrowed from `adr-contrato-sia-version-motor`).

## Inputs to ask the user

OpenAPI 3.x file (JSON; YAML needs PyYAML), title, version, **status** (`current` or `proposed`) and the in-force date,
language (`en`/`es`), whether it is a private API (it always is: Try it out is off), whether dark is wanted, and for the
comparator the proposed spec. Examples in the spec must be fictitious.

## Flow

```bash
python3 scripts/build_api_spec.py --spec api.json --title "Orders API" --version 1.0.0 \
  --status current --since 2026-11-10 --lang en --out out/ [--dark] [--compare-spec proposed.json]
python3 scripts/validate_api.py out/
```

1. Check the spec has `summary`, `operationId`, request/response examples and no real data before building.
2. Build, then run `validate_api.py` and fix every FAIL; read every WARN.
3. Look at `out/index.html` at 1280 and 390 px (chrome-devtools, or headless chromium `--screenshot`).
4. Upload `out/` as a whole folder (the vendor files must go with it).

## Fixed decisions

- Swagger options: `deepLinking:true`, `docExpansion:'list'`, `supportedSubmitMethods:[]`, `validatorUrl:null`
  (plus `defaultModelsExpandDepth:1`, `defaultModelExpandDepth:3`, `displayOperationId:true`). Do not change them.
- No topbar (not loaded, and hidden in CSS). `.swagger-ui .info .title` is `#053057`.
- Never `unpkg`, `@5` or `@latest`. To upgrade run `scripts/fetch_swagger.sh 5.x.y` (exact version, needs network and npm).
- Banner: `current` is a navy band (cyan label on navy is allowed), `proposed` is an amber band
  ("Proposed contract, not deployed"), as in `adr-claim-settlement-api`.
- Method chips: [references/method-chips.md](references/method-chips.md).
- Dark is opt-in (decided 2026-11-10; `--dark`: `tokens-dark.css` + core toggle + `assets/blend-swagger-dark.css`), both `prefers-color-scheme` and `[data-theme]`.
- PP Telegraf is embedded in every page via `blend_web.font_face()` (core); no Google Fonts link.

## Reuses from blend-web-core

`assets/tokens.css`, `tokens-dark.css`, `theme-toggle.*`, `components.css` (`b-header`, `b-chip`), `logo.svg`, `scripts/blend_web.py` (`font_face()`), and `scripts/validate.py` (run as subprocess).
Own files: `assets/blend-swagger-theme.css`, `assets/blend-swagger-dark.css`, `assets/vendor/`, `scripts/`.

## Reference shares (internal ADRES; structure only, nothing copied)

Read with the blend-share MCP tools (`list_share_files`, `read_share_file`), never WebFetch.
- `adr-claim-settlement-api`: amber "proposed" banner, hidden topbar, local pinned bundle, option set.
- `adres-siniestros-gateway-api`: navy "current in test since date" banner, `supportedSubmitMethods: []`.
- `adr-contrato-sia-version-motor`: comparator shell with iframes, inline JSON spec, `x-fuente`.
- `siniestros-gateway-swagger`: the richest description (tables, curl); worth imitating in `info.description`.

## Validation (validate_api.py)

Runs core `validate.py --kind api` on `index.html`, then: A1 spec valid (`openapi-spec-validator` if installed, otherwise
minimal structure and it says so) · A2 `$ref`s resolve · A3 examples present · A4 no JWT/keys/ARNs/tokens · A5 local pinned
Swagger, no floating CDN · A6 fixed options · A7 computed color of `.info .title` = `rgb(5, 48, 87)` (headless chromium;
CSS-only if no browser) · A8 renders operations, no script errors, no horizontal overflow · A9 folder weight.
Results: [references/validation-baseline.md](references/validation-baseline.md). Example: `examples/orders-api`
(current) and `examples/orders-api-compare` (comparator), both "Illustrative".
