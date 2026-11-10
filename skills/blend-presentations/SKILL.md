---
name: blend-presentations
description: Builds Blend360-branded HTML slide decks as one self-contained index.html (DOM deck with keyboard, hash routing, touch, n/N counter, speaker notes, print), on the blend-web-core design system, with optional client co-branding via --client-* variables, and validates them. Use when the user asks for a Blend presentation, deck, slides, workshop or kickoff deck for Blend Share, or wants an existing HTML deck checked against the Blend design.
---

# blend-presentations

Generates a Blend deck from a JSON spec and validates it. Builds on `../blend-web-core` (tokens, components,
logo, `blend_web.build`, `validate.py`); it does not copy them.

## Ask the user for

Title and subtitle, author, date, language (`lang`), theme (light slides with navy cover/section/closing by
default; `--dark` only if asked), content per slide, client (only if co-branding is wanted), whether speaker
notes are needed. Mark any invented figure `"illustrative": true`. No real client or ADRES data.

## Flow

1. Write a spec (see `examples/deck.json`): `slides[]` with `type` = `cover | section | content | quote | closing`.
   Content slides take `eyebrow`, `title`, `points[]`, `kpis[{value,label}]`; every slide takes `notes`.
2. `python3 scripts/build_deck.py spec.json out/index.html [--dark]`
3. `python3 scripts/validate_presentation.py out/index.html` (fix every FAIL, read every WARN).
4. Look at it at 1280x720 and 390x844 (chrome-devtools, or headless chromium `--screenshot`).

## What the deck gives

- DOM variant (default): `.slide` elements, one `.active`. Keys: arrows, Space, PageUp/Down, Home/End,
  `N` notes, `F` fullscreen, `Esc`. Hash routing `#n`, touch swipe, `n / N` counter (`aria-live`), progress bar,
  logo fixed top-right (white on navy slides), `prefers-reduced-motion`, `@media print` (one slide per 16:9 page).
- Co-branding: spec `client: {name, accent}` emits `--client-name` / `--client-accent` and a "Prepared for"
  chip on the cover. Client colors never replace Blend tokens; use only the `--client-*` namespace.
- Film variant (canvas 1920x1080): documented only, see [references/film-canvas.md](references/film-canvas.md).
- Tokens/components used: `--blend-*` and `.b-eyebrow`, `.b-card`, `.b-kpi` from core; deck layout in
  `assets/deck.css`, runtime in `assets/deck.js` (both inlined by the builder). Cyan is text only on navy slides.

## Reference shares (structure only)

Read from `blend-share-files/<slug>/index.html`; never `cat` them (base64 fonts), use `grep -o`/`cut`.
- `ai-evaluation-workshop`: brand tokens, embedded PP Telegraf, full keyboard, notes, aria.
- `knowledge-work-transformation`: inline official logo, cover, nav dots, compact (60 KB).
- `blend-spark-harness-engineering`: contrast roles per color, stage layout, notes.

## Validation

`validate_presentation.py` runs core `validate.py --kind presentation`, then E1 keydown (arrows, Home/End),
hashchange, touch, reduced-motion, `@media print`; E2 unique hex <= 20; E3 no forbidden hex; E4 no overflow
per slide at 1280x720 (headless chromium; WARN if none); E5 title/lang/aria/aria-live; E6 slides and counter.
Results incl. canon: [references/validation-baseline.md](references/validation-baseline.md). See README.md for limits.
