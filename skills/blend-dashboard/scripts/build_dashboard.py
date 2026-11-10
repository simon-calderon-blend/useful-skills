#!/usr/bin/env python3
"""Build a self-contained Blend dashboard (one HTML file) from a JSON spec.

Usage: build_dashboard.py SPEC.json OUT.html [--dark]
SPEC fields (see SKILL.md): title, subtitle, lang, updated, source, illustrative, dark, mode
("dashboard" | "table"), columns, rows | csv, kpis, filters, charts, table.
Rows come from spec["rows"] (list of objects) or spec["csv"] (path relative to the spec; header row required).
Reuses blend-web-core (tokens, components, logo, PP Telegraf embedded by default) through blend_web.build. Stdlib only.
"""
import argparse, csv, html, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT.parent / "blend-web-core" / "scripts"))
from blend_web import build  # noqa: E402

AGGS = {"count", "sum", "avg", "min", "max", "distinct"}
CHARTS = {"bar", "hbar", "line"}
PII_NAMES = re.compile(r"(cedula|cédula|documento|nit|email|correo|telefono|teléfono|phone|nombre_paciente|patient)", re.I)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_rows(spec, base):
    if "csv" in spec:
        with open(base / spec["csv"], newline="", encoding="utf-8-sig") as f:
            return [dict(r) for r in csv.DictReader(f)]
    return spec["rows"]


