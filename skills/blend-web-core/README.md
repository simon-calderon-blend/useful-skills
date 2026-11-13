# blend-web-core

Shared base for the Blend web skills. Created 2026-11-10 from the analysis of 106 Blend Shares
(`/home/simoncl20/Work/blend/bld/blend-share-files/analisis-tipos-documento/`). Local only, not published.

## Decisions taken

- Navy for web is `#053057`. `#003059` stays documented for Word only (`blend-documents`, untouched).
- Palette tokens, logo geometry and the component set come from the canonical shares
  (`ai-evaluation-workshop`, `knowledge-work-transformation`, `blend-spark-harness-engineering`, `blend-events`,
  `persona-grounding-experiment`) and the Design System bundle in `blend-brb-screen/_ds/`.
- Demos have no skill of their own: recipes in `references/demo-recipes.md`.

## Decisions on the former PENDIENTE items (user, 2026-11-10)

| Item | Decision | Where |
|---|---|---|
| Dark mode | Optional, never the default. The core can build dark artifacts: `--dark` adds `tokens-dark.css` and a persistent light/dark toggle | `assets/tokens-dark.css`, `assets/theme-toggle.{css,js}`, `blend_web.build(dark=True)` |
| PP Telegraf | Bundled in the skill and embedded by default (base64, +61 KB). `--font none` falls back to Montserrat via Google Fonts. The user authorized bundling; I did not verify the license independently. Source file is the same OTF distributed by the `blend-branding` skill in the marketplace share | `assets/fonts/PPTelegraf-Regular.otf` |
| Logo | The variant in almost all shares (geometry common to them; letters `currentColor`: navy on light, white on dark). Its path numbers differ slightly from the `blend-logo.svg` in the marketplace `blend-branding` skill (another export); not compared visually | `assets/logo.svg` |
| ok/warn/bad colors | Accepted as derived from the Design System bundle (`007676`, `B86A12`, `C8412B`): there is no official guide for state colors | `assets/tokens.css` |

## Design pass (2026-11-13)

The core and the six web skills were reworked against a distillation of three external design skills (their
principles rewritten for Blend; nothing is loaded from them at runtime). Brand tokens, logo and font are unchanged.

| Decision | Where |
|---|---|
| Additive layout tokens: spacing `--s-*`, widths `--w-*`, type roles `--t-*`, motion `--dur-*` / `--ease`, tints `--tint-*` (`color-mix()` of existing tokens, no new hex) | `assets/tokens.css`, `references/tokens.md` |
| One `.b-eyebrow` per page; other small labels are `.b-label` (sentence case) | `assets/components.css` |
| Callouts are tinted wells with a worded title; no coloured side stripe on cards, callouts or findings | `assets/components.css` |
| KPI figures are a hairline-parted row (`.b-kpi` without `.b-card`); `.b-card.b-kpi` still works for decks | `assets/components.css` |
| Status chips set the word in ink with a dot and border in the state colour: `--state-warn` and `--state-bad` do not reach 4.5:1 as small text on paper | `assets/components.css`, `references/tokens.md` |
| Buttons and filter chips have hover, focus-visible, active and disabled; `--focus` turns cyan inside navy regions | `assets/components.css` |
| Reduced motion keeps colour transitions and removes movement | `assets/components.css` |
| `validate.py` check 11 "craft": warnings only, own CSS only (vendored CSS is skipped) | `scripts/validate.py` |
| `blend_web.build()` adds a skip link when the body has `id="main"` | `scripts/blend_web.py` |

`blend-presentations` was not edited. It inherits the core, so a rebuilt deck picks up balanced heading wraps and the
new card padding; its committed example was not regenerated.

## Known limits

- `validate.py` check 9 needs Playwright (not installed here): without `--render` it reports SKIP.
- The contrast check on cyan text is a heuristic on CSS rules, not a rendered-pixel test.
- Validation baseline against the canonical shares: `references/validation-baseline.md`. The canon itself
  fails or warns on several checks (no meta description, `knowledge-work-transformation` uses system-ui,
  `blend-spark-harness-engineering` has no logo and falls back to the system font).
- Check 2 now passes only when PP Telegraf is embedded; canonical shares that declare it without embedding get a WARN.
- The dark toggle was tested for logic (click cycles dark/light, `aria-pressed`) and visually in headless Chromium for one page; not on every skill's output (see each skill's README).
