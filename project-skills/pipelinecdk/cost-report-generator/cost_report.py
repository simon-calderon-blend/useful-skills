#!/usr/bin/env python3
"""Regenerate the "Reporte Costos" workbook from the prod CUR for a date window.

Read-only against AWS: S3 ListObjectsV2 + GetObject on the CUR Parquet files only.
No Athena, no Glue, no S3 writes.

The template workbook package is kept (charts, styles, formulas of Resumen /
Analisis de Costos / Analisis). Only the sheetData of Detalle_facturado,
Por_cuenta, Por_servicio and Cuenta_servicio_uso is regenerated, and cached
formula values are refreshed so the file is correct even before Excel recalculates.
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import boto3
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
REF = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))

# Columns read from the CUR Parquet (names confirmed against the real file schema).
CUR_COLS = [
    "line_item_usage_account_id", "line_item_usage_start_date", "line_item_usage_end_date",
    "line_item_product_code", "product_servicecode", "line_item_line_item_type",
    "line_item_line_item_description", "line_item_usage_type", "line_item_operation",
    "line_item_usage_amount", "line_item_currency_code", "line_item_unblended_cost",
    "resource_tags",
]
KEEP_TYPES = ["Usage", "FlatRateSubscription"]
PRUEBAS, PROCESAMIENTO, PROD = ("Plataforma - Ambiente de Pruebas", "Procesamiento",
                                "Plataforma - Producción y Soporte")
DATA_TRANSFER = "AWSDataTransfer"

# Spanish layer of Cuenta_servicio_uso / Por_servicio (reverse-engineered from the template).
CAT_CUS = {"Analitica y BI": "Analítica y BI", "Busqueda y analitica": "Búsqueda y analítica",
           "Integracion y mensajeria": "Integración y mensajería",
           "Integracion y orquestacion": "Integración y orquestación",
           "Operaciones y gestion": "Operaciones y gestión", "Networking": "Redes",
           "Storage": "Almacenamiento"}
# Por_servicio translates fewer labels and keeps the template's "Análitica" spelling.
CAT_PS = {"Analitica y BI": "Análitica y BI", "Busqueda y analitica": "Búsqueda y analítica",
          "Operaciones y gestion": "Operaciones y gestión", "Networking": "Redes"}

DETAIL_COLS = ["Fecha y hora de inicio", "Fecha y hora de fin", "Cuenta AWS", "Nombre de la cuenta",
               "Ambiente", "Servicio AWS", "Modelo o detalle del servicio", "Código de producto AWS",
               "Código de servicio AWS", "Tipo de cargo AWS", "Concepto facturado por AWS",
               "Operación AWS", "Descripción del cargo AWS", "Cantidad reportada por AWS",
               "Unidad de facturación", "Moneda original", "Rubro", "Costo AWS (USD)",
               "Tasa de cambio (COP/USD)", "Costo AWS (COP)", "Tarifa de licenciamiento",
               "Costo licenciamiento (COP)", "Total facturable (COP)", "Regla de atribución",
               "Centro de costo", "Proyecto", "Aplicación", "Categoria principal"]


# ----------------------------------------------------------------------------- CUR access

def read_cur(session, bucket, prefix, months):
    """Download the Parquet files of the given billing periods (read-only GET) into memory."""
    s3 = session.client("s3")
    frames = []
    for m in months:
        pfx = f"{prefix}BILLING_PERIOD={m}/"
        keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=pfx)
                for o in page.get("Contents", []) if o["Key"].endswith(".parquet")]
        if not keys:
            sys.exit(f"ERROR: no Parquet files under s3://{bucket}/{pfx}")
        for key in keys:
            tbl = pq.read_table(io.BytesIO(s3.get_object(Bucket=bucket, Key=key)["Body"].read()))
            missing = [c for c in CUR_COLS if c not in tbl.schema.names]
            if missing:
                sys.exit(f"ERROR: columns missing in s3://{bucket}/{key}: {missing}")
            frames.append(tbl.select(CUR_COLS).to_pandas())
            print(f"  read {key.rsplit('/', 1)[-1]} ({m}): {len(frames[-1]):,} rows")
    return pd.concat(frames, ignore_index=True)


# ----------------------------------------------------------------------------- derivations

def usage_unit(usage_type, desc):
    """Unit label. The export has no pricing_unit column, so this is a keyword rule
    reverse-engineered from the template (100% match on its 60,304 rows)."""
    u = (usage_type or "").lower()
    if "token" in u:
        return "1K tokens" if "per 1K tokens" in (desc or "") else "1M tokens"
    if "gb-hours" in u or u.endswith(":memory"):
        return "GB-hours"
    if "vcpu" in u:
        return "vCPU-hours"
    if "lcu" in u:
        return "LCU-hours"
    if "bytes" in u or "bytehr" in u or "bytehour" in u:
        return "GB"
    if "storage" in u:
        return "GB-month"
    if "request" in u:
        return "requests"
    if "hour" in u:
        return "hours"
    return "unidad CUR"


def service_name(code, servicecode):
    base = REF["product_base_names"].get(code, code)
    return "AWS Data Transfer - " + base if servicecode == DATA_TRANSFER else base


def model_name(servicio, code, usage_type):
    if servicio.endswith("(Amazon Bedrock Edition)"):
        return servicio
    if code == "AmazonBedrock":
        m = re.match(r"^[A-Z0-9]+-(.+)-(?:input|output)-tokens$", usage_type or "")
        if m:
            return m.group(1)
    return None


def attribution_rule(acct):
    r = REF["accounts"][acct]
    if r["conditional"]:
        return f"Cuenta condicionada + {REF['conditional_project']}"
    if "factor" in r:
        return f"Cuenta directa x {r['factor']}"
    if "from" in r:
        return f"Cuenta directa desde {r['from']}"
    return "Cuenta directa"


def build_detail(raw, start, end_excl, trm, fee, warn):
    d = raw[(raw.line_item_usage_start_date >= start) & (raw.line_item_usage_start_date < end_excl)]
    d = d[d.line_item_line_item_type.isin(KEEP_TYPES) & (d.line_item_unblended_cost != 0)].reset_index(drop=True)
    d["acct"] = d.line_item_usage_account_id.astype(object)

    known = set(REF["accounts"])
    other = d[~d.acct.isin(known)]
    if len(other):
        warn.append(f"{other.acct.nunique()} accounts of the CUR are not in reference.json and were excluded "
                    f"({len(other):,} rows, USD {other.line_item_unblended_cost.sum():,.2f}): "
                    + ", ".join(sorted(other.acct.unique())))
    d = d[d.acct.isin(known)].copy()

    tags = d.resource_tags.map(lambda r: dict(r) if r is not None else {})
    d["Proyecto"] = tags.map(lambda t: t.get("user_project_id"))
    d["Aplicación"] = tags.map(lambda t: t.get("user_app"))
    d["Centro de costo"] = tags.map(lambda t: t.get("user_cost_center"))

    cond = d.acct.map(lambda a: REF["accounts"][a]["conditional"])
    d = d[~cond | (d["Proyecto"] == REF["conditional_project"])].copy()

    # Costo Atribuible (QuickSight dashboard): unblended * factor, 0 before the account's "from" date.
    d["attr"] = d.line_item_unblended_cost * d.acct.map(lambda a: REF["accounts"][a].get("factor", 1.0))
    d.loc[d.line_item_usage_start_date < d.acct.map(lambda a: pd.Timestamp(REF["accounts"][a].get("from", "1970-01-01"))),
          "attr"] = 0.0

    d = d.sort_values(["line_item_usage_start_date", "acct", "line_item_product_code",
                       "line_item_usage_type", "line_item_operation"], kind="mergesort")
    obj = lambda s: s.astype(object).where(s.notna(), None)  # noqa: E731
    code, sc = obj(d.line_item_product_code), obj(d.product_servicecode)
    out = pd.DataFrame(index=d.index)
    out["Fecha y hora de inicio"] = d.line_item_usage_start_date
    out["Fecha y hora de fin"] = d.line_item_usage_end_date
    out["Cuenta AWS"] = d.acct
    out["Nombre de la cuenta"] = d.acct.map(lambda a: REF["accounts"][a]["name"])
    out["Ambiente"] = d.acct.map(lambda a: REF["accounts"][a]["ambiente"])
    out["Servicio AWS"] = [service_name(c, s) for c, s in zip(code, sc)]
    out["Modelo o detalle del servicio"] = [model_name(f, c, u) for f, c, u in
                                            zip(out["Servicio AWS"], code, obj(d.line_item_usage_type))]
    out["Código de producto AWS"] = code
    out["Código de servicio AWS"] = sc
    out["Tipo de cargo AWS"] = obj(d.line_item_line_item_type)
    out["Concepto facturado por AWS"] = obj(d.line_item_usage_type)
    out["Operación AWS"] = obj(d.line_item_operation)
    out["Descripción del cargo AWS"] = obj(d.line_item_line_item_description)
    out["Cantidad reportada por AWS"] = d.line_item_usage_amount
    out["Unidad de facturación"] = [usage_unit(u, x) for u, x in
                                    zip(obj(d.line_item_usage_type), obj(d.line_item_line_item_description))]
    out["Moneda original"] = obj(d.line_item_currency_code)
    out["Rubro"] = [PRUEBAS if REF["accounts"][a]["rubro_pruebas"]
                    else PROCESAMIENTO if cc == REF["processing_cost_center"] else PROD
                    for a, cc in zip(d.acct, d["Centro de costo"])]
    out["Costo AWS (USD)"] = d.attr
    out["Tasa de cambio (COP/USD)"] = trm
    out["Costo AWS (COP)"] = out["Costo AWS (USD)"] * trm
    out["Tarifa de licenciamiento"] = fee
    out["Costo licenciamiento (COP)"] = (out["Costo AWS (COP)"] * fee).where(out["Rubro"] == PROCESAMIENTO, 0.0)
    out["Total facturable (COP)"] = out["Costo AWS (COP)"] + out["Costo licenciamiento (COP)"]
    out["Regla de atribución"] = d.acct.map(attribution_rule)
    out["Centro de costo"] = d["Centro de costo"]
    out["Proyecto"] = d["Proyecto"]
    out["Aplicación"] = d["Aplicación"]
    out["Categoria principal"] = [
        "Networking" if s == DATA_TRANSFER else REF["categories"].get(f, "Sin clasificar")
        for f, s in zip(out["Servicio AWS"], sc)]
    out = out[DETAIL_COLS].reset_index(drop=True)
    out.attrs["raw_usd"] = float(d.line_item_unblended_cost.sum())

    unk = sorted(set(out.loc[out["Categoria principal"] == "Sin clasificar", "Servicio AWS"]))
    if unk:
        warn.append("Services without a Categoria in reference.json (category 'Sin clasificar'): " + "; ".join(unk))
    nonusd = out.loc[out["Moneda original"] != "USD", "Moneda original"].unique()
    if len(nonusd):
        warn.append(f"Non-USD currency codes found: {list(nonusd)}")
    return out


def with_totals(df, trm, fee):
    df["trm"], df["fee"] = trm, fee
    df["cop"] = df["usd"] * trm
    df["lic"] = (df["cop"] * fee).where(df["Rubro"] == PROCESAMIENTO, 0.0)
    df["tot"] = df["cop"] + df["lic"]
    return df.sort_values("tot", ascending=False, kind="mergesort").reset_index(drop=True)


def build_aggregates(detail, trm, fee):
    g = detail.copy()
    g = g.astype(object).where(g.notna(), None)
    g["Costo AWS (USD)"] = detail["Costo AWS (USD)"]
    g["Cantidad reportada por AWS"] = detail["Cantidad reportada por AWS"]

    # Por_cuenta
    k = ["Cuenta AWS", "Nombre de la cuenta", "Ambiente", "Rubro"]
    pc = g.groupby(k, dropna=False)["Costo AWS (USD)"].sum().rename("usd").reset_index()
    pc = with_totals(pc, trm, fee)

    # Por_servicio (keeps the template's partial translation of categories)
    ps_src = g.copy()
    ps_src["Categoria principal"] = ps_src["Categoria principal"].replace(CAT_PS)
    k = ["Servicio AWS", "Código de producto AWS", "Código de servicio AWS", "Rubro", "Categoria principal"]
    ps = ps_src.groupby(k, dropna=False)["Costo AWS (USD)"].sum().rename("usd").reset_index()
    ps = with_totals(ps, trm, fee)

    # Cuenta_servicio_uso: the template replaced the category word in every text field of the
    # rows whose category is Storage or Networking, and relabelled the other categories.
    cu_src = g.copy()
    txt = ["Nombre de la cuenta", "Servicio AWS", "Modelo o detalle del servicio",
           "Concepto facturado por AWS", "Operación AWS", "Unidad de facturación"]
    for word in ("Storage", "Networking"):
        mk = cu_src["Categoria principal"] == word
        for c in txt:
            cu_src.loc[mk, c] = cu_src.loc[mk, c].map(lambda v: v.replace(word, CAT_CUS[word]) if v else v)
    cu_src["Categoria principal"] = cu_src["Categoria principal"].replace(CAT_CUS)
    k = ["Cuenta AWS", "Nombre de la cuenta", "Servicio AWS", "Modelo o detalle del servicio",
         "Concepto facturado por AWS", "Operación AWS", "Unidad de facturación", "Rubro",
         "Categoria principal"]
    cu = cu_src.groupby(k, dropna=False).agg(qty=("Cantidad reportada por AWS", "sum"),
                                             usd=("Costo AWS (USD)", "sum")).reset_index()
    cu = with_totals(cu, trm, fee)
    return pc, ps, cu


# ----------------------------------------------------------------------------- Analisis sheet

def collate(s):
    """Excel-like sort key: case and accent insensitive."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().casefold()


