# Anti-patterns: generic generated design

Each of these makes a page look assembled rather than designed. The right column is what a Blend page does
instead. `validate.py` check 11 warns on the ones marked ✓.

## Structure

| Do not | Do instead |
|---|---|
| Hero, three equal cards, call to action, footer, whatever the content | Let the content pick the sections; each one has a different build |
| A grid of identical cards with an icon, a title and one line | A list with hairlines, a table, or cards only when each opens something |
| The same heading-plus-card-row skeleton in every section | At most two neighbours alike; follow a dense block with a quiet one |
| A card inside a card; a bordered table inside a bordered card ✓ | Space, hairline or `.b-well` for the inner level |
| A coloured stripe down the left edge of a card, callout or alert ✓ | Tinted well with a worded title; status as a chip |
| A strip of big numbers with no source or unit | A figure row where every number has a unit, a label and a qualifier |
| An eyebrow above every heading ✓ | One eyebrow per page; a heading that announces itself |
| 01 / 02 / 03 on things that have no order | Number only steps, report sections and anything people cite by number |
| A single card alone on the last row; a half-empty screen before the footer | Fit the column count to the item count; let short pages be short |
| Section dividers, a border and a shadow all on the same seam | One separation device per seam, the lightest that works |
| Modal, toast, chat bubble, back-to-top button | Inline disclosure and inline feedback |

## Type and colour

| Do not | Do instead |
|---|---|
| Small uppercase letter-spaced labels everywhere ✓ | `.b-label`, sentence case |
| Text below 12px; 14px grey paragraphs ✓ | 16px body in ink; 14px only for captions and meta |
| Bold for hierarchy | Size, space and navy/ink/slate (the brand face is 400 only) |
| Monospace to look technical | Mono for code, identifiers and parameters |
| Cyan on every chip, icon and border | Cyan for the primary action, the selection and the one figure that argues |
| Cyan or soft cyan as text on a light background | Navy or `--blend-link` on light; cyan text on navy only |
| Grey or half-opacity white text on navy | Soft cyan for secondary text on navy |
| Two filled buttons side by side; a filled button on every card | One `.b-btn` per view; the rest `.secondary` or links |
| Gradient text, gradient fills, glow shadows, frosted glass ✓ | Flat token colours; a shadow only on hover, with an offset |
| Colour as the only sign of status | A word, plus a dot or border in the state colour |
| Any hex that is not a token | Tokens, or `color-mix()` of tokens |

## Motion and interaction

| Do not | Do instead |
|---|---|
| `transition: all`; animating width, height or margin ✓ | `transform`, `opacity` and colour, on the motion tokens |
| Fade-and-rise on every section as you scroll; parallax; count-up numbers | Nothing moves on scroll; the page is complete at rest |
| Bounce or elastic easing | `--ease` |
| The same hover lift on every card; hover on things that are not links | One hover signal, only on what responds to a click |
| Controls with no focus ring, or a ring that fades in ✓ | The core `:focus-visible` outline |
| Carousels, auto-rotating tabs, pulsing dots | A static row or tabs the reader operates |
| Content hidden until a script runs | Everything in the HTML; scripts only enhance |

## Data

| Do not | Do instead |
|---|---|
| Pie, donut, gauge, 3D, dual axis | Bars, a line, a stacked bar, small multiples |
| A sparkline or progress ring as decoration | A chart only when it is read |
| Round, unsourced proof numbers ("3x faster") | The measured figure with its source, or no figure |
| Value labels coloured like their series | Ink text with a swatch |
| A table that scrolls the whole page sideways on a phone | Scroll inside the wrapper, or restack the rows |
| Zebra stripes plus rules plus an outer border | Horizontal rules only |

## Words

| Do not | Do instead |
|---|---|
| "Charts", "Data", "Overview", "Features" as headings | Say what the block shows |
| "Open", "Learn more", "Read more", "Click here", "Submit" ✓ | Verb plus object |
| The same fact in the hero, the KPI row and the table | Once, in the place it is needed |
| Placeholder text, `href="#"`, invented names and metrics | Real content, or the "Illustrative" label and a clearly sample value |
| "This section shows...", "Below you will find..." | Start with the content |
