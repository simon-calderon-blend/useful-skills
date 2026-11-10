# blend-guide

Guides, documentation and courses for Blend Share, on top of `blend-web-core`. Created 2026-11-10; local only, not published.

## Layout

- `SKILL.md`: how to use it. `scripts/build_guide.py`: JSON to single HTML. `scripts/validate_guide.py`: validator.
- `assets/guide.css|guide.js|theme.js`: single-HTML layout and behaviour. `assets/starlight/`: theme, config, package.json, symbol logos, favicon, minimal `index.mdx`.
- `examples/guide` and `examples/course` (built from the JSON files next to them, content "Illustrative").
- `references/starlight-theme.md`, `references/references.md`, `references/validation-baseline.md`.

## RESOLVED (user decisions, 2026-11-10)

- Dark mode: stays optional. Single HTML: off by default; `--dark` adds tokens-dark.css and the guide's own `g-theme` toggle (the core does not add a second button because the body already has a `theme` button; stored in localStorage with try/catch). Starlight: native Auto/Light/Dark.
- PP Telegraf: bundled. Single HTML inherits the core embedding (base64); the Starlight project carries `src/assets/fonts/PPTelegraf-Regular.otf` and an `@font-face` in `blend-theme.css`. License not independently verified; the user authorized bundling it.
- Logo: the one used by almost all shares (`blend-web-core/assets/logo.svg`). State colors ok/warn/bad: accepted as derived from the Design System (no official guide).

## PENDIENTE (still open, specific to this skill)

| Item | What this skill does meanwhile | How to reverse |
|---|---|---|
| Starlight dark page colour | keeps the reference blue-tinted `#0b1620`, which differs from core `#0B0D0E` | align both once the canon decides |
| Mermaid integration | `astro-mermaid` 2.2.0 + `mermaid` 12.3.0, built and rendered (the reference builds do not reveal their package) | swap in `astro.config.mjs` |
| Quiz scoring | a module is "done" when its quizzes are answered correctly; no score, no pass mark | edit `modDone` in `guide.js` |

## Known limits

- Starlight starter: `npm install` and `astro build` ran on a copy (4 pages, Pagefind indexed, mermaid rendered) with astro 6.4.8, starlight 0.40.0, astro-mermaid 2.2.0, mermaid 12.3.0, all pinned. Fixed on the way: labeled `autogenerate` group, missing `src/content.config.ts`, missing example pages. npm skipped esbuild's postinstall (allowScripts warning) and the build still worked.
- The validator on a built Starlight site fails the core weight, logo and base-path-resource checks (expected, see the baseline); its own G-checks pass. `validate.py` check 9 needs Playwright (SKIP).
- Visual review: the course (built `--dark`, forced `data-theme="dark"` in a copy) and the guide were looked at in headless chromium at 1280 px on 2026-11-10: PP Telegraf renders, one theme button (`g-theme`, the core adds none), dark readable. 390 px was reviewed earlier with chrome-devtools, not after the font change. Wide tables scroll horizontally inside their wrapper at 390 px.
- The Starlight `@font-face` (relative `url()` to `src/assets/fonts`) was not built: whether Vite emits it under `/<slug>/` is untested. The core's `theme-toggle.js` is also inlined in `--dark` pages although the guide has its own button (harmless: different localStorage key).
- No syntax highlighting in single-HTML code blocks (plain text with a language label). Course progress is per browser, not shared.
- G3 accepts any `nav` with a TOC-like label or class, so it can pass a TOC that is not about the page; G2 treats links to other shares (`/slug`) as unresolved in a standalone file.
- The Starlight course mode is only a pointer (content tree as modules plus `.blend-quiz` styles); there is no ready-made quiz component for Starlight.