def analisis_values(cu):
    cats = sorted(cu["Categoria principal"].unique(), key=collate)
    rows = []
    for c in cats:
        s = cu[cu["Categoria principal"] == c]
        b = s.loc[s.Rubro.isin([PROCESAMIENTO, PROD]), "tot"].sum()
        t = s["tot"].sum()
        rows.append((c, b, t - b, b + (t - b)))
    ordered = sorted(rows, key=lambda r: -r[3])  # SORT(...,4,-1) is stable
    return rows, ordered


# ----------------------------------------------------------------------------- XML helpers

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def num(v):
    if isinstance(v, datetime):
        v = (v - datetime(1899, 12, 30)).total_seconds() / 86400.0
    return repr(float(v)) if not isinstance(v, int) else str(v)


def cell(ref, v, s=None, f=None):
    """One <c> element. v None -> omitted (unless a formula); str -> inline string."""
    sa = f' s="{s}"' if s else ""
    if f is not None:
        fx = f"<f>{escape(f)}</f>"
        if isinstance(v, str):
            return f'<c r="{ref}"{sa} t="str">{fx}<v>{escape(_CTRL.sub("", v))}</v></c>'
        return f'<c r="{ref}"{sa}>{fx}<v>{num(v)}</v></c>'
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if isinstance(v, str):
        t = escape(_CTRL.sub("", v))
        sp = ' xml:space="preserve"' if v != v.strip() else ""
        return f'<c r="{ref}"{sa} t="inlineStr"><is><t{sp}>{t}</t></is></c>'
    return f'<c r="{ref}"{sa}><v>{num(v)}</v></c>'


