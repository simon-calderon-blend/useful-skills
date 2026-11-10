# blend-api-spec

Created 2026-11-10 from the analysis of the 6 Swagger shares (`informe-dashboard-api.md`, section API). Local only, not
published. Base: [`../blend-web-core`](../blend-web-core/README.md) (tokens, logo, validator).

## Decisions taken

- Swagger UI `5.34.1` vendored in `assets/vendor/` (bundle + css, 1.8 MB, Apache-2.0 with LICENSE and NOTICE). The standalone
  preset and source maps are left out because the topbar is not used. `fetch_swagger.sh` refreshes it from npm.
- The spec is embedded in the page and also written as `openapi.json`, so `file://` works and the user can download it.
- Core `validate.py` runs on `index.html` only; vendor css is third party and would swamp the palette check.
- Navy title uses a literal `#053057` in the theme, as the brief and the computed-color check require.

## RESOLVED (user decisions, 2026-11-10; see the core README)

- Dark mode: stays optional. `--dark` adds `tokens-dark.css`, the core light/dark toggle in the header (also in the comparator shell, which mirrors the choice into its two iframes) and `blend-swagger-dark.css` (dark overrides for Swagger, including the POST chip).
- PP Telegraf: embedded in every page (index, `actual.html`, `propuesta.html`) through `blend_web.font_face()` from the core; a probe in headless chromium found Swagger text computed as PP Telegraf (code stays monospace). License not independently verified; the user authorized bundling it.
- Logo: core `logo.svg` (the one of almost all shares). State colors ok/warn/bad: accepted as derived from the Design System; the amber banner `#FBF1E0` comes from `--state-warn`.

## PENDIENTE (still open, specific to this skill)

| Item | What this skill does meanwhile | How to reverse |
|---|---|---|
| Method chip colors `#0E6BA8` / `#B5290F` | Taken from the dashboard proposal, not from official brand colors | edit `blend-swagger-theme.css` `:root` |
| Redistributing Swagger UI inside shares | Apache-2.0 permits it; LICENSE and NOTICE travel in `vendor/` | none |

## Known limits

- `openapi-spec-validator` is not installed here: A1 did not run full schema validation on the examples (WARN).
- The chrome-devtools MCP browser was locked by another session; renders were checked with headless chromium CLI.
  Screenshots at 1280 and 390 px and the comparator at 1280 were viewed; the comparator at 390 was not reviewed in
  detail. Dark (single page and comparator) was reviewed at 1280 px with `data-theme="dark"` forced in a copy; the POST chip was fixed (outlined soft cyan). The toggle click itself and the iframe mirroring were not exercised in a browser.
- Comparator iframes have a fixed height with internal scroll; deep links apply inside each iframe, not to the shell.
- Canon baseline is partial: the two reference shares' bundles and `openapi.json` were not downloaded (see baseline).
- Only JSON specs without PyYAML; `$ref` check covers local refs only (external refs count as failures).
- No diff highlighting between current and proposed (the reference share has a diffbox); only side-by-side.
- Try it out is always off, so this skill cannot be used for public sandbox APIs.