def infer_columns(rows, given):
    given = {c["key"]: c for c in (given or [])}
    keys = list(given) or list(rows[0].keys())
    cols = []
    for k in keys:
        c = dict(given.get(k, {"key": k}))
        vals = [r.get(k) for r in rows if r.get(k) not in (None, "")]
        c.setdefault("label", k.replace("_", " ").capitalize())
        if "type" not in c:
            if vals and all(num(v) is not None for v in vals):
                c["type"] = "num"
            elif vals and all(re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", str(v)) for v in vals):
                c["type"] = "date"
            elif vals and len(set(vals)) <= max(12, len(vals) // 10):
                c["type"] = "cat"
            else:
                c["type"] = "text"
        c.setdefault("decimals", 0)
        cols.append(c)
    return cols


def coerce(rows, cols):
    out = []
    for r in rows:
        o = {}
        for c in cols:
            v = r.get(c["key"], "")
            if c["type"] == "num":
                n = num(v)
                v = "" if n is None else (int(n) if n == int(n) else n)
            o[c["key"]] = v
        out.append(o)
    return out


def agg(rows, kind, field):
    if kind == "count":
        return len(rows)
    if kind == "distinct":
        return len({r[field] for r in rows})
    v = [num(r[field]) for r in rows if num(r[field]) is not None]
    if not v:
        return 0
    return {"sum": sum(v), "avg": sum(v) / len(v), "min": min(v), "max": max(v)}[kind]


def fmt(v, dec=0, pre="", suf=""):
    return f"{pre}{v:,.{dec}f}{suf}"


def e(s):
    return html.escape(str(s), quote=True)


def check_spec(spec, cols, rows):
    keys = {c["key"] for c in cols}
    numeric = {c["key"] for c in cols if c["type"] == "num"}
    for k in keys:
        if PII_NAMES.search(k):
            print(f"WARN column '{k}' looks like PII: drop it unless the data is public", file=sys.stderr)
    for k in spec.get("kpis", []):
        if k["agg"] not in AGGS:
            sys.exit(f"kpi {k['id']}: agg must be one of {sorted(AGGS)}")
        if k["agg"] != "count" and k.get("field") not in keys:
            sys.exit(f"kpi {k['id']}: unknown field {k.get('field')}")
        if k["agg"] in {"sum", "avg", "min", "max"} and k["field"] not in numeric:
            sys.exit(f"kpi {k['id']}: field {k['field']} is not numeric")
    for c in spec.get("charts", []):
        if c["type"] not in CHARTS:
            sys.exit(f"chart {c['id']}: type must be one of {sorted(CHARTS)}")
        if c["x"] not in keys or (c.get("series") and c["series"] not in keys):
            sys.exit(f"chart {c['id']}: unknown x/series column")
        y = c["y"]
        if y["agg"] not in AGGS or (y["agg"] != "count" and y.get("field") not in numeric):
            sys.exit(f"chart {c['id']}: y needs agg and a numeric field")
        if c.get("series") and len({r[c["series"]] for r in rows}) > 5:
            sys.exit(f"chart {c['id']}: more than 5 series; fold the tail into 'Other' or filter first")


def render(spec, base, dark=False):
    rows0 = load_rows(spec, base)
    cols = infer_columns(rows0, spec.get("columns"))
    rows = coerce(rows0, cols)
    check_spec(spec, cols, rows)
    mode = spec.get("mode", "dashboard")
    dark = dark or spec.get("dark", False)
    lang = spec.get("lang", "en")
    slug = re.sub(r"[^a-z0-9]+", "-", spec["title"].lower()).strip("-")
    data = {"meta": {"slug": slug, "updated": spec.get("updated", ""), "illustrative": bool(spec.get("illustrative"))},
            "columns": cols, "rows": rows,
            "spec": {"charts": spec.get("charts", []) if mode == "dashboard" else [], "table": spec.get("table", {})}}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    parts = []
    badge = '<span class="d-badge">Illustrative</span>' if spec.get("illustrative") else ""
    theme = '<button class="d-theme" id="d-theme" type="button">Light / dark</button>' if dark else ""
    sub = f"<p>{e(spec['subtitle'])}</p>" if spec.get("subtitle") else ""
    upd = f'<p class="b-eyebrow">Updated {e(spec["updated"])}</p>' if spec.get("updated") else ""
    parts.append(f'<main class="d-wrap"><div class="d-head"><div>{upd}<h1>{e(spec["title"])}{badge}</h1>{sub}</div>{theme}</div>')

    if spec.get("kpis"):
        t = []
        for k in spec["kpis"]:
            dec, pre, suf = k.get("decimals", 0), k.get("prefix", ""), k.get("suffix", "")
            v = fmt(agg(rows, k["agg"], k.get("field")), dec, pre, suf)
            note = f'<span class="n">{e(k["note"])}</span>' if k.get("note") else ""
            t.append(f'<div class="b-card b-kpi" data-kpi="{e(k["id"])}" data-agg="{k["agg"]}" data-field="{e(k.get("field", ""))}" '
                     f'data-decimals="{dec}" data-prefix="{e(pre)}" data-suffix="{e(suf)}"><span class="v">{e(v)}</span>'
                     f'<span class="l">{e(k["label"])}</span>{note}</div>')
        parts.append('<section class="b-kpis" aria-label="Key figures">' + "".join(t) + "</section>")

    flt = spec.get("filters", {})
    bar = []
    for key in flt.get("chips", []):
        c = next(c for c in cols if c["key"] == key)
        vals = list(dict.fromkeys(r[key] for r in rows))
        bar.append(f'<div class="d-chips" role="group" aria-label="{e(c["label"])}"><span class="lbl">{e(c["label"])}</span>' +
                   "".join(f'<button type="button" class="b-chip" aria-pressed="false" data-chip-col="{e(key)}" data-chip-val="{e(v)}">{e(v)}</button>' for v in vals) + "</div>")
    if flt.get("search", True):
        bar.append('<input class="d-search" id="d-search" type="search" placeholder="Search rows" aria-label="Search rows">')
    bar.append('<div class="d-actions"><span id="d-count"></span><button type="button" class="d-btn" id="d-csv">Export CSV</button></div>')
    parts.append('<div class="d-bar">' + "".join(bar) + "</div>")

    if mode == "dashboard" and spec.get("charts"):
        cards = []
        for c in spec["charts"]:
            cap = f'<p class="cap">{e(c["caption"])}</p>' if c.get("caption") else ""
            cards.append(f'<article class="b-card d-chart" id="chart-{e(c["id"])}"><button type="button" class="d-btn ghost tgl" aria-pressed="false">Show as table</button>'
                         f'<h3>{e(c["heading"])}</h3>{cap}<div class="d-legend"></div><div class="plot"></div><div class="alt" hidden></div></article>')
        parts.append('<section class="d-sec"><h2>Charts</h2><div class="d-charts">' + "".join(cards) + "</div></section>")

    tcfg = spec.get("table", {})
    sk, sd = (tcfg.get("sort") or {}).get("key"), (tcfg.get("sort") or {}).get("dir", "asc")
    first = sorted(rows, key=lambda r: (num(r[sk]) if next(c for c in cols if c["key"] == sk)["type"] == "num" else str(r[sk])), reverse=sd == "desc") if sk else rows
    ps = tcfg.get("page_size", 25)

    def td(c, v):
        if c["type"] == "num" and v != "":
            return f'<td class="num">{e(fmt(v, c["decimals"], c.get("prefix", ""), c.get("suffix", "")))}</td>'
        return f"<td>{e(v)}</td>"
    head = "".join(f'<th data-key="{e(c["key"])}" tabindex="0" aria-sort="none"{" class=num" if c["type"] == "num" else ""}>{e(c["label"])}</th>' for c in cols)
    body = "".join("<tr>" + "".join(td(c, r[c["key"]]) for c in cols) + "</tr>" for r in first[:ps])
    parts.append(f'<section class="d-sec"><h2>{"Data" if mode == "dashboard" else "Table"}</h2><div class="d-table-wrap"><table class="b-table d-table" id="d-table">'
                 f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
                 f'<div class="d-meta"><button type="button" class="d-btn ghost" id="d-more" hidden>Show more</button></div></section>')
    src = f"Source: {e(spec['source'])}. " if spec.get("source") else ""
    ill = "Illustrative data, not real figures. " if spec.get("illustrative") else ""
    parts.append(f'<p class="d-note">{src}{ill}KPIs and charts follow the active filters.</p></main>')
    parts.append(f"<script>\nconst DATA = {blob};\n{(ROOT / 'assets' / 'dashboard.js').read_text()}</script>")

    css = (ROOT / "assets" / "dashboard.css").read_text()
    if dark:
        css += (ROOT / "assets" / "dashboard-dark.css").read_text()
    return build("\n".join(parts), spec["title"], lang, spec.get("description") or spec.get("subtitle", ""), dark, css)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("out"); ap.add_argument("--dark", action="store_true")
    a = ap.parse_args()
    sp = Path(a.spec)
    out = render(json.loads(sp.read_text()), sp.parent, a.dark)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(out)
    print("wrote", a.out, f"({len(out) // 1024} KB)")