class Err(str):
    """Marker for an error value such as #N/A."""


def rebuild_cell(ref, attrs, inner, value):
    attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
    fm = re.search(r"<f[^>]*?(?:/>|>.*?</f>)", inner or "", re.S)
    f = fm.group(0) if fm else ""
    if isinstance(value, Err):
        return f'<c r="{ref}"{attrs} t="e">{f}<v>{escape(value)}</v></c>'
    if isinstance(value, str):
        return f'<c r="{ref}"{attrs} t="str">{f}<v>{escape(_CTRL.sub("", value))}</v></c>'
    if value is None:
        return f'<c r="{ref}"{attrs} t="str">{f}<v></v></c>'
    return f'<c r="{ref}"{attrs}>{f}<v>{num(value)}</v></c>'


_CELL = re.compile(r'<c r="([A-Z]+\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)


def patch_cells(xml, values, only_formulas=True):
    def sub(m):
        ref = m.group(1)
        if ref not in values:
            return m.group(0)
        if only_formulas and "<f" not in (m.group(3) or ""):
            return m.group(0)
        return rebuild_cell(ref, m.group(2), m.group(3), values[ref])
    return _CELL.sub(sub, xml)


def strip_cached(xml):
    """Remove cached <v> of formula cells so LibreOffice has to calculate them."""
    def sub(m):
        inner = m.group(3) or ""
        if "<f" not in inner:
            return m.group(0)
        attrs = re.sub(r'\s+t="[^"]*"', "", m.group(2))
        fm = re.search(r"<f[^>]*?(?:/>|>.*?</f>)", inner, re.S).group(0)
        return f'<c r="{m.group(1)}"{attrs}>{fm}</c>'
    return _CELL.sub(sub, xml)


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def sheet_parts(xml, last_row):
    """Split a template sheet into (head, header_row_xml, row2_styles, tail), with stale
    filter state and scroll position reset."""
    i, j = xml.index("<sheetData>"), xml.index("</sheetData>")
    head, body, tail = xml[:i], xml[i + 11:j], xml[j + 12:]
    header = re.search(r'<row r="1".*?</row>', body, re.S).group(0)
    r2 = re.search(r'<row r="2".*?</row>', body, re.S)
    styles = {m.group(1): m.group(2) for m in re.finditer(r'<c r="([A-Z]+)2"(?: s="(\d+)")?', r2.group(0))}
    ncols = len(re.findall(r"<c r=", header))
    last_col = col_letter(ncols - 1)
    head = re.sub(r'<sheetPr filterMode="1">', "<sheetPr>", head)
    head = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:{last_col}{last_row}"/>', head)
    head = re.sub(r'topLeftCell="[A-Z]+\d+"', 'topLeftCell="A2"', head)
    head = re.sub(r'<selection pane="bottomLeft" activeCell="[A-Z]+\d+" sqref="[A-Z]+\d+"/>',
                  '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>', head)
    tail = re.sub(r'<autoFilter ref="[^"]*"([^>]*?)(?:/>|>.*?</autoFilter>)',
                  rf'<autoFilter ref="A1:{last_col}{last_row}"\1/>', tail, flags=re.S)
    return head, header, styles, tail, last_col


def write_sheet(zout, name, template_xml, df, specs):
    """Stream a regenerated sheet. specs: list of (column letter, kind, arg, df column).
    kind 'v' = value from df column arg; 'f' = formula text arg (with {r}) cached from df column."""
    last = len(df) + 1
    head, header, styles, tail, _ = sheet_parts(template_xml, last)
    with zout.open(name, "w") as fh:
        fh.write((head + "<sheetData>" + header).encode("utf-8"))
        cols = [(L, k, a, c, styles.get(L)) for L, k, a, c in specs]
        buf = []
        series = {c: df[c].tolist() for _, _, _, c, _ in cols}
        for i in range(len(df)):
            r = i + 2
            cells = []
            for L, k, a, c, s in cols:
                v = series[c][i]
                if isinstance(v, pd.Timestamp):
                    v = (v - pd.Timestamp("1899-12-30")).total_seconds() / 86400.0
                if k == "f":
                    cells.append(cell(f"{L}{r}", v, s, f=a.format(r=r)))
                else:
                    cells.append(cell(f"{L}{r}", v, s))
            buf.append(f'<row r="{r}">' + "".join(cells) + "</row>")
            if len(buf) >= 2000:
                fh.write("".join(buf).encode("utf-8"))
                buf = []
        fh.write(("".join(buf) + "</sheetData>" + tail).encode("utf-8"))


def formula_cols(rate_col, usd, name_rubro, cop, licc, tot, fee_col):
    """Specs of the five formula columns shared by the aggregate sheets."""
    return [(rate_col, "f", "Resumen!$C$27", "trm"),
            (cop, "f", f"{usd}{{r}}*{rate_col}{{r}}", "cop"),
            (fee_col, "f", "Resumen!$C$28", "fee"),
            (licc, "f", f'IF({name_rubro}{{r}}="Procesamiento",{cop}{{r}}*{fee_col}{{r}},0)', "lic"),
            (tot, "f", f"SUM({cop}{{r}},{licc}{{r}})", "tot")]


def detail_specs():
    v = lambda L, c: (L, "v", c, c)  # noqa: E731
    return ([v("A", DETAIL_COLS[0]), v("B", DETAIL_COLS[1]), v("C", DETAIL_COLS[2]), v("D", DETAIL_COLS[3]),
             v("E", DETAIL_COLS[4]), v("F", DETAIL_COLS[5]), v("G", DETAIL_COLS[6]), v("H", DETAIL_COLS[7]),
             v("I", DETAIL_COLS[8]), v("J", DETAIL_COLS[9]), v("K", DETAIL_COLS[10]), v("L", DETAIL_COLS[11]),
             v("M", DETAIL_COLS[12]), v("N", DETAIL_COLS[13]), v("O", DETAIL_COLS[14]), v("P", DETAIL_COLS[15]),
             v("Q", DETAIL_COLS[16]), v("R", DETAIL_COLS[17]),
             ("S", "f", "Resumen!$C$27", DETAIL_COLS[18]),
             ("T", "f", "R{r}*S{r}", DETAIL_COLS[19]),
             ("U", "f", "Resumen!$C$28", DETAIL_COLS[20]),
             ("V", "f", 'IF(Q{r}="Procesamiento",T{r}*U{r},0)', DETAIL_COLS[21]),
             ("W", "f", "SUM(T{r},V{r})", DETAIL_COLS[22]),
             v("X", DETAIL_COLS[23]), v("Y", DETAIL_COLS[24]), v("Z", DETAIL_COLS[25]),
             v("AA", DETAIL_COLS[26]), v("AB", DETAIL_COLS[27])])


# ----------------------------------------------------------------------------- LibreOffice

def lo_recalc(src_xlsx, soffice, workdir):
    """Convert with headless LibreOffice and return {sheet: {ref: value}} for the sheets we need."""
    import openpyxl
    out = Path(workdir) / "lo_out"
    out.mkdir(exist_ok=True)
    cmd = [soffice, f"-env:UserInstallation=file://{workdir}/lo_profile", "--headless",
           "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(out), str(src_xlsx)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    wb = openpyxl.load_workbook(out / Path(src_xlsx).name, read_only=True, data_only=True)
    vals = {}
    for name in ("Analisis de Costos",):
        d = {}
        for row in wb[name].iter_rows():
            for c in row:
                if c.value is None and c.data_type != "e":
                    continue
                d[c.coordinate] = Err(c.value) if c.data_type == "e" else c.value
        vals[name] = d
    wb.close()
    return vals


def refresh_chart_cache(xml, sheet_values):
    """Rewrite c:strCache / c:numCache next to each c:f so charts are right before a recalc."""
    def cells_of(ref):
        sheet, rng = ref.rsplit("!", 1)
        a, _, b = rng.replace("$", "").partition(":")
        ca, ra = re.match(r"([A-Z]+)(\d+)", a).groups()
        cb, rb = re.match(r"([A-Z]+)(\d+)", b or a).groups()
        return sheet.strip("'"), [f"{ca}{r}" for r in range(int(ra), int(rb) + 1)]

    def sub(m):
        kind, ref, body = m.group("k"), m.group("ref"), m.group("body")
        sheet, refs = cells_of(ref)
        vals = sheet_values.get(sheet)
        if vals is None:
            return m.group(0)
        fmt = re.search(r"<c:formatCode>.*?</c:formatCode>", body)
        pts = []
        for i, r in enumerate(refs):
            v = vals.get(r)
            if v is None or isinstance(v, Err):
                continue
            if isinstance(v, datetime):
                v = (v - datetime(1899, 12, 30)).total_seconds() / 86400.0
            if kind == "num":
                if isinstance(v, str):
                    continue
                v = num(v)
            elif isinstance(v, (int, float)):
                v = f"{v:.1f}"
            pts.append(f'<c:pt idx="{i}"><c:v>{escape(str(v))}</c:v></c:pt>')
        head = fmt.group(0) if fmt and kind == "num" else ""
        return (f"<c:f>{ref}</c:f><c:{kind}Cache>{head}<c:ptCount val=\"{len(refs)}\"/>"
                + "".join(pts) + f"</c:{kind}Cache>")

    return re.sub(r"<c:f>(?P<ref>[^<]*)</c:f><c:(?P<k>num|str)Cache>(?P<body>.*?)</c:(?P=k)Cache>",
                  sub, xml, flags=re.S)


# ----------------------------------------------------------------------------- main

def build_package(args, detail, pc, ps, cu, warn):
    n = len(detail)
    last = n + 1
    trm, fee = args.trm, args.licensing
    tpl = zipfile.ZipFile(args.template)
    names = tpl.namelist()
    text = lambda p: tpl.read(p).decode("utf-8")  # noqa: E731

    # --- small sheets patched in memory
    # Resumen: ranges, parameters, cached values
    s1 = text("xl/worksheets/sheet1.xml").replace("$60305", f"${last}")
    ccop = detail["Costo AWS (COP)"]
    rub = detail["Rubro"]
    usd_total = float(detail["Costo AWS (USD)"].sum())
    res_vals = {
        "B6": float(ccop[rub == PROCESAMIENTO].sum()), "E6": float(ccop[rub != PROCESAMIENTO].sum()),
        "H6": float(detail["Costo licenciamiento (COP)"].sum()), "K6": float(detail["Total facturable (COP)"].sum()),
        "B10": float(ccop[rub == PRUEBAS].sum()), "H10": float(ccop[rub == PROD].sum()),
        "F27": usd_total, "F28": usd_total * trm}
    s1 = patch_cells(s1, res_vals)
    s1 = patch_cells(s1, {"C27": trm, "C28": fee}, only_formulas=False)

    # Analisis: python-computed cached values (rows 2..23 of the fixed spill ranges)
    s6 = text("xl/worksheets/sheet6.xml")
    rows, ordered = analisis_values(cu)
    if len(rows) != 22:
        warn.append(f"Analisis sheet has a fixed 22-row range but the data has {len(rows)} categories.")
    av = {}
    for i in range(22):
        r = i + 2
        c, b, o, t = rows[i] if i < len(rows) else ("", 0.0, 0.0, 0.0)
        av.update({f"A{r}": c, f"B{r}": b, f"C{r}": o, f"D{r}": t})
        if i < len(ordered):
            av.update({f"F{r}": ordered[i][0], f"G{r}": ordered[i][1], f"H{r}": ordered[i][2], f"I{r}": ordered[i][3]})
    s6 = patch_cells(s6, av, only_formulas=False)

    # Analisis de Costos: numeric constant overrides, then LibreOffice for the cached values
    s2 = text("xl/worksheets/sheet2.xml")
    overrides = dict(args.ac_set)
    if args.audits is not None:
        overrides.update({f"{c}3": args.audits for c in "OPQRSTUVWX"})
    for ref, v in overrides.items():
        m = re.search(rf'<c r="{ref}"[^>]*?>(.*?)</c>', s2, re.S)
        if not m or "<f" in m.group(1):
            sys.exit(f"ERROR: --set {ref}: not a numeric constant cell of 'Analisis de Costos'")
        s2 = patch_cells(s2, {ref: float(v)}, only_formulas=False)

    sheets_small = {"xl/worksheets/sheet1.xml": s1, "xl/worksheets/sheet2.xml": s2, "xl/worksheets/sheet6.xml": s6}

    # --- workbook level
    wbx = text("xl/workbook.xml")
    ref_sheet = {"Cuenta_servicio_uso": (len(cu) + 1, "P"), "Detalle_facturado": (last, "AB"),
                 "Por_cuenta": (len(pc) + 1, "J"), "Por_servicio": (len(ps) + 1, "K")}
    for sh, (lr, lc) in ref_sheet.items():
        wbx = re.sub(rf"{sh}!\$A\$1:\$[A-Z]+\$\d+", f"{sh}!$A$1:${lc}${lr}", wbx)
    wbx = wbx.replace('<calcPr calcId="191028"/>', '<calcPr calcId="191028" fullCalcOnLoad="1"/>')
    rels = re.sub(r'<Relationship Id="[^"]*" Type="[^"]*/calcChain" Target="calcChain.xml"/>', "", text("xl/_rels/workbook.xml.rels"))
    ctypes = re.sub(r'<Override PartName="/xl/calcChain.xml"[^>]*/>', "", text("[Content_Types].xml"))

    generated = {"xl/worksheets/sheet3.xml": (pc, [
        ("A", "v", "Cuenta AWS", "Cuenta AWS"), ("B", "v", "Nombre de la cuenta", "Nombre de la cuenta"),
        ("C", "v", "Ambiente", "Ambiente"), ("D", "v", "Rubro", "Rubro"), ("E", "v", "usd", "usd")]
        + formula_cols("F", "E", "D", "G", "I", "J", "H")),
        "xl/worksheets/sheet4.xml": (ps, [
        ("A", "v", "Servicio AWS", "Servicio AWS"), ("B", "v", "Código de producto AWS", "Código de producto AWS"),
        ("C", "v", "Código de servicio AWS", "Código de servicio AWS"), ("D", "v", "Rubro", "Rubro"),
        ("E", "v", "usd", "usd")] + formula_cols("F", "E", "D", "G", "I", "J", "H")
        + [("K", "v", "Categoria principal", "Categoria principal")]),
        "xl/worksheets/sheet5.xml": (cu, [
        ("A", "v", "Cuenta AWS", "Cuenta AWS"), ("B", "v", "Nombre de la cuenta", "Nombre de la cuenta"),
        ("C", "v", "Servicio AWS", "Servicio AWS"), ("D", "v", "Modelo o detalle del servicio", "Modelo o detalle del servicio"),
        ("E", "v", "Concepto facturado por AWS", "Concepto facturado por AWS"),
        ("F", "v", "Operación AWS", "Operación AWS"), ("G", "v", "Unidad de facturación", "Unidad de facturación"),
        ("H", "v", "Rubro", "Rubro"), ("I", "v", "qty", "qty"), ("J", "v", "usd", "usd")]
        + formula_cols("K", "J", "H", "L", "N", "O", "M")
        + [("P", "v", "Categoria principal", "Categoria principal")]),
        "xl/worksheets/sheet7.xml": (detail, detail_specs())}

    def write_package(path, small, charts):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for nm in names:
                if nm == "xl/calcChain.xml":
                    continue
                if nm in generated:
                    df, specs = generated[nm]
                    write_sheet(z, nm, text(nm), df, specs)
                elif nm in small:
                    z.writestr(nm, small[nm])
                elif nm == "xl/workbook.xml":
                    z.writestr(nm, wbx)
                elif nm == "xl/_rels/workbook.xml.rels":
                    z.writestr(nm, rels)
                elif nm == "[Content_Types].xml":
                    z.writestr(nm, ctypes)
                elif nm in charts:
                    z.writestr(nm, charts[nm])
                else:
                    z.writestr(nm, tpl.read(nm))

    out = Path(args.output)
    if out.resolve() == Path(args.template).resolve() or out.name.startswith("Reporte Costos - 24 Julio"):
        sys.exit("ERROR: refusing to write over the template")
    out.parent.mkdir(parents=True, exist_ok=True)

    soffice = shutil.which(args.soffice)
    ac_vals = None
    if soffice:
        with tempfile.TemporaryDirectory(prefix="costrep_") as tmp:
            stripped = {k: (strip_cached(v) if k.endswith(("sheet2.xml",)) else v) for k, v in sheets_small.items()}
            inter = Path(tmp) / "intermediate.xlsx"
            print("Recalculating Analisis de Costos with LibreOffice (headless)...")
            write_package(inter, stripped, {})
            try:
                ac_vals = lo_recalc(inter, soffice, tmp)["Analisis de Costos"]
            except Exception as e:  # noqa: BLE001
                warn.append(f"LibreOffice recalculation failed ({type(e).__name__}); cached values of "
                            "'Analisis de Costos' are stale until Excel recalculates.")
    else:
        warn.append("soffice not found: cached values of 'Analisis de Costos' (and its charts) are stale "
                    "until the file is opened in Excel (fullCalcOnLoad is set).")

    charts = {}
    if ac_vals is not None:
        sheets_small["xl/worksheets/sheet2.xml"] = patch_cells(s2, ac_vals)
        values = {"Analisis de Costos": ac_vals,
                  "Analisis": {k: v for k, v in av.items()}}
        values["Analisis"].update({f"{c}1": h for c, h in zip("ABCDFGHI", ["Categoría", "Procesamiento + Plataforma Producción y Soporte", "Otros rubros", "Total", "Categoría", "Procesamiento + Plataforma Producción y Soporte", "Otros rubros", "Total"])})
        for nm in names:
            if re.match(r"xl/charts/chart\d+\.xml$", nm):
                charts[nm] = refresh_chart_cache(text(nm), values)
        check_coverage(detail, ac_vals, warn, args)
    write_package(out, sheets_small, charts)
    return out


def check_coverage(detail, v, warn, args):
    """The ranked tables of Analisis de Costos use fixed label lists; flag data they cannot see."""
    def labels(col, r1, r2):
        return {v.get(f"{col}{r}") for r in range(r1, r2 + 1)} - {None}
    for title, col, lab in [("Servicio AWS", "Servicio AWS", labels("AK", 13, 76)),
                            ("Categoria principal", "Categoria principal", labels("AO", 13, 34)),
                            ("Nombre de la cuenta", "Nombre de la cuenta", labels("AS", 13, 20))]:
        miss = detail[~detail[col].isin(lab)]
        if len(miss):
            warn.append(f"Analisis de Costos label list for '{title}' misses {miss[col].nunique()} values "
                        f"(COP {miss['Total facturable (COP)'].sum():,.2f} excluded from that table): "
                        + "; ".join(sorted(miss[col].unique())[:10]))
    days = (detail["Fecha y hora de inicio"].dt.normalize().nunique())
    if days > 34:
        warn.append(f"The window has {days} days but the daily series of Analisis de Costos holds 34 (rows 13-46 of the Rubro series).")
    if len(detail) + 1 > 100000:
        warn.append("Detalle_facturado has more than 99,999 rows; Analisis de Costos formulas stop at row 100000.")


def parse_args():
    p = argparse.ArgumentParser(description="Regenerate the cost report .xlsx from the prod CUR (read-only S3).")
    p.add_argument("--start", required=True, help="first day, YYYY-MM-DD (usage start >= 00:00)")
    p.add_argument("--end", required=True, help="last day inclusive, YYYY-MM-DD (usage start < next day 00:00)")
    p.add_argument("--profile", default="ADR-PROD-MEDICALAUDIT-SENSITIVE")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--bucket", default="adr-prod-medicalaudit-datalake")
    p.add_argument("--prefix", default="costs/adr-prod-medicalaudit-cost-export-938536499966/data/")
    p.add_argument("--output", help='default: "Reporte Costos - <start> a <end>.xlsx" in the working dir')
    p.add_argument("--template", default=str(HERE / "assets" / "template_skeleton.xlsx"))
    p.add_argument("--trm", type=float, default=3655.16, help="Resumen!C27, COP per USD")
    p.add_argument("--licensing", type=float, default=0.76, help="Resumen!C28, licensing rate on Procesamiento")
    p.add_argument("--audits", type=float, default=None,
                   help="Analisis de Costos!O3:X3 'CANTIDAD DE AUDITORIAS' (template: 3241)")
    p.add_argument("--set", dest="ac_set", action="append", default=[], metavar="CELL=VALUE",
                   help="override a numeric constant of 'Analisis de Costos' (e.g. O8=3655, T6=10420000, U8=361051863, "
                        "U12=3241, V12=5250); repeatable")
    p.add_argument("--soffice", default="soffice", help="LibreOffice binary used to refresh cached values")
    a = p.parse_args()
    try:
        a.ac_set = {k.strip().upper(): float(v) for k, v in (s.split("=", 1) for s in a.ac_set)}
    except ValueError:
        p.error("--set expects CELL=VALUE with a numeric VALUE")
    if not a.profile:
        p.error("--profile is required (no fallback to the default profile)")
    a.output = a.output or f"Reporte Costos - {a.start} a {a.end}.xlsx"
    return a


def main():
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d")
    end_excl = datetime.strptime(args.end, "%Y-%m-%d") + timedelta(days=1)
    if end_excl <= start:
        sys.exit("ERROR: --end is before --start")
    months, d = [], start.replace(day=1)
    while d < end_excl:
        months.append(d.strftime("%Y-%m"))
        d = (d + timedelta(days=32)).replace(day=1)

    print(f"Reading CUR s3://{args.bucket}/{args.prefix} periods {months} (profile {args.profile}, read-only)")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    raw = read_cur(session, args.bucket, args.prefix, months)

    warn = []
    detail = build_detail(raw, pd.Timestamp(start), pd.Timestamp(end_excl), args.trm, args.licensing, warn)
    if detail.empty:
        sys.exit("ERROR: no rows after filtering")
    pc, ps, cu = build_aggregates(detail, args.trm, args.licensing)
    out = build_package(args, detail, pc, ps, cu, warn)

    usd = detail["Costo AWS (USD)"].sum()
    print(f"\nWrote {out}")
    print(f"  Detalle_facturado rows : {len(detail):,}   Por_cuenta {len(pc)}  Por_servicio {len(ps)}  Cuenta_servicio_uso {len(cu)}")
    print(f"  Window actually covered: {detail['Fecha y hora de inicio'].min()} .. {detail['Fecha y hora de inicio'].max()}")
    print(f"  Costo AWS USD (atribuible)   : {usd:,.2f}   (CUR sin ajuste: {detail.attrs['raw_usd']:,.2f})")
    print(f"  Costo AWS COP          : {detail['Costo AWS (COP)'].sum():,.2f}")
    print(f"  Licenciamiento COP     : {detail['Costo licenciamiento (COP)'].sum():,.2f}")
    print(f"  Total facturable COP   : {detail['Total facturable (COP)'].sum():,.2f}")
    for w in warn:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
