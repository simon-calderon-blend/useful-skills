#!/usr/bin/env python3
"""Assemble a self-contained Blend HTML page from a body fragment.

Usage: blend_web.py BODY.html OUT.html --title T [--lang es] [--description D] [--dark]
                    [--font embed|none] [--extra-css FILE]
Inlines tokens.css (+ tokens-dark.css and a light/dark toggle with --dark) and components.css, embeds
PP Telegraf Regular (assets/fonts, base64, +61 KB) and adds the Blend logo as an inline SVG header.
--font none skips the embedding and loads Montserrat from Google Fonts instead.
Use {{LOGO}} in the body to place the logo yourself; otherwise the standard header is prepended.
Dark mode is optional: without --dark the page is light only; with it the page follows
prefers-color-scheme and gets a toggle that remembers the choice (localStorage, guarded).
Stdlib only.
"""
import argparse, base64, html, re
from pathlib import Path

A = Path(__file__).resolve().parent.parent / "assets"


def font_face():
    data = base64.b64encode((A / "fonts" / "PPTelegraf-Regular.otf").read_bytes()).decode()
    return ("@font-face{font-family:'PP Telegraf';font-weight:400;font-style:normal;font-display:swap;"
            f"src:url(data:font/otf;base64,{data}) format('opentype')}}\n")


def build(body, title, lang="es", description="", dark=False, extra_css="", font="embed", toggle=None):
    """toggle=None adds the light/dark button when dark is on, unless the body already has its own theme button."""
    logo = (A / "logo.svg").read_text()
    css = (font_face() if font == "embed" else "") + (A / "tokens.css").read_text()
    if toggle is None:
        toggle = dark and not re.search(r"<button[^>]*theme", body, re.I)
    if dark:
        css += (A / "tokens-dark.css").read_text()
    css += (A / "components.css").read_text()
    if toggle:
        css += (A / "theme-toggle.css").read_text()
    css += extra_css
    btn = '<button type="button" class="b-theme-toggle%s" data-theme-toggle aria-label="Toggle light/dark theme">Light / dark</button>'
    header = f'<header class="b-header"><a href="./" aria-label="Blend">{logo}</a>{btn % "" if toggle else ""}</header>'
    if "{{LOGO}}" in body:
        body = body.replace("{{LOGO}}", logo)
        header = btn % " b-theme-fixed" if toggle else ""
    fontlink = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600&display=swap" rel="stylesheet">\n'
                if font != "embed" else "")
    skip = ('<a class="b-skip" href="#main">%s</a>\n' % ("Saltar al contenido" if lang.startswith("es") else "Skip to content")
            if re.search(r'\bid="main"', body) else "")
    script = f"<script>\n{(A / 'theme-toggle.js').read_text()}</script>\n" if toggle else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description or title)}">
{fontlink}{script}<style>
{css}
</style>
</head>
<body>
{skip}{header}
{body}
</body>
</html>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("body"); ap.add_argument("out"); ap.add_argument("--title", required=True)
    ap.add_argument("--lang", default="es"); ap.add_argument("--description", default="")
    ap.add_argument("--dark", action="store_true"); ap.add_argument("--extra-css")
    ap.add_argument("--font", choices=["embed", "none"], default="embed")
    a = ap.parse_args()
    extra = Path(a.extra_css).read_text() if a.extra_css else ""
    Path(a.out).write_text(build(Path(a.body).read_text(), a.title, a.lang, a.description, a.dark, extra, a.font))
    print("wrote", a.out)
