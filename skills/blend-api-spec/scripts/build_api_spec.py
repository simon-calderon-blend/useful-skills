#!/usr/bin/env python3
"""Build a publishable Blend-themed Swagger UI folder from an OpenAPI spec.

Usage:
  build_api_spec.py --spec openapi.json --title "Orders API" --version 1.0.0 --out OUT_DIR
        [--status current|proposed] [--since 2026-11-10] [--lang en|es] [--dark]
        [--compare-spec PROPOSED.json]   # comparator: --spec is the current one, this is the proposal
Writes OUT_DIR/index.html (+ actual.html and propuesta.html in compare mode), openapi.json (the spec as
published), and vendor/ (Swagger UI bundle and css, pinned, copied from assets/vendor, no CDN).
The spec is also embedded in each page as <script type="application/json" id="spec">, so the page works from
file:// and needs no fetch. JSON specs need only the stdlib; YAML specs need PyYAML (optional).
Reuses ../../blend-web-core/assets (tokens, components, logo).
"""
import argparse, html, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CORE = HERE.parent / "blend-web-core" / "assets"
sys.path.insert(0, str(HERE.parent / "blend-web-core" / "scripts"))
from blend_web import font_face  # PP Telegraf Regular as a base64 @font-face (user-authorized bundling, 2026-11-10)

THEME_BTN = '<button type="button" class="b-theme-toggle" data-theme-toggle aria-label="Toggle light/dark theme">Light / dark</button>'

T = {
    "en": {"current": "Current contract", "proposed": "Proposed contract, not deployed", "since": "in force since",
           "private": "Private API: Try it out is disabled.", "download": "Download spec", "illus": "Illustrative",
           "side": "Side by side", "cur": "Current", "prop": "Proposed", "ver": "version"},
    "es": {"current": "Contrato vigente", "proposed": "Contrato propuesto, no desplegado", "since": "vigente desde",
           "private": "API privada: Try it out esta deshabilitado.", "download": "Descargar spec", "illus": "Illustrative",
           "side": "Lado a lado", "cur": "Actual", "prop": "Propuesta", "ver": "version"},
}


def load_spec(path):
    p = Path(path)
    text = p.read_text()
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # optional
        except ImportError:
            sys.exit("YAML spec needs PyYAML (pip install pyyaml) or convert it to JSON first")
        return yaml.safe_load(text)
    return json.loads(text)


def spec_json(spec):
    # "</" escaped so the JSON can sit inside <script>; it stays valid JSON
    return json.dumps(spec, ensure_ascii=False, indent=1).replace("</", "<\\/")


def css(dark):
    c = font_face() + (CORE / "tokens.css").read_text()
    if dark:
        c += (CORE / "tokens-dark.css").read_text()
    c += (CORE / "components.css").read_text() + (HERE / "assets" / "blend-swagger-theme.css").read_text()
    if dark:
        c += (CORE / "theme-toggle.css").read_text() + (HERE / "assets" / "blend-swagger-dark.css").read_text()
    return c


def theme_script(dark):
    return f"<script>\n{(CORE / 'theme-toggle.js').read_text()}</script>\n" if dark else ""


def banner(status, since, lang):
    t = T[lang]
    label = t[status] + (f" ({t['since']} {html.escape(since)})" if status == "current" and since else "")
    return f'<div class="b-api-band {status}" role="status"><strong>{label}.</strong> {t["private"]}</div>'


def page(spec, title, version, status, since, lang, dark, chrome=True, spec_href="openapi.json"):
    t = T[lang]
    logo = (CORE / "logo.svg").read_text()
    head = ""
    if chrome:
        head = (f'<header class="b-header"><a href="./" aria-label="Blend">{logo}</a>'
                f'<div class="b-api-meta"><span class="b-chip">{t["ver"]} {html.escape(version)}</span>'
                f'<a href="{spec_href}" download>{t["download"]}</a>{THEME_BTN if dark else ""}</div></header>\n' + banner(status, since, lang))
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(title)} {t['ver']} {html.escape(version)}">
{theme_script(dark)}<link rel="stylesheet" href="vendor/swagger-ui.css">
<style>
{css(dark)}
</style>
</head>
<body>
{head}
<main class="b-api-main"><div id="swagger-ui"></div></main>
<script type="application/json" id="spec">
{spec_json(spec)}
</script>
<script src="vendor/swagger-ui-bundle.js"></script>
<script>
  window.ui = SwaggerUIBundle({{
    spec: JSON.parse(document.getElementById("spec").textContent),
    dom_id: "#swagger-ui",
    deepLinking: true,
    docExpansion: 'list',
    defaultModelsExpandDepth: 1,
    defaultModelExpandDepth: 3,
    displayOperationId: true,
    supportedSubmitMethods: [],
    validatorUrl: null,
    presets: [SwaggerUIBundle.presets.apis],
    layout: "BaseLayout"
  }});
