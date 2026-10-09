---
name: blend-documents
description: Creates Blend360-branded Word documents, always as editable .docx files, on the official Blend letterhead template, with the logo header, brand footer, Montserrat typography taken from real Blend documents, navy and cyan palette, and ready-made headings, tables, KPI tiles, callouts and brand-styled charts. Use when the user asks for a Blend or Blend360 document, report, proposal, memo, letter, status brief, meeting notes or one-pager, mentions the Blend letterhead or template ("plantilla de Blend", "papel membretado", "documento con el formato de Blend"), or wants Markdown, an analysis or data turned into a branded Word document.
---

# Blend documents

Generates `.docx` files on `assets/blend-letterhead.dotx`. The template's header (logo and background mark),
footer, page setup and theme are kept as is; this skill adds the text styles (measured from a real Blend
document) and the blocks the template lacks.

**Every file this skill produces is a `.docx`**, so the user can edit it in Word. Never hand over a PDF, `.dotx`
or image instead. Text uses real Word styles (restyle once, everything updates); tables, lists and the table of
contents are native Word objects.

## Quick start

Prose-heavy content: write Markdown, convert.

```bash
uv run <skill-dir>/scripts/md_to_docx.py in.md out/name.docx [--cover] [--toc] [--lang es] [--year 2026]
```

KPI tiles, letters, landscape tables or custom charts: use the Python API.

```python
# /// script
# dependencies = ["python-docx>=1.1", "lxml", "matplotlib"]
# ///
import sys; sys.path.insert(0, "<skill-dir>/scripts")
from blend_docx import BlendDocument
from blend_charts import bar_chart

doc = BlendDocument(title="Q3 report", author="Jane Doe")
doc.cover("Q3 report", "Customer analytics", ["October 2026"])
doc.heading("Summary")
doc.kpis([("+12%", "Revenue"), ("91%", "Retention")])
doc.callout("Retention drives the growth.", title="Key takeaway", kind="key")
doc.chart(bar_chart(["Q1", "Q2"], {"Revenue": [4.1, 4.6]}), caption="Revenue by quarter")
doc.save("out/q3-report.docx")
```

Run with `uv run script.py`. Working examples: `examples/report.py` (cover, TOC, KPIs, 3 chart types,
tables, landscape appendix), `examples/letter.py`, `examples/sample.md` (converter input).

## Workflow

1. **Scope it.** Confirm document type, audience, language (English or Spanish), and whether there is a
   cover and table of contents. Pick sensible defaults rather than interviewing; ask only what changes the output.
   Real content comes from the user; never invent figures. If sample data is needed, label it "synthetic".
2. **Choose the path.** Markdown converter for mostly prose with tables and a few charts; Python API otherwise.
   Structure by document type is in [components.md](references/components.md#recipes-by-document-type).
3. **Build** with `uv run`. For Spanish pass `figure_label="Figura", table_label="Tabla"` (API) or `--lang es`.
4. **Verify.** Always render and look at every page:
   `<skill-dir>/scripts/render.sh out/name.docx` (PDF and PNGs go to a temp folder, review only), then read the PNGs. Check: logo and footer present,
   no orphan headings or lone table rows, charts legible, no text over the thickest part of the background ring.
   For a strict check run the `docx` skill's `scripts/office/validate.py` on the file.
5. **Deliver** only the `.docx` and its path. Mention caveats that apply: Word fills the table of contents on
   open (and asks once); the machine opening it needs Montserrat installed or Word substitutes a font; charts
   are embedded images, so changing a number means regenerating the chart; the footer says 2023 unless
   `--year` / `copyright_year` is set.

## Brand rules in one screen

- Fonts: Montserrat body (11 pt, automatic color), **Montserrat Black** for headings (H1 16, H2 13, H3 11 pt, navy
  `003059`), title 26 pt bold navy. Cyan `00EDED` only as lines and fills (never text on white), slate `304550`
  for secondary text. These sizes come from a real Blend document, not guesses.
- Page A4, 1-inch margins, 15.9 cm text column. One H1 per section, no skipped levels. Tables: navy header with
  white bold text, light grid `D9E2E7`, right-aligned numbers, 10 pt (9 pt with `compact=True`).
- Charts: navy for one series, fixed validated palette for 2 to 5, legend for 2+, no dual axes, no in-figure
  title (the numbered caption is the title).
- Never use theme colors in generated XML (the template theme is inverted); `blend_docx.py` uses explicit RGB.
- Full values and the derived-versus-template distinction: [brand.md](references/brand.md).

## Reference

- [brand.md](references/brand.md): palette with contrast, text styles (measured vs derived), tables, page geometry, header and footer, known limits.
- [components.md](references/components.md): every block, Markdown syntax, recipes per document type.
- [charts.md](references/charts.md): chart selection, color rules, custom charts, diagrams.

## Notes

- Do not edit `assets/blend-letterhead.dotx`; it is the brand source. To change what every document looks like,
  change `blend_docx.py` styles.
- To modify an already-built Blend `.docx`, use the `docx` skill (unpack, edit XML, repack); do not regenerate.
- Pyright or IDE warnings about unresolved `docx` imports are expected: dependencies come from `uv run`, not a global install.
