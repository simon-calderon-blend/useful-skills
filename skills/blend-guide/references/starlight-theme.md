# Recreating the Blend theme in a new Starlight project

Source: built CSS of `ds-best-practices` (`_astro/common.CgUl-Mqs.css`, 66 KB; byte-identical across `ai-eng-best-practices` and `ds-onboarding` per the analysis). The build is Starlight 0.40.0 / Astro 6.4.5 (`<meta name="generator">`). Only the Blend layer was extracted: the rest is Starlight's own default CSS. The result is `assets/starlight/src/styles/blend-theme.css`. Nothing here was installed or built.

## What the Blend layer consists of

1. Five brand variables: `--blend-neon #00eded`, `--blend-washed-blue #053057`, `--blend-light-turquoise #a2f3f3`, `--blend-off-white #f4f3f0`, `--blend-cool-gray #314550`.
2. `--sl-font: "PP Telegraf", system-ui, ...`. The theme bundles `PPTelegraf-Regular.otf` (`assets/starlight/src/assets/fonts/`, copied from `blend-web-core/assets/fonts`) through an `@font-face` with a relative `url()`, so Vite adds the Astro `base`. No Google Fonts link. Decided 2026-11-10 by the user; license not independently verified, the user authorized bundling it.
3. Dark palette (Starlight default theme): accent `#00c6c6`, accent-low `#053057`, accent-high `#a2f3f3`, page `#0b1620`, nav and sidebar `#081019`, hairline `#1b2a38`, blue-gray scale `#16222e ... #e4e9ef`, text `#f4f3f0`; links in content use neon.
4. Light palette: accent `#075089`, accent-low `#d6f7f7`, accent-high `#042038`, text `#0b0d0e`, page white, sidebar off-white, hairline `#e3e1da`.
5. Details: 2px neon bar on top of the header, pill hero button (neon on washed-blue text, hover light turquoise), neon `::selection`, tighter hero.
6. Theme selector Auto / Light / Dark: Starlight's own; Pagefind search in the header: built in. Both need no configuration.
7. Mermaid: the builds ship `<pre class="mermaid">` plus mermaid chunks rendered in the browser. The integration is not identifiable from a build; `astro-mermaid` is a guess that produces the same markup (pin the version when installing).
8. Not in the theme (project specific): the harness picker of `ai-eng-best-practices` (`data-harness` + localStorage) and the extra `custom.css` of `blendx-living-docs`.

## Commands (not run by the skill)

```bash
npm create astro@latest my-guide -- --template starlight --no-install   # or copy assets/starlight/ as the base
cd my-guide
npm install @astrojs/starlight@0.40.0 astro@6.4.8 astro-mermaid@2.2.0 mermaid@12.3.0   # pinned: these resolved and built on 2026-11-10
cp <skill>/assets/starlight/src/styles/blend-theme.css src/styles/
cp -r <skill>/assets/starlight/src/assets src/ ;   # includes src/assets/fonts/PPTelegraf-Regular.otf
 cp <skill>/assets/starlight/public/favicon.svg public/
# merge <skill>/assets/starlight/astro.config.mjs (customCss, mermaid, base); sidebar: with Starlight >= 0.39 a labeled
# group uses items: [{ autogenerate: { directory } }], not autogenerate next to label
cp <skill>/assets/starlight/src/content.config.ts src/   # required by Astro 6
cp -r <skill>/assets/starlight/src/content/docs/* src/content/docs/   # the example pages the sidebar points to
npm run dev        # preview
npm run build      # writes dist/ and the Pagefind index (dist/pagefind/)
```

Publish `dist/` as the share; `base` in `astro.config.mjs` must equal the share path (`/<slug>`) because assets are absolute. Check with `python3 scripts/validate_guide.py dist --kind guide` (expect the core FAILs for weight/logo described in `validation-baseline.md`) and `python3 scripts/validate_guide.py <project> ` (source check: theme tokens and `customCss`).

## Reconciliation with blend-web-core `assets/tokens.css`

| Value | Starlight builds | blend-web-core | Same? |
|---|---|---|---|
| cyan | `--blend-neon #00eded` | `--blend-cyan #00EDED` | yes (alias added in blend-theme.css) |
| navy | `--blend-washed-blue #053057` | `--blend-navy #053057` | yes |
| soft cyan | `--blend-light-turquoise #a2f3f3` | `--blend-cyan-soft #A2F3F3` | yes |
| paper | `--blend-off-white #f4f3f0` | `--blend-paper #F4F3F0` | yes |
| slate | `--blend-cool-gray #314550` | `--blend-slate #314550` | yes |
| accent on light | `--sl-color-accent #075089` | `--blend-link #075089` | yes |
| accent on dark | `--sl-color-accent #00c6c6` | `--blend-link-dark #00C6C6` | yes |
| dark page | `#0b1620` (nav `#081019`) | `tokens-dark.css` uses `--blend-black #0B0D0E` | **no**: Starlight dark is blue-tinted |
| dark gray scale | `#16222e ... #e4e9ef` | none | only in Starlight |
| light accent-low / hairline | `#d6f7f7` / `#e3e1da` | none | only in Starlight |
| state colors | Starlight defaults (hsl) | `--state-ok/warn/bad` | RESOLVED 2026-11-10: ok/warn/bad accepted as derived from the Design System (no official guide); Starlight keeps its defaults |

Variable names differ but the values are the same, so a page in one family can reuse the other's palette. Only dark page background differs; in a single HTML guide with `--dark` the core tokens apply, in Starlight the blue-tinted dark stays (native, kept as in the reference builds). Dark mode stays optional (decision 2026-11-10).

## Inconsistency to note

`blendx-living-docs` is Starlight with the default Starlight blue (hsl 224/234) as a base layer and a second `custom.css` on top (accent `00eded`, background `0b0d0e`, JetBrains Mono, dark-first). It is a variant, not the family-A theme; do not copy it.
