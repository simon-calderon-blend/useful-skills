#!/usr/bin/env python3
"""Build a single-file Blend guide or course (HTML) from a JSON spec.

Usage: build_guide.py SPEC.json OUT.html [--dark]
Reuses ../../blend-web-core (tokens.css, components.css, logo.svg, blend_web.build) and adds assets/guide.css
and assets/guide.js. Stdlib only. See SKILL.md for the spec format.
"""
import argparse, html, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
sys.path.insert(0, str(HERE.parent.parent / "blend-web-core" / "scripts"))
import blend_web  # noqa: E402


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "section"


def inline(s):
    """Escape, then allow `code`, **bold**, [text](url)."""
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)


def code(c):
    lang = html.escape(c.get("lang") or "text")
    title = html.escape(c.get("title") or lang)
    return (f'<div class="g-code"><div class="bar"><span class="lang">{title}</span>'
            f'<button type="button" class="copy">Copy</button></div>'
            f'<pre data-lang="{lang}"><code class="language-{lang}">{html.escape(c["text"])}</code></pre></div>')


def block(b, ctx):
    if "p" in b: return f'<p>{inline(b["p"])}</p>'
    if "h3" in b:
        i = b.get("id") or slug(b["h3"]); ctx["subs"].append((i, b["h3"]))
        return f'<h3 id="{i}">{inline(b["h3"])}</h3>'
    if "list" in b: return "<ul>" + "".join(f"<li>{inline(x)}</li>" for x in b["list"]) + "</ul>"
    if "code" in b: return code(b["code"])
    if "callout" in b:
        c = b["callout"]; kind = c.get("kind", "note")
        cls = {"note": "", "warn": " warn", "bad": " bad"}.get(kind, "")
        t = html.escape(c.get("title") or {"note": "Note", "warn": "Warning", "bad": "Do not"}.get(kind, "Note"))
        return f'<div class="b-callout g-callout{cls}" role="note"><span class="t">{t}</span>{inline(c["text"])}</div>'
    if "steps" in b:
        out = ['<ol class="g-steps">']
        for s in b["steps"]:
            out.append(f'<li class="g-step"><h3>{inline(s["title"])}</h3>')
            if s.get("body"): out.append(f'<p>{inline(s["body"])}</p>')
            if s.get("code"): out.append(code(s["code"]))
            out.append("</li>")
        return "".join(out) + "</ol>"
    if "table" in b:
        t = b["table"]
        head = "".join(f"<th>{inline(h)}</th>" for h in t["head"])
        rows = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
        cap = f'<caption>{inline(t["caption"])}</caption>' if t.get("caption") else ""
        return f'<div class="b-table-wrap"><table class="b-table">{cap}<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
    if "diagram" in b:
        d = b["diagram"]
        if "flow" in d:
            parts = []
            for i, n in enumerate(d["flow"]):
                if i: parts.append('<span class="a" aria-hidden="true">&rarr;</span>')
                title, _, sub = n.partition("|")
                parts.append(f'<div class="n"><b>{inline(title.strip())}</b>{inline(sub.strip())}</div>')
            body = f'<div class="g-flow">{"".join(parts)}</div>'
        else:
            body = d["svg"]  # trusted, author-provided inline SVG (use token colors via currentColor / CSS vars)
        cap = f'<figcaption>{inline(d["caption"])}</figcaption>' if d.get("caption") else ""
        return f'<figure class="g-fig">{body}{cap}</figure>'
    if "quiz" in b:
        q = b["quiz"]; ctx["quizzes"] += 1; qid = q.get("id") or f'q{ctx["quizzes"]}'
        opts = "".join(f'<button type="button" class="opt">{inline(o)}</button>' for o in q["options"])
        return (f'<div class="g-quiz b-card" data-quiz="{qid}" data-answer="{int(q["answer"])}" '
                f'data-why="{html.escape(q.get("why", ""), quote=True)}"><p class="q"><strong>Check:</strong> {inline(q["q"])}</p>'
                f'{opts}<p class="fb" role="status" aria-live="polite" hidden></p>'
                f'<button type="button" class="retry" hidden>Try again</button></div>')
    if "html" in b: return b["html"]
    raise SystemExit(f"unknown block: {list(b)}")


