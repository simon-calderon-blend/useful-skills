# Design principles

How a Blend page is composed. The brand fixes the logo, palette, typeface (PP Telegraf 400) and tone;
everything here is about what you do with them. Tokens named below live in `assets/tokens.css`.

## 1. Know what the page is for

| Mode | Blend artifacts | The reader must | The brand owns |
|---|---|---|---|
| Read | report, guide, article | understand and find their place | the frame: masthead, summary band, section openers, how tables, code and callouts are set. The reading column stays calm |
| Operate | dashboard, portal, API reference | finish a task | type, palette, density. Never the position of navigation, filters or controls |
| Persuade | landing, one-pager | decide and act | the whole page: one promise, proof, one action |

Read and Operate pages are predictable on purpose: fixed type sizes, stable density, standard controls.
Asymmetry and display-size type belong to Persuade only.

## 2. Layout

- **One left line.** Header, every section and footer share one container (`--w-page`, or `--w-wide` for
  dashboards, the API reference and sidebar layouts) and one gutter (`--gutter`). Prose keeps `--measure`
  inside it; tables, figures and grids use the full width.
- **Squint test.** Blur the page: one primary element, two or three secondary, the rest quiet. If two things
  compete at the same size, one of them is wrong.
- **A section needs mass.** A heading and one paragraph is not a section. Give it a figure, a table, three or
  more rows, a working control, or fold it into the section above.
- **Vary the skeleton.** Never more than two neighbouring sections with the same build (heading, then a row of
  cards). After a dense block (table, grid, findings) comes a quiet one.
- **No dead space.** No half-empty screen under the content, no single card stranded on the last grid row. A
  grid with 3 items is 3 across, not 2 + 1; 5 items is a lead item plus four, or a list.
- **Separation ladder.** Use the lowest rung that works: space, then a 1px hairline, then a tinted well
  (`.b-well`, no border), then a card (`.b-card`). Never a card inside a card or a bordered box inside a well.
- **First screen.** Read: where am I (logo, document type), the title, the answer (verdict or lede), the way
  forward (contents). Operate: the control and the data it scopes. Persuade: the promise, one proof, the action.

## 3. Spacing

- Only the scale: `--s-1` to `--s-9` (4, 8, 12, 16, 24, 32, 48, 64, 96 px). A value that is not on it is a bug.
- Rhythm is contrast: tight inside a group (`--s-1` to `--s-3`), generous between groups (`--s-6` and up). The
  same gap everywhere reads as a list of equals.
- A heading belongs to what follows: about twice the space above it as below.
- Siblings are spaced with `gap`, not with margins on the children. Grid and flex children get `min-width: 0`.

## 4. Type

- Weight is always 400, so hierarchy comes from **size, space and colour** (navy headings, ink body, slate
  secondary). `<strong>` is set in navy at 400 by the core, and `font-synthesis: none` stops the browser faking a bold.
- Roles, ratio 1.2: `--t-micro` 12 · `--t-small` 14 · `--t-body` 16 · `--t-lead` 19 · `--t-h2` 28 · `--t-h1` 40 ·
  `--t-figure` 33 · `--t-display` (fluid, Persuade only). One size per role across the page. Nothing below 12px;
  running text never below 16px.
- Measure 45 to 75 characters for prose. `--measure` is 48ch because `ch` is the width of the 0, and the 0 of PP
  Telegraf is 1.5 times its average letter: 48ch is about 72 characters, 68ch would be 104. Never copy a `ch` value
  from another typeface. Headings are capped in `ch` too (h1 24, h2 32, h3 44).
  Line-height falls as size grows: 1.65 body, 1.3 lead, 1.15 headings.
- `text-wrap: balance` on headings and `pretty` on body are set by the core. Check that no heading ends on a
  one-word line at 390px.
- Numbers use tabular figures (`.b-num`, set already on KPI values and `td.num`). A number never breaks from
  its unit: use a non-breaking space.
