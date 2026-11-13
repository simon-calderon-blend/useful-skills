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

## Layout, type and motion tokens (not brand)

Added 2026-11-13. They carry no colour or typeface, so they do not change the brand; they make every skill use
the same rhythm. Rules for using them: [design-principles.md](design-principles.md).

| Group | Tokens | Values |
|---|---|---|
| Measure | `--measure` | 48ch (was 68ch; measured at 104 characters per line in PP Telegraf, now about 72) |
| Spacing | `--s-1` … `--s-9` | 4, 8, 12, 16, 24, 32, 48, 64, 96 px |
| Widths | `--w-page`, `--w-wide`, `--gutter` | 72rem, 80rem, `clamp(1rem, 4vw, 2.5rem)` |
| Type roles | `--t-micro`, `--t-small`, `--t-body`, `--t-lead`, `--t-h2`, `--t-h1`, `--t-figure`, `--t-display` | 12, 14, 16, 19, 28, 40, 33 px; display is fluid 35 to 58 px |
| Motion | `--dur-1`, `--dur-2`, `--dur-3`, `--ease` | 120, 220, 420 ms; `cubic-bezier(.2,.8,.2,1)` |
| Controls | `--tap`, `--radius-sm`, `--focus` | 44px, 6px, `--accent` (cyan inside navy regions) |
| Tints | `--tint-note`, `--tint-key`, `--tint-ok`, `--tint-warn`, `--tint-bad`, `--tint-info` | `color-mix()` of a brand or state token into `--surface`; no new hex |

## Contrast (computed, WCAG)

Navy on paper 11.6:1, ink on paper 15.9:1, slate on paper 8.9:1, white on navy 13.4:1, cyan on navy 8.8:1,
cyan on white 1.5:1 (never as text).
State colours as text: ok 5.5:1 on white, info 7.9:1, bad 4.9:1 on white but 4.5:1 on paper, warn 4.1:1 on white and
3.7:1 on paper. So chips set the status word in ink and use the state colour for the dot and border.

## Dark theme (optional)

Only `blenda-and-critical-7` (`.dark`) and four dashboards (`prefers-color-scheme` + `[data-theme]`) implement
dark; the Starlight sites have their own. Decision (2026-11-10): dark stays optional, never the default. To build
with it: `blend_web.py --dark` (or `build(..., dark=True)`), which adds `tokens-dark.css`, follows
`prefers-color-scheme` and adds a toggle (`data-theme-toggle`) that remembers the choice in localStorage (guarded).
A page that brings its own theme button is not given a second one. Provide both selectors or neither (check 7).

## What is not here

- `#003059`, `#304550`, `#F3F3F0` (docx values), `#1DF4F4`, `#00ECEC`, `#0B1E3D`, `#00D4C8`: forbidden in web.
- `#0E2841` and sky `#28B5E8` belong to the Design System content slides; use them only in an explicit product theme.
