# Blend360 document brand reference

Two sources, both read from the files themselves (no public Blend360 brand guide exists to cite):

1. `assets/blend-letterhead.dotx`: theme, page setup, header, footer. It defines no heading, title, list or
   table styles.
2. A real Blend document built on that template (the "ADR - Operación" operations document): its
   `styles.xml` and body formatting supplied the text styles and the table design. Marked **(ADR)** below.

Anything neither source fixes is **derived**: a reasonable default, not an official rule. If Blend publishes
a brand guide, it wins. The ADR file itself is not in the repo (it holds names and comments); only the
extracted style values are.

## Contents

- [Fixed by the template](#fixed-by-the-template)
- [Palette](#palette)
- [Typography](#typography)
- [Text styles and tables](#text-styles-and-tables)
- [Header and footer](#header-and-footer)
- [Known limits](#known-limits)

## Fixed by the template

| Item | Value |
|---|---|
| Page | A4 portrait, 11906 x 16838 twips (21.0 x 29.7 cm) |
| Margins | 1 inch (2.54 cm) on all sides; header and footer 0.5 inch from the edge |
| Text column | 9026 twips = 15.92 cm = 6.27 in |
| Body font | Montserrat (theme minor font) |
| Heading font | Montserrat Black (theme major font) |
| Default body size | 11 pt in the document defaults (the template's empty body paragraph is 12 pt navy, but real use in the ADR is 11 pt automatic) |
| Default paragraph | 8 pt after, line 1.08 |
| Language | en-US |
| Theme | "Blend360" color scheme, "Custom 2" font scheme |

## Palette

Theme colors, with how this skill uses them. Contrast is WCAG against the stated background.

| Name | Hex | Theme slot | Use | Contrast |
|---|---|---|---|---|
| Navy | `003059` | accent2 | Title, headings, table header fill, links, single-series charts. Body text is automatic (black) | 13.4:1 on white |
| Cyan | `00EDED` | accent3 | Rules, accents, callout edges, KPI top border. **Never text on white** | 1.5:1 on white, 9.1:1 on navy |
| Light cyan | `A2F3F3` | accent1 | The page background mark (shown at 20%) | decorative |
| Slate | `304550` | accent4 | Secondary text, captions, labels | 10.0:1 on white |
| Ink | `1A1A1A` | accent5 | Chart value labels, code | 17.4:1 on white |
| Near black | `0B0D0E` | accent6 | Reserved | |
| Paper | `F3F3F0` | dk2 | Zebra rows, KPI tiles, code and key callout fill | navy 12.1:1 on it |
| Footer grey | `808080` | n/a | Footer text only | 3.9:1 (small, footer only) |

Derived tints and extras: `ECFDFD` (light cyan at 20%, matches the background mark; callout fill),
`D9E2E7` (table grid, from the ADR), `E39B2D` / `FFF6E5` (amber for warnings, kept off the brand palette on purpose).

**Theme color trap.** The template theme is inverted: `dk1` is `FFFFFF` and `lt1` is `1A1A1A`, and the
mapping sends text1 to dark1. Never reference theme colors (`themeColor="text1"`) in generated XML: use
explicit RGB, as `blend_docx.py` does.

## Typography

Montserrat must be installed on the machine that opens the document, or Word substitutes a font and the
layout shifts. `fc-list | grep -i montserrat` checks; Google Fonts distributes it. Static weights used:
Regular, Italic, Bold, and **Montserrat Black** (a separate family name, used for display text).

## Text styles and tables

**(ADR)** = measured in the Blend ADR document; the rest is derived. All styles are real Word styles, so
changing one in Word restyles every paragraph that uses it.

| Style | Font | Size | Spacing before / after | Source and notes |
|---|---|---|---|---|
| Normal | Montserrat, automatic color | 11 pt | 0 / 8 pt, line 1.08 | (ADR) document defaults |
| Title | Montserrat Bold, navy | 26 pt | 0 / 6 pt | (ADR) the ADR types it in capitals; the style does not force caps |
| Subtitle | Montserrat, navy | 13 pt | 0 / 12 pt | (ADR) |
| Heading 1 | Montserrat Black, navy | 16 pt | 12 / 0 pt | (ADR) keep with next; outline level 1 |
| Heading 2 | Montserrat Black, navy | 13 pt | 12 / 0 pt | (ADR) outline level 2 |
| Heading 3 | Montserrat Black, navy | 11 pt | 12 / 0 pt | (ADR) outline level 3 |
| TOC Heading | Montserrat Black bold, navy | 14 pt | 24 / 0 pt | (ADR) not listed in the TOC |
| TOC 1 / 2 / 3 | Montserrat | 12 bold italic / 11 bold / 10 | 6 / 0 pt; indent 0 / 220 / 440 | (ADR) |
| Hyperlink (character) | navy, underlined | | | derived: the ADR's cyan `00EDED` is 1.5:1 on white |
| Table Text / Table Header | Montserrat / Bold white | 10 pt (9 pt "Small") | 0 / 0 | ADR uses 11 pt, or 9 pt for dense tables |
| Meta | Montserrat, slate | 9 pt | 0 / 2 pt | derived: dates, authors, references |
| Caption | Montserrat Italic, slate | 8.5 pt | 4 / 12 pt | derived: "Figure n." / "Table n." |
| KPI Value / Label | Montserrat Black navy 24 pt / slate 8.5 pt | | | derived: tile fill Paper, 2.25 pt cyan top border |
| Callout Title / Text | Bold caps navy 9 pt / 10 pt | | | derived: 4.5 pt colored left edge |
| Quote, Code | Italic slate / Courier New 8.5 pt | | | derived |

The ADR's Heading styles are Word's defaults with the Blend theme font and a cyan color (`47E7E7`), and every
heading in the document overrides the color to navy `003059` by hand. This skill puts the navy in the style
itself, so headings look like the ADR without per-run overrides.

**Tables (ADR):** navy `003059` header fill with bold white text; light grid `D9E2E7`, 0.5 pt, on every edge
and between all cells; no banding; default 108 twip side padding. This skill adds 2.5 pt top and bottom
padding (derived) and fixed column widths set on both the grid and every cell. Optional: `zebra=True`
(Paper rows), `total_row=True` (bold on light cyan), `compact=True` (9 pt).

**Lists:** Word's standard structure (720 twips per level, 360 hanging; Symbol, Courier New and Wingdings
bullets; decimal, letter, roman numbering), as in the ADR numbering part. The ADR body itself types "- " by hand.

Rules of thumb: one H1 per major section; never skip heading levels; use cyan only as a line or fill; align
numbers right; one key-takeaway callout per page at most.

## Header and footer

Both come from the template untouched, on every page and every section:

- **Header:** Blend logo (`image1.png`, 3.53 x 0.67 cm) at the top-left margin; behind the text, a large
  "B" ring mark (`image2.png`, rotated 180 degrees, 20% opacity) that bleeds off the right and bottom edges.
- **Footer:** `© Copyright of Blend360 2023. All rights reserved.` on the left; web, LinkedIn and X icons
  with `www.blend360.com | Blend360 | @OfficialB360` on the right; 6.5 pt, grey `808080`.

The copyright year is baked into the template. Pass `copyright_year=2026` (or `--year` on the converter)
to update it; leave it alone when the user wants the template verbatim.

## Known limits

- **Landscape sections:** the footer icons are anchored at fixed offsets, so on landscape pages they sit left
  of the web text instead of above it. Fine for appendices; avoid landscape for the main flow.
- **Table of contents:** Word builds it when the file opens (it asks once). LibreOffice and previews show the
  placeholder line.
- **Background mark:** it sits behind content on every page. Opaque white chart images and table fills cover
  it; that is acceptable, but do not place small text directly on the thickest part of the ring.
- **Fonts when sharing:** fonts are not embedded in the .docx, so recipients without Montserrat see a substitute
  and the layout shifts. Tell them to install it (Google Fonts); the deliverable stays a .docx either way.
