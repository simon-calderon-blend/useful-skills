#!/usr/bin/env python3
"""Validate a Blend report: blend-web-core validate.py (--kind report) plus report-specific checks.

Usage: validate_report.py PATH [--variant auto|simple|sidebar|scorecard] [--strict] [--render] [--dark ...]
Extra checks (R1..R6):
  R1 executive summary near the top (before the first table / finding)
  R2 every finding has a severity chip and evidence
  R3 every table has a header row and the CSS paints table headers navy (#053057)
  R4 @media print and @page exist
  R5 table of contents when there are more than 3 sections (not required for the scorecard variant)
  R6 status colors (ok/warn/bad/severity) come only from the core tokens
Exit code 1 on any FAIL (or WARN with --strict). Stdlib only.
"""
import argparse, re, subprocess, sys
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent.parent / "blend-web-core"
TOKENS = (CORE / "assets" / "tokens.css").read_text()
CORE_HEX = {h.upper() for h in re.findall(r"#([0-9a-fA-F]{6})\b", TOKENS)} | {"FFFFFF"}
NAVY = re.compile(r"053057|var\(--(?:blend-navy|washed-blue|navy|heading)\)", re.I)
SUMMARY = re.compile(r"executive summary|resumen ejecutivo|resumen|summary|verdict|veredicto|key findings|tl;dr|at a glance", re.I)


def strip(t):
    t = re.sub(r"data:[a-z/+.-]+;base64,[A-Za-z0-9+/=]+", "data:BASE64", t)
    return re.sub(r"<!--.*?-->", "", t, flags=re.S)


def css_of(t):
    return re.sub(r"/\*.*?\*/", "", "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", t, re.S | re.I)), flags=re.S)


