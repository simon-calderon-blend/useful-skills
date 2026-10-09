# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.1", "lxml", "matplotlib"]
# ///
"""Build Blend360-branded Word documents on top of the Blend letterhead template.

The template (assets/blend-letterhead.dotx) supplies the page, header (logo and
background mark), footer, theme fonts and colors. This module adds the paragraph,
table and list styles the template lacks, plus content blocks (headings, tables,
callouts, KPI rows, charts, letters). See references/brand.md for the values.

    from blend_docx import BlendDocument
    doc = BlendDocument(title="Q3 report", author="Jane Doe")
    doc.cover("Q3 report", "Customer analytics")
    doc.heading("Summary")
    doc.paragraph("Revenue grew **12%** year over year.")
    doc.save("q3-report.docx")
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date as _date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.parts.numbering import NumberingPart
from docx.shared import Cm, Emu, Pt, RGBColor

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "blend-letterhead.dotx"

# Palette taken from the template theme (see references/brand.md).
NAVY = "003059"        # accent2: headings, title, table headers, links (body text stays automatic, as in the ADR)
CYAN = "00EDED"        # accent3: rules and accents only, never text on white
CYAN_LIGHT = "A2F3F3"  # accent1
SLATE = "304550"       # accent4: secondary text
INK = "1A1A1A"         # accent5
PAPER = "F3F3F0"       # theme dk2: zebra rows, code, KPI tiles
CYAN_TINT = "ECFDFD"   # CYAN_LIGHT at 20%, the tint of the page background mark
MUTED = "808080"       # footer text
GRID = "D9E2E7"        # table grid lines (from the Blend ADR document)
AMBER, AMBER_TINT = "E39B2D", "FFF6E5"  # derived, for warnings

LINE = 259 / 240  # Word default line spacing, 1.08
BODY_FONT = "Montserrat"
DISPLAY_FONT = "Montserrat Black"
MONO_FONT = "Courier New"

_INLINE = re.compile(
    r"\[(?P<ltext>[^\]]+)\]\((?P<url>[^)\s]+)\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|`(?P<code>[^`]+)`"
    r"|(?<![\w*])\*(?P<ital>[^*\s][^*]*?)\*(?![\w*])"
)

# Child order required by the WordprocessingML schema.
_PPR = ("pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers "
        "pBdr shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE "
        "autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents "
        "suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle "
        "rPr sectPr pPrChange").split()
_TCPR = ("cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText "
         "vAlign hideMark").split()
_TBLPR = ("tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc "
          "tblCellSpacing tblInd tblBorders shd tblLayout tblCellMar tblLook").split()
_SIDES = ["top", "left", "bottom", "right", "insideH", "insideV"]


def _put(parent, child, order):
    """Insert child into parent at its schema position, replacing a same-named sibling."""
    name = child.tag.split("}")[1]
    for old in parent.findall(qn(f"w:{name}")):
        parent.remove(old)
    later = set(order[order.index(name) + 1:])
    for i, sib in enumerate(parent):
        if sib.tag.split("}")[1] in later:
            parent.insert(i, child)
            return child
    parent.append(child)
    return child


def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(f"w:{k}"), str(v))
    return e


def _borders(container_tag, **sides):
    """Build w:pBdr / w:tcBorders / w:tblBorders. Each side is (eighths_of_pt, color) or None (no border)."""
    b = _el(container_tag)
    for side in _SIDES:
        if side not in sides:
            continue
        spec = sides[side]
        if spec is None:
            b.append(_el(f"w:{side}", val="nil"))
        else:
            sz, color = spec
            b.append(_el(f"w:{side}", val="single", sz=sz, space=4 if container_tag == "w:pBdr" else 0, color=color))
    return b


def _shade(fill):
    return _el("w:shd", val="clear", color="auto", fill=fill)


def _margins(top, left, bottom, right):
    m = _el("w:tcMar")
    for side, w in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        m.append(_el(f"w:{side}", w=w, type="dxa"))
    return m


def _open_template(path: Path):
    """Open the .dotx as an editable document (python-docx rejects the template content type)."""
    data = path.read_bytes()
    if path.suffix.lower() == ".dotx":
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                blob = zin.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    blob = blob.replace(b"wordprocessingml.template.main+xml", b"wordprocessingml.document.main+xml")
                zout.writestr(item, blob)
        data = out.getvalue()
    return Document(io.BytesIO(data))


class BlendDocument:
    def __init__(self, title: str = "", author: str = "", subject: str = "",
                 template: Path | str = TEMPLATE, copyright_year: int | None = None,
                 figure_label: str = "Figure", table_label: str = "Table"):
        self.figure_label, self.table_label = figure_label, table_label  # e.g. "Figura" / "Tabla" for Spanish
        self.doc = _open_template(Path(template))
        # The template carries SharePoint metadata (customXml) that names people it was shared with.
        for rid, rel in list(self.doc.part.rels.items()):
            if rel.reltype.endswith("/customXml"):
                self.doc.part.drop_rel(rid)
        body = self.doc.element.body
        for child in list(body):
            if child.tag != qn("w:sectPr"):
                body.remove(child)
        self._figures = self._tables = 0
        self._next_num = 2  # numId 1 is the shared bullet list
        self._define_styles()
        self._define_numbering()
        props = self.doc.core_properties
        props.title, props.subject = title, subject
        props.author = props.last_modified_by = author  # replaces the template's author names
        props.comments = ""
        if copyright_year:
            self._set_copyright_year(copyright_year)

    # ---- geometry -------------------------------------------------------
    @property
    def content_width_twips(self) -> int:
        s = self.doc.sections[-1]
        return int((s.page_width - s.left_margin - s.right_margin) / 635)

    @property
    def content_width_cm(self) -> float:
        s = self.doc.sections[-1]
        return (s.page_width - s.left_margin - s.right_margin) / 360000

    # ---- styles ---------------------------------------------------------
    def _style(self, name, *, font=BODY_FONT, size=11, bold=False, italic=False, color=None,
               before=0, after=8, line=LINE, keep_next=False, keep_lines=False, outline=None, extra=None,
               caps=False):
        styles = self.doc.styles
        try:
            st = styles[name]
        except KeyError:
            st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        if name != "Normal":
            st.base_style = styles["Normal"]
        st.quick_style = True
        f = st.font
        f.name, f.size, f.bold, f.italic = font, Pt(size), bold, italic
        if color:  # None leaves the automatic text color, as in the ADR body
            f.color.rgb = RGBColor.from_string(color)
        f.all_caps = caps or None
        rfonts = st.element.get_or_add_rPr().find(qn("w:rFonts"))
        for attr in ("cs", "eastAsia"):
            rfonts.set(qn(f"w:{attr}"), font)
        pf = st.paragraph_format
        pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), line
        pf.keep_with_next = keep_next or None
        pf.keep_together = keep_lines or None
        ppr = st.element.get_or_add_pPr()
        if outline is not None:
            _put(ppr, _el("w:outlineLvl", val=outline), _PPR)
        for el in extra or []:
            _put(ppr, el, _PPR)
        return st

    def _define_styles(self):
        # Values marked (ADR) were read from the styles.xml and body formatting of a real Blend document;
        # the rest are derived. See references/brand.md.
        self._style("Normal")  # (ADR) Montserrat 11 pt, automatic color, 8 pt after, line 1.08
        self._style("Title", size=26, bold=True, color=NAVY, after=6, line=1.0, keep_next=True)  # (ADR)
        self._style("Subtitle", size=13, color=NAVY, after=12)  # (ADR)
        for name, size, level in (("Heading 1", 16, 0), ("Heading 2", 13, 1), ("Heading 3", 11, 2)):
            # (ADR) sizes, 12 pt before, 0 after, keep with next; the ADR styles say cyan but every heading
            # overrides it to navy by hand, so the style itself carries navy here.
            self._style(name, font=DISPLAY_FONT, size=size, color=NAVY, before=12, after=0, keep_next=True,
                        keep_lines=True, outline=level)
        self._style("TOC Heading", font=DISPLAY_FONT, size=14, bold=True, color=NAVY, before=24, line=1.15,
                    keep_next=True, outline=9)  # (ADR) body level so it is not listed in the TOC
        self._style("TOC 1", size=12, bold=True, italic=True, before=6, after=0)  # (ADR)
        self._style("TOC 2", bold=True, before=6, after=0, extra=[_el("w:ind", left=220)])  # (ADR)
        self._style("TOC 3", size=10, after=0, extra=[_el("w:ind", left=440)])  # (ADR)
        self._style("Meta", size=9, color=SLATE, after=2, line=1.1)
        self._style("Caption", size=8.5, italic=True, color=SLATE, before=4, after=12, line=1.1)
        self._style("List Paragraph", after=3)
        self._style("Table Text", size=10, after=0, line=1.1)  # ADR tables use 11 pt, or 9 pt when dense
        self._style("Table Header", size=10, bold=True, color="FFFFFF", after=0, line=1.1)  # (ADR) navy fill
        self._style("Table Text Small", size=9, after=0, line=1.1)
        self._style("Table Header Small", size=9, bold=True, color="FFFFFF", after=0, line=1.1)
        self._style("KPI Value", font=DISPLAY_FONT, size=24, color=NAVY, after=0, line=1.0)
        self._style("KPI Label", size=8.5, color=SLATE, after=0, line=1.1)
        self._style("Callout Title", size=9, bold=True, color=NAVY, after=2, line=1.1, caps=True)
        self._style("Callout Text", size=10, after=0, line=1.2)
        self._style("Quote", italic=True, color=SLATE, before=6, after=10,
                    extra=[_borders("w:pBdr", left=(24, CYAN)), _el("w:ind", left=240)])
        self._style("Code", font=MONO_FONT, size=8.5, color=INK, after=0, line=1.1,
                    extra=[_shade(PAPER), _el("w:ind", left=120, right=120)])
        styles = self.doc.styles
        link = styles.add_style("Hyperlink", WD_STYLE_TYPE.CHARACTER)  # navy: the ADR's cyan is 1.5:1 on white
        link.base_style = styles["Default Paragraph Font"]
        link.font.color.rgb = RGBColor.from_string(NAVY)
        link.font.underline = True

    def _define_numbering(self):
        # Same structure Word writes for its default lists (and the ADR numbering.xml): 720 twips of
        # indent per level, 360 hanging, Symbol / Courier New / Wingdings bullets.
        bullet_glyphs = [("\uf0b7", "Symbol"), ("o", "Courier New"), ("\uf0a7", "Wingdings")]
        number_formats = ["decimal", "lowerLetter", "lowerRoman"]

        def lvl(i, fmt, text, font=""):
            fonts = f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}" w:hint="default"/></w:rPr>' if font else ""
            return (f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/>'
                    f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{720 * (i + 1)}" w:hanging="360"/></w:pPr>{fonts}</w:lvl>')
        bullets = "".join(lvl(i, "bullet", *bullet_glyphs[i % 3]) for i in range(9))
        decimals = "".join(lvl(i, number_formats[i % 3], f"%{i + 1}.") for i in range(9))
        xml = (f'<w:numbering {nsdecls("w")}>'
               f'<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>{bullets}</w:abstractNum>'
               f'<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>{decimals}</w:abstractNum>'
               '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>')
        part = self.doc.part
        try:  # the template has no numbering part, and python-docx cannot create one itself
            self._numbering = part.part_related_by(RT.NUMBERING).element
        except KeyError:
            np = NumberingPart(PackURI("/word/numbering.xml"),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml",
                               parse_xml(xml), part.package)
            part.relate_to(np, RT.NUMBERING)
            self._numbering = np.element

    def _new_numbered_list(self) -> int:
        nid, self._next_num = self._next_num, self._next_num + 1
        self._numbering.append(parse_xml(
            f'<w:num {nsdecls("w")} w:numId="{nid}"><w:abstractNumId w:val="1"/>'
            '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'))
        return nid

    # ---- inline text ----------------------------------------------------
    def _runs(self, p, text, *, bold=None, italic=None, color=None, size=None):
        """Add text to paragraph p, honoring **bold**, *italic*, `code` and [link](url)."""
        pos = 0
        for m in _INLINE.finditer(text):
            if m.start() > pos:
                self._run(p, text[pos:m.start()], bold, italic, color, size)
            if m.group("ltext"):
                self._link(p, m.group("ltext"), m.group("url"), size)
            elif m.group("bold"):
                self._run(p, m.group("bold"), True, italic, color, size)
            elif m.group("code"):
                r = self._run(p, m.group("code"), bold, italic, INK, size and size - 0.5)
                r.font.name = MONO_FONT
                r._r.get_or_add_rPr().append(_shade(PAPER))
            else:
                self._run(p, m.group("ital"), bold, True, color, size)
            pos = m.end()
        if pos < len(text):
            self._run(p, text[pos:], bold, italic, color, size)

    @staticmethod
    def _run(p, text, bold=None, italic=None, color=None, size=None):
        r = p.add_run(text)
        if bold is not None:
            r.bold = bold
        if italic is not None:
            r.italic = italic
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
        if size:
            r.font.size = Pt(size)
        return r

    @staticmethod
    def _link(p, text, url, size=None):
        rid = p.part.relate_to(url, RT.HYPERLINK, is_external=True)
        h = _el("w:hyperlink", history=1)
        h.set(qn("r:id"), rid)
        r = _el("w:r")
        rpr = _el("w:rPr")
        rpr.append(_el("w:rStyle", val="Hyperlink"))  # real style: editable from Word's style pane
        if size:
            rpr.append(_el("w:sz", val=int(size * 2)))
        r.append(rpr)
        t = _el("w:t")
        t.text = text
        r.append(t)
        h.append(r)
        p._p.append(h)

    # ---- text blocks ----------------------------------------------------
    def paragraph(self, text="", *, style="Normal", align=None, bold=None, italic=None, color=None,
                  size=None, space_after=None, keep_next=False):
        p = self.doc.add_paragraph(style=style)
        self._runs(p, text, bold=bold, italic=italic, color=color, size=size)
        if align:
            p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                           "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[align]
        if space_after is not None:
            p.paragraph_format.space_after = Pt(space_after)
        if keep_next:
            p.paragraph_format.keep_with_next = True
        return p

    def _spacer(self, pts=8):
        """Fixed-height gap after a table or callout (an empty Normal paragraph would be much taller)."""
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = Pt(pts)
        return p

    def heading(self, text, level=1):
        if level not in (1, 2, 3):
            raise ValueError("heading level must be 1, 2 or 3")
        return self.paragraph(text, style=f"Heading {level}")

    def title_block(self, title, subtitle="", meta=()):
        """Compact document opening (title, subtitle, meta lines) for non-cover documents."""
        self.paragraph(title, style="Title")
        if subtitle:
            self.paragraph(subtitle, style="Subtitle")
        for line in meta:
            self.paragraph(line, style="Meta")

    def cover(self, title, subtitle="", meta=(), page_break=True):
        """Cover page: title block pushed well below the logo, then a page break."""
        p = self.paragraph(title, style="Title")
        p.paragraph_format.space_before = Pt(150)
        if subtitle:
            self.paragraph(subtitle, style="Subtitle")
        for line in meta:
            self.paragraph(line, style="Meta")
        if page_break:
            self.page_break()

    def bullets(self, items, level=0):
        """items: strings, or (text, [children]) tuples for nesting."""
        self._list(items, level, num_id=1)

    def numbered(self, items, level=0):
        """Same shape as bullets(); every call restarts numbering at 1."""
        self._list(items, level, num_id=self._new_numbered_list())

    def _list(self, items, level, num_id):
        for item in items:
            text, children = (item, ()) if isinstance(item, str) else item
            p = self.paragraph(text, style="List Paragraph")
            num = _el("w:numPr")
            num.append(_el("w:ilvl", val=level))
            num.append(_el("w:numId", val=num_id))
            _put(p._p.get_or_add_pPr(), num, _PPR)
            if children:
                self._list(children, level + 1, num_id)
        if level == 0:  # breathing room before the next block
            self.doc.paragraphs[-1].paragraph_format.space_after = Pt(10)

    def quote(self, text, source=""):
        self.paragraph(text + (f" — {source}" if source else ""), style="Quote")

    def code(self, text):
        for line in text.rstrip("\n").split("\n"):
            self.paragraph(line or " ", style="Code")
        self._spacer(6)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def toc(self, levels=3, title="Contents"):
        """Table of contents field. Word fills it on open (asks once); LibreOffice does not."""
        self.paragraph(title, style="TOC Heading")
        p = self.doc.add_paragraph()
        for kind in ("begin", "instr", "separate", "text", "end"):
            r = p.add_run()._r
            if kind == "instr":
                it = _el("w:instrText")
                it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                it.text = f' TOC \\o "1-{levels}" \\h \\z \\u '
                r.append(it)
            elif kind == "text":
                t = _el("w:t")
                t.text = "Right-click and choose Update Field to build the table of contents."
                r.append(t)
            else:
                r.append(_el("w:fldChar", fldCharType=kind))
        settings = self.doc.settings.element
        if settings.find(qn("w:updateFields")) is None:
            upd = _el("w:updateFields", val="true")
            anchor = next((e for n in ("hdrShapeDefaults", "footnotePr", "endnotePr", "compat")
                           if (e := settings.find(qn(f"w:{n}"))) is not None), None)
            anchor.addprevious(upd) if anchor is not None else settings.append(upd)

    # ---- tables ---------------------------------------------------------
    def _widths(self, ncols, weights):
        """Relative weights (or None for equal columns) -> exact dxa widths summing to the content width."""
        total = self.content_width_twips
        if weights is None:
            weights = [1] * ncols
        ws = [int(total * w / sum(weights)) for w in weights]
        ws[-1] += total - sum(ws)
        return ws

    def _table(self, rows, cols, widths):
        t = self.doc.add_table(rows=rows, cols=cols)
        pr = t._tbl.tblPr
        _put(pr, _el("w:tblW", w=sum(widths), type="dxa"), _TBLPR)
        _put(pr, _el("w:tblLayout", type="fixed"), _TBLPR)
        _put(pr, _el("w:tblInd", w=0, type="dxa"), _TBLPR)
        mar = _el("w:tblCellMar")
        for side, w in (("top", 50), ("left", 108), ("bottom", 50), ("right", 108)):
            mar.append(_el(f"w:{side}", w=w, type="dxa"))
        _put(pr, mar, _TBLPR)
        for i, w in enumerate(widths):  # dual widths: grid column and every cell
            t.columns[i].width = Emu(w * 635)
            for row in t.rows:
                row.cells[i].width = Emu(w * 635)
        for row in t.rows:
            row._tr.get_or_add_trPr().append(_el("w:cantSplit"))
        return t

    def table(self, header, rows, widths=None, align=None, zebra=False, total_row=False, caption="",
              keep_together=None, compact=False):
        """header: list[str]; rows: list[list]; widths: relative weights; align: 'l'/'r'/'c' per column.

        Design from the Blend ADR: navy header with white bold text, light grid (D9E2E7), no banding.
        compact=True uses 9 pt for dense tables (the ADR uses 9 pt there and 11 pt in small ones).
        total_row=True bolds the last row on a light-cyan fill. zebra=True adds Paper banding.
        keep_together keeps rows (and the caption) on one page; default is on for tables up to 15 rows.
        Cells accept inline markup.
        """
        ncols = len(header)
        align = align or ["l"] * ncols
        jc = {"l": None, "r": WD_ALIGN_PARAGRAPH.RIGHT, "c": WD_ALIGN_PARAGRAPH.CENTER}
        t = self._table(len(rows) + 1, ncols, self._widths(ncols, widths))
        _put(t._tbl.tblPr, _borders("w:tblBorders", top=(4, GRID), left=(4, GRID), bottom=(4, GRID),
                                    right=(4, GRID), insideH=(4, GRID), insideV=(4, GRID)), _TBLPR)
        t.rows[0]._tr.get_or_add_trPr().append(_el("w:tblHeader"))  # repeat header on each page
        head_style, text_style = ("Table Header Small", "Table Text Small") if compact else ("Table Header", "Table Text")
        for r, row in enumerate([list(header)] + [[str(v) for v in x] for x in rows]):
            is_total = total_row and r == len(rows)
            for c, value in enumerate(row):
                cell = t.cell(r, c)
                tcpr = cell._tc.get_or_add_tcPr()
                if r == 0:
                    _put(tcpr, _shade(NAVY), _TCPR)
                elif is_total:
                    _put(tcpr, _shade(CYAN_TINT), _TCPR)
                elif zebra and r % 2 == 0:
                    _put(tcpr, _shade(PAPER), _TCPR)
                _put(tcpr, _el("w:vAlign", val="center"), _TCPR)
                p = cell.paragraphs[0]
                p.style = head_style if r == 0 else text_style
                p.alignment = jc[align[c]]
                self._runs(p, value, bold=True if is_total else None)
                if keep_together if keep_together is not None else len(rows) <= 15:
                    p.paragraph_format.keep_with_next = r < len(rows) or bool(caption)
        if caption:
            self._tables += 1
            self.paragraph(f"{self.table_label} {self._tables}. {caption}", style="Caption")
        else:
            self._spacer()
        return t

    def callout(self, text, title="", kind="note"):
        """kind: 'note' (cyan), 'key' (navy, for the one takeaway), 'warning' (amber)."""
        accent, fill = {"note": (CYAN, CYAN_TINT), "key": (NAVY, PAPER), "warning": (AMBER, AMBER_TINT)}[kind]
        t = self._table(1, 1, [self.content_width_twips])
        cell = t.cell(0, 0)
        tcpr = cell._tc.get_or_add_tcPr()
        _put(tcpr, _borders("w:tcBorders", top=None, left=(36, accent), bottom=None, right=None), _TCPR)
        _put(tcpr, _shade(fill), _TCPR)
        _put(tcpr, _margins(120, 200, 120, 160), _TCPR)
        first = cell.paragraphs[0]
        if title:
            first.style = "Callout Title"
            self._runs(first, title)
            body = cell.add_paragraph(style="Callout Text")
        else:
            first.style = "Callout Text"
            body = first
        self._runs(body, text)
        self._spacer()

    def kpis(self, items):
        """items: [(value, label), ...] shown as tiles; 2 to 4 fit comfortably."""
        n = len(items)
        t = self._table(1, n, self._widths(n, None))
        _put(t._tbl.tblPr, _borders("w:tblBorders", insideV=(36, "FFFFFF")), _TBLPR)
        for c, (value, label) in enumerate(items):
            cell = t.cell(0, c)
            tcpr = cell._tc.get_or_add_tcPr()
            _put(tcpr, _borders("w:tcBorders", top=(18, CYAN)), _TCPR)
            _put(tcpr, _shade(PAPER), _TCPR)
            _put(tcpr, _margins(140, 160, 140, 120), _TCPR)
            cell.paragraphs[0].style = "KPI Value"
            self._runs(cell.paragraphs[0], str(value))
            lab = cell.add_paragraph(style="KPI Label")
            self._runs(lab, label)
        self._spacer()

    # ---- figures --------------------------------------------------------
    def image(self, path_or_stream, width_cm=None, caption="", alt="", align="center"):
        width_cm = min(width_cm or self.content_width_cm, self.content_width_cm)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if align == "center" else WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.keep_with_next = bool(caption)
        p.paragraph_format.space_after = Pt(0 if caption else 8)
        pic = p.add_run().add_picture(path_or_stream, width=Cm(width_cm))
        pic._inline.docPr.set("descr", alt or caption or "Figure")
        if caption:
            self._figures += 1
            self.paragraph(f"{self.figure_label} {self._figures}. {caption}", style="Caption")

    def chart(self, fig, width_cm=None, caption="", alt="", transparent=False):
        """Embed a matplotlib figure (see blend_charts.py) as a 220-dpi PNG.

        Opaque white by default. transparent=True lets the page background mark show through, but some
        PDF viewers resample transparent PNGs with dark fringes on thin gridlines.
        """
        import matplotlib.pyplot as plt
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=220, bbox_inches="tight", transparent=transparent, facecolor="white")
        plt.close(fig)
        buf.seek(0)
        self.image(buf, width_cm, caption, alt or caption)

    # ---- letters --------------------------------------------------------
    def letter_head(self, recipient=(), subject="", on=None, reference=""):
        """Date, recipient block and subject line. `on` is a date or a ready-made string."""
        on = on or _date.today()
        self.paragraph(on if isinstance(on, str) else f"{on:%B} {on.day}, {on.year}", space_after=14)
        for i, line in enumerate(recipient):
            self.paragraph(line, space_after=14 if i == len(recipient) - 1 else 0)
        if reference:
            self.paragraph(reference, style="Meta", space_after=6)
        if subject:
            self.paragraph(subject, bold=True, space_after=10)

    def signature(self, name, role="", closing="Sincerely,"):
        self.paragraph(closing, space_after=30, keep_next=True)
        self.paragraph(name, bold=True, space_after=0, keep_next=bool(role))
        if role:
            self.paragraph(role, style="Meta")

    # ---- sections -------------------------------------------------------
    def landscape(self):
        """Start a landscape section (wide tables). Header and footer carry over."""
        self._orient(WD_ORIENT.LANDSCAPE)

    def portrait(self):
        self._orient(WD_ORIENT.PORTRAIT)

    def _orient(self, orient):
        s = self.doc.add_section(WD_SECTION.NEW_PAGE)
        w, h = s.page_width, s.page_height
        if (orient == WD_ORIENT.LANDSCAPE) != (w > h):
            s.page_width, s.page_height = h, w
        s.orientation = orient

    # ---- footer / output ------------------------------------------------
    def _set_copyright_year(self, year):
        for sec in self.doc.sections:
            for t in sec.footer._element.iter(qn("w:t")):
                if t.text and "Copyright" in t.text:
                    t.text = re.sub(r"\b20\d\d\b", str(year), t.text)

    def save(self, path):
        path = Path(path)
        if path.suffix.lower() != ".docx":
            raise ValueError("output must end in .docx")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(path)
        return path
