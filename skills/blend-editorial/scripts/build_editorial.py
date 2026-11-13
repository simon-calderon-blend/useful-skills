#!/usr/bin/env python3
"""Build a Blend article or commercial page from a JSON spec (stdlib only).

Usage: build_editorial.py SPEC.json OUT.html [--dark]
Spec keys: kind (article|one-pager|landing), lang, title, eyebrow, dek, meta, description,
  nav (bool), cta {label, href, title, text}, client {name, logo (file path, optional), alt, confidential},
  illustrative (bool), footer, sections [{label, title, blocks:[...]}]  (one-pager: sheets [{sections}] ).
Blocks: {p}, {h3}, {ul:[..]}, {quote, cite}, {callout}, {kpis:[[value,label,qualifier?]..]}, {cards:[[title,text]..]},
  {steps:[[title,text]..]}, {figure:"<svg>", caption}, {table:{head:[..], rows:[[..]]}}.
Reuses ../../blend-web-core (tokens, components, logo, blend_web.build).
"""
import base64, html, json, mimetypes, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CORE = HERE.parent / "blend-web-core"
sys.path.insert(0, str(CORE / "scripts"))
import blend_web  # noqa: E402

e = html.escape


def block(b):
    if "p" in b: return f"<p>{b['p']}</p>"
    if "h3" in b: return f"<h3>{e(b['h3'])}</h3>"
    if "ul" in b: return "<ul>" + "".join(f"<li>{i}</li>" for i in b["ul"]) + "</ul>"
    if "quote" in b:
        c = f"<cite>{e(b['cite'])}</cite>" if b.get("cite") else ""
        return f'<blockquote class="e-quote">{e(b["quote"])}{c}</blockquote>'
    if "callout" in b: return f'<div class="b-callout">{b["callout"]}</div>'
    if "kpis" in b:
        return '<div class="b-kpis">' + "".join(f'<div class="b-kpi"><span class="v">{e(k[0])}</span><span class="l">{e(k[1])}</span>'
                                               + (f'<span class="c">{e(k[2])}</span>' if len(k) > 2 else "") + "</div>" for k in b["kpis"]) + "</div>"
    if "cards" in b:
        return '<div class="e-cards">' + "".join(f'<div><h3>{e(t)}</h3><p>{x}</p></div>' for t, x in b["cards"]) + "</div>"
    if "steps" in b:
        return '<ol class="e-steps">' + "".join(f"<li><strong>{e(t)}</strong><span>{x}</span></li>" for t, x in b["steps"]) + "</ol>"
    if "figure" in b:
        cap = f"<figcaption>{b['caption']}</figcaption>" if b.get("caption") else ""
        return f'<figure class="e-figure">{b["figure"]}{cap}</figure>'
    if "table" in b:
        t = b["table"]
        return ('<div class="b-table-wrap"><table class="b-table"><thead><tr>' + "".join(f"<th>{e(h)}</th>" for h in t["head"]) +
                "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in t["rows"]) + "</tbody></table></div>")
    raise SystemExit(f"unknown block: {list(b)}")


def section(s, n):
    sid = s.get("id") or f"s{n}"
    # "label" feeds the topbar nav only: no eyebrow and no 01/02 above the heading (the h2 announces itself)
    return (f'<section class="e-section" id="{sid}"><h2>{e(s["title"])}</h2><div class="e-prose">' + "".join(block(b) for b in s["blocks"]) + "</div></section>")


def cobrand(spec, logo):
    c = spec.get("client")
    if not c: return f'<a href="./" aria-label="Blend">{logo}</a>'
    if c.get("logo"):
        f = Path(c["logo"])
        mime = mimetypes.guess_type(f.name)[0] or "image/svg+xml"
        uri = f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
        who = f'<img src="{uri}" alt="{e(c.get("alt") or c["name"] + " logo")}">'
    else:
        who = f'<span class="client">{e(c["name"])}</span>'
    return f'<div class="e-cobrand"><a href="./" aria-label="Blend">{logo}</a><span class="div"></span><span class="x" aria-hidden="true">×</span>{who}</div>'


def build(spec, dark=False):
    kind = spec.get("kind", "article")
    logo = "{{LOGO}}"  # blend_web.build swaps in assets/logo.svg and skips its own header
    secs = spec.get("sections", [])
    nav = ""
    if spec.get("nav") and secs:
        nav = "<nav aria-label=\"Sections\">" + "".join(f'<a href="#{s.get("id") or "s%d" % i}">{e(s.get("label", s["title"]))}</a>' for i, s in enumerate(secs, 1)) + "</nav>"
    top = f'<header class="e-topbar">{cobrand(spec, logo)}{nav}</header>'
    cta = spec.get("cta")
    actions = f'<div class="actions"><a class="b-btn e-btn" href="{e(cta["href"])}">{e(cta["label"])}</a></div>' if cta and kind != "article" else ""
    pill = ' <span class="e-pill">Illustrative</span>' if spec.get("illustrative") else ""
    eyebrow = f'<p class="b-eyebrow">{e(spec["eyebrow"])}</p>' if spec.get("eyebrow") else ""  # optional: the page's one eyebrow
    dek = f'<p class="dek">{e(spec["dek"])}</p>' if spec.get("dek") else ""
    meta = f'<span>{e(spec["meta"])}</span>' if spec.get("meta") else ""
    metap = f'<p class="meta">{meta}{pill}</p>' if meta or pill else ""
    hero = f'<div class="e-hero"><div>{eyebrow}<h1>{e(spec["title"])}</h1>{dek}{actions}{metap}</div></div>'
    if kind == "one-pager":
        sheets = spec.get("sheets") or [secs]
        n = 0; out = []
        for i, sh in enumerate(sheets):
            inner = ""
            for s in sh:
                n += 1; inner += section(s, n)
            first = top + hero if i == 0 else ""
            out.append(f'<div class="e-sheet" data-page="{i + 1}">{first}<main class="e-main">{inner}</main>@@LAST@@' if i == len(sheets) - 1 else
                       f'<div class="e-sheet" data-page="{i + 1}">{first}<main class="e-main">{inner}</main></div>')
        main = "".join(out)
    else:
        main = '<main class="e-main" id="main">' + "".join(section(s, i) for i, s in enumerate(secs, 1)) + "</main>"
    band = ""
    if cta:  # the closing band repeats the page's single action, in the same words
        band = (f'<div class="e-cta"><div><h2>{e(cta.get("title", cta["label"]))}</h2><p>{e(cta.get("text", ""))}</p></div>'
                f'<a class="b-btn e-btn" href="{e(cta["href"])}">{e(cta["label"])}</a></div>')
    conf = " · Confidential" if (spec.get("client") or {}).get("confidential") else ""
    foot = f'<footer class="e-footer"><span>{e(spec.get("footer", "© 2026 Blend Analytics Ltd."))}{conf}</span><a href="https://www.blend360.com">blend360.com</a></footer>'
    if kind == "one-pager":
        body = main.replace("@@LAST@@", band + foot + "</div>")  # CTA and footer stay on the last sheet
    else:
        body = top + hero + main + band + foot
    extra = (HERE / "assets" / "editorial.css").read_text()
    if kind == "one-pager":
        extra += (HERE / "assets" / "onepager.css").read_text()
    if dark:
        extra += (HERE / "assets" / "editorial-dark.css").read_text()
    return blend_web.build(body, spec["title"], spec.get("lang", "en"),
                           spec.get("description", spec.get("dek", "")), dark, extra)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    spec = json.loads(Path(args[0]).read_text())
    Path(args[1]).write_text(build(spec, "--dark" in sys.argv))
    print("wrote", args[1])
