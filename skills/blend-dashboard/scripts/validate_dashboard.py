#!/usr/bin/env python3
"""Validate a Blend dashboard: blend-web-core validate.py (--kind dashboard) plus dashboard checks.

Usage: validate_dashboard.py PATH [--dark {auto,required,off}] [--strict] [--render]
Extra checks:
 D1 embedded data: `const DATA = {...}` (or [...]) is present and parses as JSON
 D2 KPIs: every element with data-kpi is recomputed from the embedded rows and compared with the shown value
 D3 PII: column names, e-mails, NIT/cedula/phone patterns in the page and in the data
 D4 scripts: every <script src> is cdnjs.cloudflare.com with an exact version (Chart.js must be 4.4.0)
 D5 charts: no dual axis, no title inside a Chart.js figure, SVG charts carry role=img + aria-label
PASS / WARN / FAIL per line, exit 1 on any FAIL (or WARN with --strict). Stdlib only.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "blend-web-core" / "scripts" / "validate.py"
PII_COL = re.compile(r"(cedula|cédula|documento|\bnit\b|email|e-mail|correo|telefono|teléfono|phone|celular|patient|paciente)", re.I)
PII_VAL = {
    "e-mail": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "NIT": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-\d\b"),
    "cedula/ID": re.compile(r"(?i)\b(c\.?c\.?|cédula|cedula|nit|dni|ssn)\b[\s:#.]*\d{6,}"),
    "phone": re.compile(r"(?<!\d)(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"),
}


def extract_data(html):
    m = re.search(r"\bconst\s+DATA\s*=\s*", html)
    if not m:
        return None, "absent"
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[m.end():])
        return obj, "ok"
    except ValueError as ex:
        return None, f"unparseable: {str(ex)[:60]}"


def rows_of(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("rows", "data", "records", "items"):
            if isinstance(data.get(k), list):
                return data[k]
    return None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def agg(rows, kind, field):
    if kind == "count":
        return len(rows)
    if kind == "distinct":
        return len({json.dumps(r.get(field)) for r in rows})
    v = [num(r.get(field)) for r in rows if num(r.get(field)) is not None]
    if not v:
        return 0
    return {"sum": sum(v), "avg": sum(v) / len(v), "min": min(v), "max": max(v)}[kind]


def parse_shown(text, pre, suf):
    t = text.strip()
    if pre and t.startswith(pre):
        t = t[len(pre):]
    if suf and t.endswith(suf):
        t = t[:-len(suf)]
    return num(t.replace(",", ""))


def check_kpis(html, rows):
    tiles = re.findall(r"<[^>]+\bdata-kpi=[^>]*>.*?</div>", html, re.S)
    if not tiles:
        return "WARN", "no tiles with data-kpi: KPIs cannot be checked against the data"
    if rows is None:
        return "FAIL", f"{len(tiles)} KPI tile(s) but no embedded rows to check them against"
    bad, ok = [], 0
    for t in tiles:
        a = dict(re.findall(r'data-([\w-]+)="([^"]*)"', t))
        shown = re.search(r'class="v">([^<]*)<', t)
        name = a.get("kpi", "?")
        if not shown:
            bad.append(f"{name}: no value element"); continue
        import html as H
        pre, suf, dec = H.unescape(a.get("prefix", "")), H.unescape(a.get("suffix", "")), int(a.get("decimals") or 0)
        got = parse_shown(H.unescape(shown.group(1)), pre, suf)
        want = agg(rows, a.get("agg", ""), a.get("field", ""))
        if got is None or abs(got - want) > 0.5 * 10 ** -dec + 1e-9:
            bad.append(f"{name}: shown {shown.group(1)!r}, data gives {want:,.{dec}f}")
        else:
            ok += 1
    return ("FAIL", "; ".join(bad[:4])) if bad else ("PASS", f"{ok} KPI(s) match the embedded data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--dark", default="auto", choices=["auto", "required", "off"])
    ap.add_argument("--strict", action="store_true"); ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    p = Path(a.path)
    index = p / "index.html" if p.is_dir() else p
    html = index.read_text(errors="ignore")
    cmd = [sys.executable, str(CORE), str(p), "--kind", "dashboard", "--dark", a.dark] + (["--render"] if a.render else [])
    core = subprocess.run(cmd, capture_output=True, text=True)
    print(core.stdout.rstrip())
    if core.returncode > 1 or not core.stdout:
        print(core.stderr.strip()); sys.exit(2)

    rows_out = []
    data, st = extract_data(html)
    rows = rows_of(data) if data is not None else None
    if st == "ok":
        rows_out.append(("D1", "data", "PASS", f"DATA parses; {len(rows) if rows is not None else 'no'} rows"))
    elif st == "absent":
        rows_out.append(("D1", "data", "WARN", "no `const DATA` (static page or data loaded elsewhere): D2 cannot verify KPIs"))
    else:
        rows_out.append(("D1", "data", "FAIL", st))
    s, m = check_kpis(html, rows) if st != "absent" else ("WARN", "skipped: no embedded data")
    if st == "ok" and rows is None and re.search(r"data-kpi=", html):
        s, m = "FAIL", "DATA has no rows array (expected DATA.rows or a top-level list)"
    rows_out.append(("D2", "kpis", s, m))

    # D3 PII on data keys + values + page text outside the data blob
    live = re.sub(r"\bconst\s+DATA\s*=.*?;\n", "", html, flags=re.S) if st == "ok" else html
    live = re.sub(r"<style.*?</style>|<svg.*?</svg>", "", live, flags=re.S)
    blob = json.dumps(data, ensure_ascii=False) if data is not None else ""
    cols = set()
    if isinstance(data, dict):
        cols |= {c.get("key", "") for c in data.get("columns", []) if isinstance(c, dict)}
    if rows:
        cols |= {k for r in rows[:50] if isinstance(r, dict) for k in r}
    hits = [f"column '{c}'" for c in sorted(cols) if PII_COL.search(c)]
    for label, rx in PII_VAL.items():
        n = len(rx.findall(live + "\n" + blob))
        if n:
            hits.append(f"{n} {label} pattern(s)")
    rows_out.append(("D3", "pii", "FAIL" if hits else "PASS", ", ".join(hits) if hits else "no PII column names or patterns (regex only; still review the content)"))

    # D4 scripts
    bad = []
    chartjs = []
    for src in re.findall(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)", html, re.I):
        mm = re.match(r"https://cdnjs\.cloudflare\.com/ajax/libs/([\w.-]+)/(\d+\.\d+\.\d+)/", src)
        if not mm:
            bad.append(src[:60])
        elif mm.group(1).lower() == "chart.js":
            chartjs.append(mm.group(2))
    if bad:
        rows_out.append(("D4", "scripts", "FAIL", "script src not on cdnjs with exact version: " + ", ".join(bad)))
    elif any(v != "4.4.0" for v in chartjs):
        rows_out.append(("D4", "scripts", "WARN", f"Chart.js {chartjs} (skill pins 4.4.0)"))
    else:
        rows_out.append(("D4", "scripts", "PASS", "no external scripts" if not re.search(r"<script[^>]+src", html) else "cdnjs only, exact versions"))

    # D5 charts
    probs = []
    if re.search(r"yAxisID|\by1\s*:\s*\{|position\s*:\s*['\"]right['\"]", html):
        probs.append("possible dual axis")
    if re.search(r"title\s*:\s*\{[^}]*display\s*:\s*true", html):
        probs.append("title inside Chart.js figure")
    svgs = re.findall(r"<svg\b[^>]*>", html)
    chartsvg = [s for s in svgs if 'class="chart' in s]
    if any("aria-label" not in s or 'role="img"' not in s for s in chartsvg):
        probs.append("SVG chart without role=img + aria-label")
    uses = bool(chartjs) or "d-chart" in html or "<canvas" in html
    rows_out.append(("D5", "charts", "FAIL" if probs else "PASS", ", ".join(probs) if probs else ("rules ok" if uses else "no charts (table/KPI page)")))

    for n, c, s, m in rows_out:
        print(f"{n:>2} {c:<12} {s:<4} {m}")
    fail = core.returncode == 1 or any(s == "FAIL" for _, _, s, _ in rows_out)
    warn = "WARN" in core.stdout or any(s == "WARN" for _, _, s, _ in rows_out)
    print("RESULT", "FAIL" if fail else ("WARN" if warn else "PASS"))
    sys.exit(1 if fail or (a.strict and warn) else 0)


if __name__ == "__main__":
    main()
