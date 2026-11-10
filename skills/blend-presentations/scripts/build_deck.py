#!/usr/bin/env python3
"""Build a self-contained Blend deck (DOM variant) from a JSON spec.

Usage: build_deck.py SPEC.json OUT/index.html [--dark]
Spec: {"title","subtitle","author","date","lang","client":{"name","accent"}?,
       "slides":[{"type":"cover|section|content|quote|closing", ...}]}
Slide fields: cover{title,subtitle,eyebrow}, section{title,eyebrow}, content{eyebrow,title,points[],kpis[{value,label}],
illustrative(bool)}, quote{quote,author}, closing{title,subtitle,contact}; every slide takes "notes".
Reuses blend-web-core (tokens, components, logo, blend_web.build). PP Telegraf is embedded by the core (+61 KB). Stdlib only.
"""
import argparse, html, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
sys.path.insert(0, str(HERE.parent.parent / "blend-web-core" / "scripts"))
from blend_web import build  # noqa: E402

e = html.escape


def notes(s):
    return f'<p class="notes">{e(s["notes"])}</p>' if s.get("notes") else ""


def slide(s, i, total, spec):
    t = s.get("type", "content")
    eyebrow = f'<p class="b-eyebrow">{e(s["eyebrow"])}</p>' if s.get("eyebrow") else ""
    label = f'aria-label="{e(s.get("title") or s.get("quote", "")[:60] or t)}"'
    if t == "cover":
        client = spec.get("client")
        tag = f'<span class="client-tag">{e(spec.get("client_label", "Prepared for"))} {e(client["name"])}</span>' if client else ""
        meta = " · ".join(x for x in (spec.get("author"), spec.get("date")) if x)
        inner = (f'{eyebrow}<h1>{e(s["title"])}</h1><p class="lede">{e(s.get("subtitle", ""))}</p>'
                 f'<p class="meta">{e(meta)}</p>{tag}')
        cls = "s-cover dark"
    elif t == "section":
        inner = f'{eyebrow}<p class="num" aria-hidden="true">{i:02d}</p><h2>{e(s["title"])}</h2>'
        cls = "s-section dark"
    elif t == "quote":
        inner = f'<blockquote>{e(s["quote"])}</blockquote><cite>{e(s.get("author", ""))}</cite>'
        cls = "s-quote"
    elif t == "closing":
        contact = f'<p class="meta">{e(s["contact"])}</p>' if s.get("contact") else ""
        inner = f'{eyebrow}<h1>{e(s["title"])}</h1><p class="lede">{e(s.get("subtitle", ""))}</p>{contact}'
        cls = "s-closing dark"
    else:
        pts = "".join(f"<li>{e(p)}</li>" for p in s.get("points", []))
        pts = f'<ul class="points">{pts}</ul>' if pts else ""
        kp = "".join(f'<div class="b-card b-kpi"><span class="v">{e(k["value"])}</span><span class="l">{e(k["label"])}</span></div>'
                     for k in s.get("kpis", []))
        kp = f'<div class="kpi-strip">{kp}</div>' if kp else ""
        ill = '<p class="illus">Illustrative data</p>' if s.get("illustrative") else ""
        inner = f'{eyebrow}<h2>{e(s["title"])}</h2>{pts}{kp}{ill}'
        cls = "s-content"
    active = " active" if i == 1 else ""
    return (f'<section class="slide {cls}{active}" id="s{i}" role="group" aria-roledescription="slide" '
            f'aria-label="{i} / {total}: {e(s.get("title") or s.get("quote", "")[:60] or t)}" aria-hidden="{"false" if i == 1 else "true"}">'
            f'{inner}{notes(s)}</section>')


def render(spec, dark=False):
    slides = spec["slides"]
    n = len(slides)
    body = "\n".join(slide(s, i, n, spec) for i, s in enumerate(slides, 1))
    chrome = f"""
<div class="deck-logo">{{{{LOGO}}}}</div>
<nav class="deck-hud" aria-label="Slide navigation">
  <button type="button" id="deck-prev" aria-label="Previous slide">&larr;</button>
  <span class="counter" id="deck-counter" role="status" aria-live="polite">1 / {n}</span>
  <span><button type="button" id="deck-notes-btn" aria-label="Toggle speaker notes (N)">N</button>
  <button type="button" id="deck-next" aria-label="Next slide">&rarr;</button></span>
</nav>
<div class="deck-progress" aria-hidden="true"></div>
<aside class="deck-notes dark" id="deck-notes" aria-label="Speaker notes" hidden><p class="b-eyebrow">Notes</p><div class="text"></div></aside>"""
    page_body = f'<main class="deck" aria-label="{e(spec["title"])}">\n{body}\n</main>{chrome}\n<script>\n{(ASSETS / "deck.js").read_text()}</script>'
    css = (ASSETS / "deck.css").read_text()
    c = spec.get("client")
    if c:  # co-branding: client colors only in --client-*; never replaces Blend tokens
        css = f":root {{ --client-name: '{c['name']}'; --client-accent: {c.get('accent', '#00EDED')}; }}\n" + css
    return build(page_body, spec["title"], spec.get("lang", "en"), spec.get("subtitle", ""), dark, css)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("out"); ap.add_argument("--dark", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(json.loads(Path(a.spec).read_text()), a.dark))
    print("wrote", out)
