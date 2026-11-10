---
name: blend-web-core
description: Shared Blend360 design system for web documents (self-contained HTML for Blend Share). Provides the design tokens (navy 053057, cyan 00EDED, paper F4F3F0, PP Telegraf with Montserrat fallback), the Blend logo, base components (header, hero, KPI tiles, cards, callouts, chips, tables), optional dark theme, recipes for demos and mockups, and validate.py, which checks a page against the Blend design. Use when building or checking any Blend HTML page, or as the base that the other blend-* web skills rely on. For Word files use blend-documents instead.
---

# Blend web core

Base layer for every Blend web document. The type-specific skills (blend-presentations, blend-dashboard,
blend-api-spec, blend-report, blend-guide, blend-editorial, blend-portal) build on this one.

## Quick start

```bash
python3 scripts/blend_web.py body.html out/index.html --title "Title" --lang es [--dark]
python3 scripts/validate.py out/index.html --kind article
```

`blend_web.py` wraps a body fragment with `assets/tokens.css`, `assets/components.css`, the inline logo and
PP Telegraf (bundled in `assets/fonts`, embedded as base64, +61 KB). `--font none` skips it and loads Montserrat from Google
Fonts instead. `--dark` also adds the dark tokens and a light/dark toggle that remembers the choice. Use the `b-*`
classes from `components.css` in the body.

## Rules

- **Navy is `#053057` on the web.** `#003059` belongs to the Word skill only; never use it in HTML.
- Palette: navy `053057`, cyan `00EDED`, soft cyan `A2F3F3`, paper `F4F3F0`, slate `314550`, ink `1A1A1A`,
  black `0B0D0E`, white. Pink `FF2D9B` is a rare accent for decks. Derived tokens (teal, link, states) are in
  `assets/tokens.css` with their source.
- **Cyan and soft cyan are never text on a light background** (1.5:1). On navy or black they are fine.
- Type: `font-family: 'PP Telegraf','Montserrat',system-ui,...`, weight 400 only. PP Telegraf Regular is bundled
  with this skill and embedded by default (license not independently verified; the user authorized bundling it).
- Logo: always the inline SVG in `assets/logo.svg` (viewBox 572x110, `fill=currentColor`); letters navy on
  light, white on dark. Do not redraw it.
- Real content only. Illustrative data is labeled "Illustrative". Client or ADRES material is internal: no
  real data, secrets or ARNs in a page.
- Self-contained HTML. External resources only: Google Fonts, and cdnjs with an exact version in the path.
- Dark mode is optional and off by default. See [references/tokens.md](references/tokens.md).

## Workflow

1. Pick the type skill if one fits; otherwise build from this core.
2. Build with `blend_web.py` or by hand using `tokens.css`.
3. Run `validate.py --kind <type>`; fix every FAIL, read every WARN.
4. Look at the page at 1280 and 390 px (chrome-devtools screenshots, or `--render` if Playwright is installed).

## validate.py (10 checks)

1 palette (forbidden hex fail, off-palette warn) · 2 font stack · 3 lang/title/viewport/h1 (meta description is a warn) · 4 logo ·
5 contrast and cyan text · 6 external resources and local refs · 7 dark (both `prefers-color-scheme` and
`[data-theme]` or neither) · 8 weight per `--kind` · 9 render at 1280/390 px (`--render`, otherwise SKIP) ·
10 secrets and e-mails. `--strict` turns WARN into failure. `--json` for machine output.
Results against the canonical shares: [references/validation-baseline.md](references/validation-baseline.md).

## Reference

- [references/tokens.md](references/tokens.md): token table, dark theme, what is derived versus canon.
- [references/demo-recipes.md](references/demo-recipes.md): the nine demos as recipes (mockup, guided demo, scoring tool).
- [README.md](README.md): sources and decisions.
- Word documents: `blend-documents` (`references/brand.md`, `references/charts.md` for palette and chart rules).
