# blend-editorial

Article and commercial pages on top of `../blend-web-core`. Created 2026-11-10. Local only, not published.

## RESUELTO (user decisions, 2026-11-10; the core README governs)

- Dark mode stays OPTIONAL: `--dark` adds the core tokens-dark, the toggle (bottom-left, fixed) and `assets/editorial-dark.css`, which makes topbar, logo, nav, labels, pull quote and step cards follow the dark tokens (hero/CTA stay navy in both themes; the diagram sits on a white tile). Without `--dark` that file is not included.
- PP Telegraf embedded by default (+61 KB; `font="none"` for Montserrat). Packaging authorized by the user; license not verified independently. The example article SVG now lists PP Telegraf first.
- Logo: the one in `blend-web-core/assets/logo.svg`. Status colors: accepted as derived from the Design System.

## PENDIENTE (specific to this skill)

| Item | What this skill does meanwhile | How to reverse |
|---|---|---|
| Client logo permission | the generator accepts any logo file; it cannot verify permission. Placeholder only in the repo | keep real logos out of git |
| Hero width | hero content aligned to the 1080px section bleed, not the 900px of the canon | `--e-hero` in editorial.css |

## Known limits

- Playwright is not installed: E8 and core check 9 report SKIP. 375 px was measured with chrome-devtools (article, one-pager, landing: scrollWidth 375 = innerWidth). 1280 and 390/375 px were looked at for article and one-pager; the landing was only measured at 375 px, not screenshotted.
- One-pager page count is only the number of `.e-sheet` blocks; real print overflow was NOT verified (no PDF render done). Sheets use `overflow: hidden`, so excess content would be clipped in print.
- No tabs, accordions, sidebars, progress bars, interactive modules or video: add by hand if needed. Case study, proposal and deliverables preview use the landing build; no dedicated templates.
- E1 is a CSS heuristic (selectors with prose/article/content/... or a `p` rule). Canon `synthetic-studio-engagement-model` fails E1/E2/E3/E5 (13.5px body, 1.5 line-height, no CTA button class); that is a real deviation, kept.
- E7 checks structure, not whether the logo is real or allowed.