- **One eyebrow per page** (`.b-eyebrow`, in the masthead or hero). All other small labels are `.b-label`:
  sentence case, no letter-spacing. Monospace is for code, identifiers and parameters only.

## 5. Colour

- The palette is fixed; what you decide is the dose. Paper and white carry the page, ink and navy carry the
  text. **Navy commits by region** (hero, summary band, table head, closing band), not as scattered accents.
- **Cyan is a signal, not a fill**: the primary action, the current selection, one rule in the masthead, the
  figure that argues, and text on navy. If more than a few elements on a screen are cyan, none of them is.
- **One filled button per view** (`.b-btn`). Other actions are `.b-btn.secondary` or links.
- On navy, secondary text is soft cyan (`--blend-cyan-soft`), never grey and never white at reduced opacity.
- State colours (`--state-*`) mean state and nothing else, and never work alone: every status is a word plus a
  dot or border. They are not small-text colours on light (warn is 4.1:1 on white).
- No gradients, glows, glass or blurred backgrounds. No pure decoration behind text.

## 6. States and interaction

- Every control has rest, hover, focus-visible, active and disabled. The core gives these to `.b-btn` and
  `button.b-chip`; any new control must define all five.
- Hover is one signal, inside `@media (hover: hover)`, and never the only way to reach something. Elements that
  do nothing do not react.
- Focus is a 2px outline, instant. On navy set `--focus: var(--blend-cyan)` (done for `.b-hero`, `.b-band`).
- Hit targets are 44px (`--tap`) on touch. Button and navigation labels never wrap.
- A data region has four states: loading, empty (what happened, why, one way out), error, full. Write the
  empty state; never show a blank frame.
- Feedback stays where the action happened: Copy becomes "Copied" for two seconds. No toasts.
- Core content is in the HTML and readable without JavaScript.

## 7. Motion

- Three durations and one curve: `--dur-1` press, `--dur-2` hover and indicators, `--dur-3` panels and progress,
  all on `--ease`. No bounce.
- Animate `transform`, `opacity` and colour only. Never `transition: all`, never width, height, margin or top.
- Scrolling moves nothing: no reveal on scroll, no parallax, no count-up. The final number is in the HTML.
- Under `prefers-reduced-motion` movement stops and colour changes stay (the core does this).

## 8. Data

- **Choose the form from the data.** One value: a figure with its qualifier. Two to five values: a figure row or
  horizontal bars. A trend: a line. More than seven categories: a table. Parts of a whole: a stacked bar.
  Never a pie, donut or gauge.
- **Every figure says what it counts**: unit in the value, the thing counted in the label, a target, baseline
  or period in the caption. No trend arrow nobody measured. A KPI row must not repeat the table under it.
- KPI figures sit in a row parted by hairlines (`.b-kpis` with plain `.b-kpi`), not in identical cards.
- Charts: zero baseline for bars, 3 to 5 gridlines, one y axis, flat marks, one series emphasised. Text never
  takes a series colour: put a swatch beside the label. Series palette: `blend-dashboard`.
- Tables: navy head that does not wrap, horizontal rules only, numbers right-aligned, the first column names the
  row. On a phone keep the naming column in view (restack or scroll inside `.b-table-wrap`), never the page.
- One claim per table or figure, with a caption that states it. Sample data is labelled "Illustrative".

## 9. Words on the page

Tone belongs to the brand; these are mechanics.

- A heading says what the reader gets ("Accuracy by ticket category"), not the kind of block ("Table", "Data",
  "Overview").
- A button is a verb plus its object ("Export CSV", "Open the guide"). Never "Open", "Learn more", "Click here".
  One wording per action across the page.
- Each fact appears once, in one wording. Link text makes sense out of context.
- Empty and error text names the real situation and the next step.

Anti-patterns to check against: [anti-patterns.md](anti-patterns.md). Before delivery:
[delivery-checklist.md](delivery-checklist.md).
