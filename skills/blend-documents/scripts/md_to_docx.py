# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.1", "lxml", "matplotlib"]
# ///
"""Convert Markdown to a Blend-branded .docx.

    uv run md_to_docx.py input.md output.docx [--cover] [--toc] [--author NAME] [--year 2026] [--lang es]

Supported: front matter (title, subtitle, author, date), # to ### headings, paragraphs with
**bold** *italic* `code` [links](url), bullet and numbered lists (nested), pipe tables
(column alignment from the separator row), fenced code, images, blockquotes, GitHub alerts
(> [!NOTE] / [!KEY] / [!WARNING]), `<!-- pagebreak -->`, and charts:

    ```chart
    {"type": "bar", "categories": ["Q1", "Q2"], "series": {"Revenue": [4.1, 4.6]},
     "caption": "Revenue", "highlight": "Q2"}
    ```
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blend_docx import BlendDocument  # noqa: E402

BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)")
NUMBER = re.compile(r"^(\s*)\d+[.)]\s+(.*)")
IMAGE = re.compile(r'^!\[(.*?)\]\((\S+?)(?:\s+"(.*)")?\)\s*$')
LANGS = {"en": ("Figure", "Table", "Contents"), "es": ("Figura", "Tabla", "Contenido")}
ALERT = {"NOTE": ("note", "Note"), "KEY": ("key", "Key takeaway"), "WARNING": ("warning", "Warning")}


def front_matter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, text[m.end():]


def list_tree(items):
    """[(indent, text)] -> nested [(text, children)] using relative indentation."""
    root = []
    stack = [(-1, root)]  # (indent, list that children at deeper indents are appended to)
    for indent, text in items:
        while stack[-1][0] >= indent:
            stack.pop()
        children = []
        stack[-1][1].append((text, children))
        stack.append((indent, children))
    return root


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render_chart(doc, spec):
    import blend_charts as bc
    kind = spec.get("type", "bar")
    if kind == "bar":
        fig = bc.bar_chart(spec["categories"], spec["series"], horizontal=spec.get("horizontal", False),
                           stacked=spec.get("stacked", False), highlight=spec.get("highlight"),
                           value_fmt=spec.get("value_fmt", "{:,.0f}"), axis_label=spec.get("axis_label", ""))
    elif kind == "line":
        fig = bc.line_chart(spec["x"], spec["series"], value_fmt=spec.get("value_fmt", "{:,.0f}"),
                            axis_label=spec.get("axis_label", ""))
    elif kind == "donut":
        fig = bc.donut_chart(spec["labels"], spec["values"], center_text=spec.get("center_text", ""))
    else:
        raise ValueError(f"unknown chart type {kind!r} (bar, line, donut)")
    doc.chart(fig, width_cm=spec.get("width_cm"), caption=spec.get("caption", ""), alt=spec.get("alt", ""))


def convert(md_path, out_path, cover=False, toc=False, author="", year=None, lang="en"):
    meta, body = front_matter(Path(md_path).read_text(encoding="utf-8"))
    figure, table, contents = LANGS[lang]
    doc = BlendDocument(title=meta.get("title", ""), author=author or meta.get("author", ""), copyright_year=year,
                        figure_label=figure, table_label=table)
    if meta.get("title"):
        opener = doc.cover if cover else doc.title_block
        opener(meta["title"], meta.get("subtitle", ""), [m for m in (meta.get("date"), meta.get("author")) if m])
    if toc:
        doc.toc(title=contents)

    lines, i, para = body.splitlines(), 0, []

    def flush():
        if para:
            doc.paragraph(" ".join(s.strip() for s in para))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("```"):
            flush()
            lang, buf = stripped[3:].strip(), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            if lang == "chart":
                render_chart(doc, json.loads("\n".join(buf)))
            else:
                doc.code("\n".join(buf))
        elif m := re.match(r"^(#{1,6})\s+(.*)", stripped):
            flush()
            doc.heading(m.group(2), min(len(m.group(1)), 3))
        elif stripped == "<!-- pagebreak -->":
            flush()
            doc.page_break()
        elif m := IMAGE.match(stripped):
            flush()
            src = Path(m.group(2))
            doc.image(src if src.is_absolute() else Path(md_path).parent / src, caption=m.group(3) or "",
                      alt=m.group(1))
        elif stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            flush()
            header, seps, rows = split_row(stripped), split_row(lines[i + 1]), []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            i -= 1
            align = ["c" if s.startswith(":") and s.endswith(":") else "r" if s.endswith(":") else "l" for s in seps]
            weights = [max(len(r[c]) if c < len(r) else 0 for r in [header] + rows) + 4 for c in range(len(header))]
            doc.table(header, [r + [""] * (len(header) - len(r)) for r in rows], widths=weights, align=align)
        elif stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            i -= 1
            tag = re.match(r"^\[!(\w+)\]$", quote[0]) if quote else None
            if tag and tag.group(1).upper() in ALERT:
                kind, title = ALERT[tag.group(1).upper()]
                doc.callout(" ".join(quote[1:]), title=title, kind=kind)
            else:
                doc.quote(" ".join(quote))
        elif BULLET.match(line) or NUMBER.match(line):
            flush()
            numbered = bool(NUMBER.match(line))
            items = []
            while i < len(lines) and (m := BULLET.match(lines[i]) or NUMBER.match(lines[i])):
                items.append((len(m.group(1).expandtabs(4)), m.group(2)))
                i += 1
            i -= 1
            (doc.numbered if numbered else doc.bullets)(list_tree(items))
        else:
            para.append(line)
        i += 1
    flush()
    return doc.save(out_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--cover", action="store_true", help="use a cover page instead of a compact title block")
    ap.add_argument("--toc", action="store_true", help="insert a table of contents (Word updates it on open)")
    ap.add_argument("--author", default="")
    ap.add_argument("--year", type=int, help="year shown in the footer copyright line (template says 2023)")
    ap.add_argument("--lang", choices=sorted(LANGS), default="en", help="caption and contents labels")
    a = ap.parse_args()
    print(convert(a.input, a.output, a.cover, a.toc, a.author, a.year, a.lang))