def rules(css):
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", css)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--variant", default="auto", choices=["auto", "simple", "sidebar", "scorecard"])
    ap.add_argument("--strict", action="store_true"); ap.add_argument("--render", action="store_true")
    ap.add_argument("--dark", default="auto", choices=["auto", "required", "off"])
    a = ap.parse_args()
    p = Path(a.path)
    index = p / "index.html" if p.is_dir() else p
    raw = index.read_text(errors="ignore")
    t = strip(raw)
    css = css_of(t)
    variant = a.variant
    if variant == "auto":
        m = re.search(r'<body[^>]*data-variant="(\w+)"', t)
        variant = m.group(1) if m else "simple"

    rows = []
    # Core validator
    cmd = [sys.executable, str(CORE / "scripts" / "validate.py"), str(p), "--kind", "report", "--dark", a.dark]
    if a.render:
        cmd.append("--render")
    core = subprocess.run(cmd, capture_output=True, text=True)
    print("== blend-web-core validate.py --kind report ==")
    print(core.stdout.rstrip())
    if core.returncode not in (0, 1):
        print(core.stderr)
    core_fail = [l for l in core.stdout.splitlines() if re.match(r"\s*\d+ \S+\s+FAIL", l)]
    core_warn = [l for l in core.stdout.splitlines() if re.match(r"\s*\d+ \S+\s+WARN", l)]
    rows.append(("core", "FAIL" if core_fail else ("WARN" if core_warn else "PASS"),
                 f"{len(core_fail)} FAIL, {len(core_warn)} WARN in the core checks (see above)"))

    body = re.search(r"<body.*", t, re.S | re.I)
    body = body.group(0) if body else t
    first_table = body.find("<table")
    first_finding = min([i for i in (body.find('class="r-finding"'), body.find("class='finding'"), body.find('class="finding"')) if i >= 0] or [-1])
    limits = [i for i in (first_table, first_finding) if i >= 0]
    cutoff = min(limits) if limits else len(body)

    # R1 executive summary
    head = body[:cutoff]
    hs = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", head, re.S | re.I)
    by_id = re.search(r'<(?:section|div|aside)[^>]*(?:id|class)="[^"]*(?:resumen|summary|exec|verdict)[^"]*"', head, re.I)
    hit = [re.sub(r"<[^>]+>", "", h).strip() for h in hs if SUMMARY.search(re.sub(r"<[^>]+>", "", h))]
    if hit or by_id:
        rows.append(("R1", "PASS", f"summary before first table/finding: {(hit[0] if hit else 'by id/class')[:50]!r}"))
    else:
        rows.append(("R1", "FAIL", "no executive summary / verdict heading before the first table or finding"))

    # R2 findings with severity and evidence
    fs = re.findall(r'<(article|div|section|li)[^>]*class="[^"]*\b(?:r-)?finding\b[^"]*"[^>]*>(.*?)</\1>', body, re.S | re.I)
    if not fs:
        rows.append(("R2", "WARN", "no finding blocks (class 'finding' / 'r-finding') found; severity/evidence not checkable"))
    else:
        nosev = [i + 1 for i, (_, x) in enumerate(fs) if not re.search(r'class="[^"]*\b(?:sev|b-chip)\b|data-sev=', x)]
        noev = [i + 1 for i, (_, x) in enumerate(fs) if not re.search(r'class="[^"]*\b(?:r-)?evidence\b|<details|<pre|<table|<figure', x)]
        if nosev or noev:
            rows.append(("R2", "FAIL", f"{len(fs)} findings; without severity: {nosev or 'none'}; without evidence: {noev or 'none'}"))
        else:
            rows.append(("R2", "PASS", f"{len(fs)} findings, all with severity chip and evidence"))

    # R3 tables: header row + navy th in CSS
    tables = re.findall(r"<table\b.*?</table>", body, re.S | re.I)
    nohead = [i + 1 for i, x in enumerate(tables) if not re.search(r"<th\b", x, re.I)]
    navy_th = any(re.search(r"\bth\b", sel) and re.search(r"background(?:-color)?\s*:\s*([^;]+)", b) and
                  NAVY.search(re.search(r"background(?:-color)?\s*:\s*([^;]+)", b).group(1))
                  for sel, b in rules(css))
    if not tables and variant == "scorecard":
        rows.append(("R3", "PASS", "scorecard without tables (score bars are the evidence)"))
    elif not tables:
        rows.append(("R3", "WARN", "no tables in the report (evidence usually needs at least one)"))
    elif nohead:
        rows.append(("R3", "FAIL", f"tables without <th> header row: {nohead}"))
    elif not navy_th:
        rows.append(("R3", "FAIL", f"{len(tables)} tables, but no CSS rule paints th with navy #053057 (background: var(--blend-navy))"))
    else:
        rows.append(("R3", "PASS", f"{len(tables)} tables with header row; th rule uses navy"))

    # R4 print
    mp = bool(re.search(r"@media\s+print", css)); pg = bool(re.search(r"@page\b", css))
    if not mp:
        rows.append(("R4", "FAIL", "@media print missing"))
    elif not pg:
        rows.append(("R4", "FAIL" if variant == "scorecard" else "WARN", "@page missing" + (" (required for the scorecard one-pager)" if variant == "scorecard" else "")))
    else:
        rows.append(("R4", "PASS", "@media print and @page present"))

    # R5 TOC
    nsec = len(re.findall(r"<h2[\s>]", body, re.I))
    toc = re.search(r"<nav[^>]*>(.*?)</nav>", body, re.S | re.I)
    links = len(re.findall(r'href="#[^"]+"', toc.group(1))) if toc else 0
    ids = set(re.findall(r'\bid="([^"]+)"', body))
    broken = [h for h in re.findall(r'href="#([^"]+)"', toc.group(1))] if toc else []
    broken = [h for h in broken if h not in ids]
    if nsec <= 3 or variant == "scorecard":
        rows.append(("R5", "PASS", f"{nsec} h2 sections; TOC not required" + (" (scorecard)" if variant == "scorecard" else "")))
    elif links < 3:
        rows.append(("R5", "FAIL", f"{nsec} h2 sections but no <nav> TOC with 3+ anchor links"))
    elif broken:
        rows.append(("R5", "FAIL", f"TOC links to missing ids: {broken[:4]}"))
    else:
        rows.append(("R5", "PASS", f"{nsec} h2 sections; TOC with {links} working anchors"))

    # R6 status colors only from core tokens
    bad = []
    for sel, b in rules(css):
        if re.search(r"\.(?:ok|warn|bad|sev|severity|status|pill|chip|badge|state)\b|data-sev|\.(?:ok|warn|bad)", sel):
            for h in re.findall(r"#([0-9a-fA-F]{3,6})\b", b):
                hx = h.upper() if len(h) == 6 else "".join(c * 2 for c in h.upper())
                if hx not in CORE_HEX:
                    bad.append(f"#{hx} in {sel[:30]}")
    for name, val in re.findall(r"(--(?:ok|warn|bad|good|danger|success|error|state-[\w-]+|sev[\w-]*|status[\w-]*))\s*:\s*([^;}]+)", css):
        for h in re.findall(r"#([0-9a-fA-F]{6})\b", val):
            if h.upper() not in CORE_HEX:
                bad.append(f"{name}: #{h.upper()}")
    if bad:
        rows.append(("R6", "FAIL", "status colors off the core tokens: " + "; ".join(bad[:5])))
    else:
        rows.append(("R6", "PASS", "no status color outside blend-web-core tokens (ok/warn/bad/info)"))

    print(f"\n== blend-report checks (variant={variant}) ==")
    for n, s, m in rows:
        print(f"{n:<5} {s:<4} {m}")
    fail = any(s == "FAIL" for _, s, _ in rows)
    warn = any(s == "WARN" for _, s, _ in rows)
    print("\nRESULT:", "FAIL" if fail else ("WARN" if warn else "PASS"))
    sys.exit(1 if fail or (a.strict and warn) else 0)


if __name__ == "__main__":
    main()