</script>
</body>
</html>
"""


MIRROR = """  // the panes are same-origin iframes: mirror the theme chosen with the toggle into them (guarded, file:// may refuse)
  document.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-theme-toggle]")) return;
    document.querySelectorAll("iframe").forEach(function (f) {
      try { f.contentDocument.documentElement.setAttribute("data-theme", document.documentElement.getAttribute("data-theme")); } catch (x) {}
    });
  });
"""


def shell(title, version, since, lang, dark):
    t = T[lang]
    logo = (CORE / "logo.svg").read_text()
    mirror = MIRROR if dark else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(title)}: {t['cur'].lower()} / {t['prop'].lower()}">
{theme_script(dark)}<style>
{css(dark)}
</style>
</head>
<body data-view="side">
<header class="b-header"><a href="./" aria-label="Blend">{logo}</a>
<div class="b-api-meta"><span class="b-chip">{t['ver']} {html.escape(version)}</span>
<div class="b-api-toggle" role="group" aria-label="View">
<button type="button" data-v="side" aria-pressed="true">{t['side']}</button>
<button type="button" data-v="current" aria-pressed="false">{t['cur']}</button>
<button type="button" data-v="proposed" aria-pressed="false">{t['prop']}</button></div>
<a href="openapi.json" download>{t['download']}</a>{THEME_BTN if dark else ""}</div></header>
{banner("proposed", since, lang)}
<div class="b-api-panes">
<figure class="current"><figcaption>{t['cur']}</figcaption><iframe src="actual.html" title="{t['cur']}"></iframe></figure>
<figure class="proposed"><figcaption>{t['prop']}</figcaption><iframe src="propuesta.html" title="{t['prop']}"></iframe></figure>
</div>
<script>
{mirror}  var bs = document.querySelectorAll(".b-api-toggle button");
  bs.forEach(function (b) {{ b.addEventListener("click", function () {{
    document.body.dataset.view = b.dataset.v;
    bs.forEach(function (x) {{ x.setAttribute("aria-pressed", x === b ? "true" : "false"); }});
  }}); }});
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True); ap.add_argument("--title", required=True)
    ap.add_argument("--version", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--status", default="current", choices=["current", "proposed"])
    ap.add_argument("--since", default=""); ap.add_argument("--lang", default="en", choices=["en", "es"])
    ap.add_argument("--dark", action="store_true"); ap.add_argument("--compare-spec")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    spec = load_spec(a.spec)
    (out / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n")
    vend = out / "vendor"; vend.mkdir(exist_ok=True)
    for f in ("swagger-ui-bundle.js", "swagger-ui.css", "LICENSE", "NOTICE", "VERSION"):
        shutil.copy(HERE / "assets" / "vendor" / f, vend / f)
    if a.compare_spec:
        prop = load_spec(a.compare_spec)
        (out / "openapi-proposed.json").write_text(json.dumps(prop, ensure_ascii=False, indent=1) + "\n")
        (out / "actual.html").write_text(page(spec, a.title + " (current)", a.version, "current", a.since, a.lang, a.dark, chrome=False))
        (out / "propuesta.html").write_text(page(prop, a.title + " (proposed)", a.version, "proposed", a.since, a.lang, a.dark, chrome=False))
        (out / "index.html").write_text(shell(a.title, a.version, a.since, a.lang, a.dark))
    else:
        (out / "index.html").write_text(page(spec, a.title, a.version, a.status, a.since, a.lang, a.dark))
    print("wrote", out, "(swagger-ui-dist", (vend / "VERSION").read_text().strip() + ")")


if __name__ == "__main__":
    main()
