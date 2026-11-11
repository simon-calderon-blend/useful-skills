#!/usr/bin/env python3
"""Build the Blend-styled triage page from a report JSON.

usage: build_page.py REPORT.json OUT.html [--no-validate]

Writes OUT.html as an Artifact page fragment (no doctype/html/head: the Artifact tool adds them) with
PP Telegraf embedded, Blend tokens (light only), components, the inline logo and the report data.
Then writes OUT.validate.html (same page in a full <html lang="es"> document) and runs the bundled
Blend validator on it. Exit code 1 if the validator reports a FAIL. Stdlib only.
"""
import base64, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = HERE.parent / "assets"
B = A / "blend"


def blend_css():
    font = base64.b64encode((B / "fonts" / "PPTelegraf-Regular.otf").read_bytes()).decode()
    face = ("@font-face{font-family:'PP Telegraf';font-weight:400;font-style:normal;font-display:swap;"
            f"src:url(data:font/otf;base64,{font}) format('opentype')}}\n")
    return face + "".join((B / n).read_text() for n in ("tokens.css", "components.css"))


def build(report):
    page = (A / "triage-page.html").read_text()
    data = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    title = report.get("title") or "Triage de hallazgos"
    for k, v in {"@@TITLE@@": title, "@@BLEND_CSS@@": blend_css(),
                 "@@LOGO@@": (B / "logo.svg").read_text().strip(), "/*@@REPORT@@*/null": data}.items():
        if k not in page:
            sys.exit(f"template marker missing: {k}")
        page = page.replace(k, v)
    return page


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    report = json.loads(Path(args[0]).read_text())
    report.pop("_comment", None)
    leaks = re.findall(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:", json.dumps(report))
    if leaks:
        sys.exit(f"report contains full ARNs (Blend rule: none in a page): {leaks[:3]} - abbreviate them")
    out = Path(args[1])
    page = build(report)
    out.write_text(page)
    print(f"wrote {out} ({len(page) // 1024} KB)")
    if "--no-validate" in sys.argv:
        return
    vcopy = out.with_suffix(".validate.html")
    vcopy.write_text('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                     '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                     f'</head><body>{page}</body></html>')
    r = subprocess.run([sys.executable, str(HERE / "validate_blend.py"), str(vcopy), "--kind", "generic", "--dark", "off"])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