def build(spec, dark=False):
    mode = spec.get("mode", "guide")
    ctx = {"subs": [], "quizzes": 0}
    toc, secs = [], []
    for n, s in enumerate(spec["sections"], 1):
        sid = s.get("id") or slug(s["title"]); ctx["subs"] = []
        inner = "".join(block(b, ctx) for b in s["blocks"])
        if mode == "course":
            if "quiz" not in json.dumps(s["blocks"]): print(f"WARN: module '{s['title']}' has no quiz", file=sys.stderr)
            head = (f'<p class="b-eyebrow">Module {n:02d}</p><h2 id="{sid}-h">{inline(s["title"])}'
                    f'<span class="g-modmark" hidden></span></h2>')
            secs.append(f'<section id="{sid}" data-mod="{n}">{head}{inner}</section>')
        else:
            secs.append(f'<section id="{sid}"><h2>{inline(s["title"])}</h2>{inner}</section>')
        sub = "".join(f'<li class="sub"><a href="#{i}">{html.escape(t)}</a></li>' for i, t in ctx["subs"])
        toc.append(f'<li data-for="{sid}"><a href="#{sid}">{html.escape(s["title"])}</a></li>{sub}')
    title = spec["title"]; lang = spec.get("lang", "en")
    cfg = {"mode": mode, "key": spec.get("storage_key", "blend-course-" + slug(title)), "themeKey": "blend-guide-theme"}
    toc_html = (f'<nav class="g-toc" aria-label="Table of contents"><details open><summary>Contents</summary>'
                f'<ol>{"".join(toc)}</ol></details></nav>')
    theme = '<button type="button" class="g-theme" aria-label="Toggle light/dark theme">Theme</button>' if dark else ""
    header = f'<header class="b-header"><a href="./" aria-label="Blend">{{{{LOGO}}}}</a><div class="g-top">{theme}</div></header>'
    if mode == "course":
        mins = spec.get("minutes")
        kp = [(len(secs), "Modules"), (ctx["quizzes"], "Quizzes")] + ([(mins, "Minutes")] if mins else [])
        kpis = "".join(f'<div class="b-kpi"><span class="v">{v}</span><span class="l">{l}</span></div>' for v, l in kp)
        hero = (f'<section class="g-hero"><p class="b-eyebrow">{html.escape(spec.get("eyebrow", "Course"))}</p>'
                f'<h1>{inline(title)}</h1><p>{inline(spec.get("intro", ""))}</p><div class="b-kpis">{kpis}</div>'
                f'<div class="g-progress"><div class="bar"><div class="fill"></div></div><small></small></div>'
                f'<button type="button" class="g-reset">Reset progress</button></section>')
        top = hero; h1_in_main = ""
    else:
        top = ""
        h1_in_main = (f'<p class="b-eyebrow">{html.escape(spec.get("eyebrow", "Guide"))}</p><h1>{inline(title)}</h1>'
                      f'<p class="g-lede">{inline(spec.get("intro", ""))}</p>')
    js = (ASSETS / "guide.js").read_text().replace("/*THEME*/", (ASSETS / "theme.js").read_text() if dark else "")
    body = (f'{header}{top}<div class="g-layout">{toc_html}<main class="g-main" id="main">{h1_in_main}{"".join(secs)}</main></div>'
            f'<footer class="b-footer">{inline(spec.get("footer", "Blend360"))}</footer>'
            f'<script type="application/json" id="g-config">{json.dumps(cfg)}</script>'
            f'<script>{js}</script>')
    extra = (ASSETS / "guide.css").read_text()
    return blend_web.build(body, title, lang, spec.get("description", ""), dark, extra)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("out"); ap.add_argument("--dark", action="store_true")
    a = ap.parse_args()
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(Path(a.spec).read_text()), a.dark))
    print("wrote", out)
