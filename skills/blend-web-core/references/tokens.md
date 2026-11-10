# Tokens

Defined in `assets/tokens.css` (light, default) and `assets/tokens-dark.css` (optional dark).

## Palette

| Token | Hex | Use | Source |
|---|---|---|---|
| `--blend-navy` | 053057 | headings, brand surfaces, table headers | canon decks/portals; Design System `colors.css` |
| `--blend-cyan` | 00EDED | fills, rules, CTA, text on navy/black only | canon |
| `--blend-cyan-soft` | A2F3F3 | tints, highlights on dark | canon |
| `--blend-paper` | F4F3F0 | page background | canon |
| `--blend-slate` | 314550 | secondary text | canon |
| `--blend-ink` / `--blend-black` | 1A1A1A / 0B0D0E | body text / dark background | canon |
| `--blend-pink` | FF2D9B | rare accent, decks | knowledge-work-transformation |
| `--blend-teal`, `--state-ok` | 007676 | ok state, accessible teal text | Design System |
| `--state-warn` | B86A12 | warn | Design System `orange-700` |
| `--state-bad` | C8412B | bad | Design System `red-600` |
| `--state-info` | 11567F | info | Design System `blue-700` |
| `--blend-link` / `--blend-link-dark` | 075089 / 00C6C6 | accent on light / dark | Starlight `common.css` |

No share defines an ok/warn/bad palette of its own; the states above come from the Design System bundle and
are the only derived values. Accepted 2026-11-10: there is no official guide for state colors.

## Contrast (computed, WCAG)

Navy on paper 11.6:1, ink on paper 15.9:1, slate on paper 8.9:1, white on navy 13.4:1, cyan on navy 8.8:1,
cyan on white 1.5:1 (never as text).

## Dark theme (optional)

Only `blenda-and-critical-7` (`.dark`) and four dashboards (`prefers-color-scheme` + `[data-theme]`) implement
dark; the Starlight sites have their own. Decision (2026-11-10): dark stays optional, never the default. To build
with it: `blend_web.py --dark` (or `build(..., dark=True)`), which adds `tokens-dark.css`, follows
`prefers-color-scheme` and adds a toggle (`data-theme-toggle`) that remembers the choice in localStorage (guarded).
A page that brings its own theme button is not given a second one. Provide both selectors or neither (check 7).

## What is not here

- `#003059`, `#304550`, `#F3F3F0` (docx values), `#1DF4F4`, `#00ECEC`, `#0B1E3D`, `#00D4C8`: forbidden in web.
- `#0E2841` and sky `#28B5E8` belong to the Design System content slides; use them only in an explicit product theme.
