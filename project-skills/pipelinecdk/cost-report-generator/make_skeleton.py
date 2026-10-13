#!/usr/bin/env python3
"""Maintenance only: build assets/template_skeleton.xlsx from the full template workbook.

Keeps the whole package (charts, styles, formulas of Resumen / Analisis de Costos / Analisis)
but cuts Detalle_facturado, Por_cuenta, Por_servicio and Cuenta_servicio_uso down to the
header row plus one prototype data row (cost_report.py regenerates the rest) and drops calcChain.
Usage: make_skeleton.py "<full template>.xlsx"   (the template is only read)
"""
import re
import sys
import zipfile
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(__file__).resolve().parent / "assets" / "template_skeleton.xlsx"
dst.parent.mkdir(exist_ok=True)
CUT = {f"xl/worksheets/sheet{n}.xml" for n in (3, 4, 5, 7)}
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
    for name in zin.namelist():
        if name == "xl/calcChain.xml":
            continue
        data = zin.read(name)
        if name in CUT:
            x = data.decode("utf-8")
            i = x.index("<sheetData>")
            row2 = re.search(r'<row r="2".*?</row>', x, re.S).end()
            x = x[:row2] + x[x.index("</sheetData>"):]
            data = x.encode("utf-8")
        elif name == "xl/_rels/workbook.xml.rels":
            data = re.sub(rb'<Relationship Id="[^"]*" Type="[^"]*/calcChain" Target="calcChain.xml"/>', b"", data)
        elif name == "[Content_Types].xml":
            data = re.sub(rb'<Override PartName="/xl/calcChain.xml"[^>]*/>', b"", data)
        zout.writestr(name, data)
print("wrote", dst, dst.stat().st_size, "bytes")
