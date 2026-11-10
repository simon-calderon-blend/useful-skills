# blend-presentations

Deck generator and validator for Blend HTML presentations. Spec: `SKILL.md`. Layout: `assets/` (deck.css,
deck.js), `scripts/` (build_deck.py, validate_presentation.py), `examples/` (deck.json and generated index.html,
all "Illustrative"), `references/` (film-canvas.md, validation-baseline.md).

## RESUELTO (user decisions, 2026-11-10; the core README governs)

- Dark mode: stays OPTIONAL. `--dark` adds `tokens-dark.css` and the core light/dark toggle (`data-theme-toggle`, localStorage with try/catch). In decks the toggle sits top-left (`deck.css`, `.b-theme-fixed`) so it never covers the prev button, the counter or the notes button; the HUD turns paper-colored in dark.
- PP Telegraf: embedded by default by `blend_web.build` (base64, +61 KB; `font="none"` goes back to Montserrat via Google Fonts). Packaging authorized by the user; license not verified independently.
- Logo: the one in `blend-web-core/assets/logo.svg` (the one in almost all shares).
- ok/warn/bad state colors: accepted as derived from the Design System (no official guide exists).

## PENDIENTE (specific to this skill)

- Print: `@page` is fixed at 1280x720 px; not tested in a real print dialog or PDF export.

## Límites conocidos

- Only 5 slide types (cover, section, content with bullets/KPIs, quote, closing). No comparison, table, SVG diagram or image slides yet; hand-edit HTML for those.
- Film canvas variant is documented, not generated.
- Overflow check (E4) uses headless chromium with a probe; on canon decks with scaled stages it may over-report. It needs `chromium` or Chrome on PATH, otherwise WARN.
- `validate_presentation.py` reads literal strings (e.g. `'Home'`), so an equivalent implementation (key codes) would fail E1.
- Canon baseline: ai-evaluation-workshop and knowledge-work-transformation both FAIL several checks (see baseline); not loosened.
- Mobile (<640 px) slides scroll vertically when content is long; the deck itself never scrolls horizontally.
