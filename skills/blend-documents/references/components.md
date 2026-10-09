# Components and document recipes

API of `scripts/blend_docx.py` (`BlendDocument`), the Markdown syntax of `scripts/md_to_docx.py`, and
recipes for common document types. Values behind the styles are in [brand.md](brand.md); charts are in
[charts.md](charts.md).

## Contents

- [Setup](#setup)
- [Blocks](#blocks)
- [Inline markup](#inline-markup)
- [Markdown converter](#markdown-converter)
- [Recipes by document type](#recipes-by-document-type)
- [Editing an existing Blend document](#editing-an-existing-blend-document)

## Setup

```python
import sys; sys.path.insert(0, "<skill-dir>/scripts")
from blend_docx import BlendDocument
doc = BlendDocument(title="...", author="...", copyright_year=None)  # year None keeps the template's 2023
...
doc.save("out/name.docx")   # must end in .docx
```

Run scripts with `uv run script.py`: the `# /// script` header installs python-docx, lxml and matplotlib.
`BlendDocument` opens the `.dotx`, empties the body and keeps header, footer, page setup and theme.
`save()` only writes `.docx`. The template's author names and SharePoint sharing metadata are removed from
the output; pass `author=` to set one. Text styles are real Word styles, so edits in Word apply document-wide.

## Blocks

| Call | Produces | Notes |
|---|---|---|
| `cover(title, subtitle, meta=[...], page_break=True)` | Cover page | Title sits below the logo; follow with a heading |
| `title_block(title, subtitle, meta=[...])` | Compact opening on page 1 | For short documents, no cover |
| `toc(levels=3)` | Table of contents | Word fills it on open; place after the cover |
| `heading(text, level)` | Heading 1 to 3 | Level 4+ is not defined; restructure instead |
| `paragraph(text, align=, bold=, italic=, color=, size=, space_after=)` | Body text | Inline markup works; colors are hex without `#` |
| `bullets(items)` / `numbered(items)` | Lists | Item is a string or `(text, [children])`; each `numbered` call restarts at 1 |
| `table(header, rows, widths=, align=, zebra=False, total_row=False, compact=False, caption=)` | Table | Navy header, light grid. `widths` are relative weights; `align` is `"l"`/`"r"`/`"c"` per column; `compact=True` is 9 pt; rows stay together up to 15 rows |
| `kpis([(value, label), ...])` | Metric tiles | 2 to 4 tiles; keep values short ("+44%", "4.2M") |
| `callout(text, title=, kind=)` | Boxed note | `kind`: `note` (cyan), `key` (navy, the main takeaway), `warning` (amber) |
| `quote(text, source=)` | Pull quote | |
| `code(text)` | Monospace block | |
| `image(path, width_cm=, caption=, alt=)` | Picture | Width is capped at the text column; always give `alt` or `caption` |
| `chart(fig, width_cm=, caption=, alt=)` | Matplotlib figure | See [charts.md](charts.md) |
| `letter_head(recipient=[...], subject=, on=, reference=)` / `signature(name, role)` | Letter parts | `on` is a date or a string |
| `page_break()` | New page | |
| `landscape()` / `portrait()` | New section | For wide appendix tables only |

Captions are numbered automatically ("Figure 1.", "Table 1."), separately for figures and tables.

## Inline markup

In `paragraph`, list items, table cells, callouts and KPI text: `**bold**`, `*italic*`, `` `code` ``,
`[label](https://url)`. Links use the Hyperlink character style (navy, underlined); cyan is never used for text.

## Markdown converter

```bash
uv run scripts/md_to_docx.py in.md out.docx [--cover] [--toc] [--author NAME] [--year 2026]
```

| Markdown | Result |
|---|---|
| Front matter `title`, `subtitle`, `date`, `author` | Title block (cover with `--cover`) |
| `#`, `##`, `###` | Heading 1 to 3 (deeper levels become 3) |
| `-` / `1.` lists, indented to nest | Bullets / numbered |
| Pipe table; `:--` `--:` `:-:` set alignment | Branded table (widths follow content length) |
| `> [!NOTE]`, `> [!KEY]`, `> [!WARNING]` + text | Callout; a plain `>` becomes a quote |
| `![alt](path "caption")` | Image with numbered caption; relative paths resolve from the .md file |
| ` ```chart ` + JSON | Chart; `type` is `bar`, `line` or `donut` (fields below) |
| `<!-- pagebreak -->` | Page break |

Chart JSON: `bar`: `categories`, `series` ({name: [values]}), optional `horizontal`, `stacked`, `highlight`,
`value_fmt`, `axis_label`. `line`: `x`, `series`. `donut`: `labels`, `values`, `center_text`. All accept
`caption`, `alt`, `width_cm`. Anything the converter lacks (KPI tiles, landscape, letters) needs the Python API.

## Recipes by document type

**Report or analysis (10+ pages).** `cover` then `toc`, then H1 per section. Open with an executive summary
that has 2 to 4 `kpis` and one `key` callout. One chart or table per claim, each with a caption. End with
numbered recommendations. Appendix tables in `landscape()` after the main flow. See `examples/report.py`.

**Proposal.** `cover`; H1 sections: context, approach, scope, timeline (table), team, pricing (table with
`total_row=True`), next steps. Put commitments in a `key` callout and assumptions in a `warning` callout.

**One-pager or status brief.** `title_block` (no cover), 3 H1 sections at most, one table, one chart,
one `key` callout. Convert from Markdown when the content is mostly prose: see `examples/sample.md`.

**Memo or short note.** `title_block` with meta lines (To, From, Date), then paragraphs and bullets.
No cover, no TOC.

**Business letter.** `letter_head` (date, recipient, subject), salutation, body paragraphs, `signature`.
Keep to one page; the background mark makes a second page feel heavy. See `examples/letter.py`.

**Meeting notes.** `title_block`, a table (attendees), H2 per topic with bullets, a final table of
actions (owner, due date, status).

**Workshop or analysis deliverable with many figures.** Same as a report; use `image()` for screenshots and
diagrams exported as PNG at 2x, width 12 to 16 cm, with captions.

## Editing an existing Blend document

When the user hands over a finished `.docx` built on this template, do not rebuild it. Use the `docx` skill:
unpack, edit `word/document.xml`, repack, validate. The header, footer and styles stay as they are.
