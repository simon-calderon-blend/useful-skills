#!/usr/bin/env python3
"""Build a Blend report (self-contained HTML) from a JSON spec.

Usage: build_report.py SPEC.json OUT.html [--variant simple|sidebar|scorecard] [--dark]
The spec's "variant" key is used when --variant is not given. See ../references/spec.md for the schema
and ../examples/*.json for working specs. Reuses blend-web-core (tokens, components, logo) through
blend_web.build(); only the report layer (assets/report.css) lives here. Stdlib only.
"""
import argparse, html, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "blend-web-core" / "scripts"))
from blend_web import build  # noqa: E402

CSS = (HERE.parent / "assets" / "report.css").read_text()
SEV = {"critical": ("bad", "Critical"), "high": ("bad", "High"), "medium": ("warn", "Medium"),
       "low": ("", "Low"), "info": ("info", "Info")}
SEV_ES = {"critical": "Crítico", "high": "Alto", "medium": "Medio", "low": "Bajo", "info": "Info"}
STATE = {"ok": "ok", "warn": "warn", "bad": "bad", "": ""}
L = {"en": dict(summary="Executive summary", findings="Findings", recs="Recommendations", evidence="Evidence",
                rec="Recommendation", appendix="Appendix", contents="Contents", status="Status", date="Date",
                audience="Audience", internal="Internal", client="Client", draft="Draft", final="Final",
                illus="Illustrative data", owner="Owner", score="Score", source="Source"),
     "es": dict(summary="Resumen ejecutivo", findings="Hallazgos", recs="Recomendaciones", evidence="Evidencia",
                rec="Recomendación", appendix="Anexo", contents="Contenido", status="Estado", date="Fecha",
                audience="Audiencia", internal="Interna", client="Cliente", draft="Borrador", final="Final",
                illus="Datos ilustrativos", owner="Responsable", score="Puntaje", source="Fuente")}


def esc(s):
    """Escape text; `x` becomes <code>x</code>."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(str(s), quote=False))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "s"


def chip(sev, lang):
    cls, label = SEV[sev]
    label = SEV_ES[sev] if lang == "es" else label
    return f'<span class="b-chip {cls} sev" data-sev="{sev}">{label}</span>'.replace("  ", " ")


def table(t):
    num = set(t.get("num", []))
    head = "".join(f'<th scope="col"{" class=num" if i in num else ""}>{esc(h)}</th>' for i, h in enumerate(t["headers"]))
    rows = "".join("<tr>" + "".join(f'<td{" class=num" if i in num else ""}>{esc(c)}</td>' for i, c in enumerate(r)) + "</tr>"
                   for r in t["rows"])
    cap = f"<caption>{esc(t['caption'])}</caption>" if t.get("caption") else ""
    wide = " r-wide" if len(t["headers"]) >= 5 else ""
    return (f'<div class="b-table-wrap"><table class="b-table{wide}">{cap}<thead><tr>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def code(c):
    cap = f"<figcaption>{esc(c['caption'])}</figcaption>" if c.get("caption") else ""
    return f'<figure><pre class="r-code" tabindex="0"><code>{html.escape(c["text"])}</code></pre>{cap}</figure>'


def evidence_html(ev, lang):
    """ev: str | dict(table|code|text) | list of those."""
    items = ev if isinstance(ev, list) else [ev]
    out = []
    for e in items:
        if isinstance(e, str):
            out.append(f"<p>{esc(e)}</p>")
        elif "table" in e:
            out.append(table(e["table"]))
        elif "code" in e:
            out.append(code(e["code"]))
        elif "text" in e:
            out.append(f"<p>{esc(e['text'])}</p>")
    boxed = any(not isinstance(e, str) and ("table" in e or "code" in e) for e in items)
    return f'<div class="r-evidence{" plain" if boxed else ""}"><span class="b-label">{L[lang]["evidence"]}</span>{"".join(out)}</div>'


def finding(f, lang):
    sev = f["severity"]
    rec = (f'<p class="r-rec"><strong>{L[lang]["rec"]}.</strong> {esc(f["recommendation"])}</p>'
           if f.get("recommendation") else "")
    return (f'<article class="r-finding" id="{f["id"].lower()}" data-sev="{sev}"><header>'
            f'<span class="id">{esc(f["id"])}</span><h3>{esc(f["title"])}</h3>{chip(sev, lang)}</header>'
            f'<p>{esc(f["text"])}</p>{evidence_html(f["evidence"], lang)}{rec}</article>')


def callout(c):
    kind = {"note": "", "key": " key", "warning": " warn", "warn": " warn", "bad": " bad"}[c.get("kind", "note")]
    t = f'<span class="t">{esc(c["title"])}</span>' if c.get("title") else ""
    return f'<div class="b-callout{kind}" role="note">{t}<p>{esc(c["text"])}</p></div>'


def recs(items, lang):
    lis = []
    for r in items:
        meta = []
        if r.get("priority"):
            p = r["priority"]
            cls = {"high": "bad", "medium": "warn", "low": ""}.get(p, "")
            plabel = {"high": "Alta", "medium": "Media", "low": "Baja"}.get(p, p) if lang == "es" else str(p).capitalize()
            meta.append(f'<span class="b-chip {cls}">{esc(plabel)}</span>')
        if r.get("owner"):
            meta.append(f'<span>{L[lang]["owner"]}: {esc(r["owner"])}</span>')
        m = f'<div class="m">{"".join(meta)}</div>' if meta else ""
        lis.append(f'<li><div><span class="t">{esc(r["title"])}</span>{esc(r.get("text", ""))}{m}</div></li>')
    return f'<ol class="r-recs">{"".join(lis)}</ol>'


def score(s, lang):
    rows = []
    for it in s["items"]:
        mx = it.get("max", 5)
        pct = max(0, min(100, round(100 * it["score"] / mx)))
        st = STATE[it.get("state", "")]
        rows.append(f'<div class="r-score-row"><span>{esc(it["label"])}</span>'
                    f'<span class="bar" role="img" aria-label="{it["score"]} / {mx}"><i style="width:{pct}%"></i></span>'
                    f'<span class="n">{it["score"]} / {mx}</span>'
                    + (f'<span class="b-chip {st}">{esc(it.get("state_label", st))}</span>' if st else "<span></span>")
                    + "</div>")
    return f'<div class="r-score">{"".join(rows)}</div>'


def block(b, lang):
    k = next(iter(b))
    v = b[k]
    if k == "p":
        return f'<div class="r-prose"><p>{esc(v)}</p></div>'
    if k == "h3":
        return f"<h3>{esc(v)}</h3>"
    if k == "callout":
        return callout(v)
    if k == "findings":
        return f'<div class="r-findings">{"".join(finding(f, lang) for f in v)}</div>'
    if k == "table":
        return table(v)
    if k == "code":
        return code(v)
    if k == "recommendations":
        return recs(v, lang)
    if k == "kpis":
        return kpis(v)
    if k == "score":
        return score(v, lang)
    if k == "columns":
        return f'<div class="r-two">{"".join(f"<div class=r-stack>{blocks(c, lang)}</div>" for c in v)}</div>'
    if k == "html":  # escape hatch for a hand-made figure (inline SVG); caller owns the markup
        return v
    raise SystemExit(f"unknown block: {k}")


def blocks(bs, lang):
    return "".join(block(b, lang) for b in bs)


def kpis(items, cls=""):
    t = "".join(f'<div class="b-kpi"><span class="v">{esc(k["value"])}</span><span class="l">{esc(k["label"])}</span>'
                + (f'<span class="c">{esc(k["caption"])}</span>' if k.get("caption") else "") + "</div>" for k in items)
    return f'<div class="b-kpis r-kpis {cls}">{t}</div>'


def section(s, i, lang, appendix=False):
    sid = s.get("id") or slug(s["title"])
    n = (f'{L[lang]["appendix"]} {chr(64 + i)}' if appendix else f"{i}.")
    cls = ' class="r-appendix"' if appendix else ""
    return (f'<section id="{sid}"{cls}><h2><span class="r-n">{n}</span>{esc(s["title"])}</h2>'
            f'<div class="r-stack">{blocks(s["blocks"], lang)}</div></section>')


def render(spec, variant, dark=False):
    lang = spec.get("lang", "es")
    T = L[lang]
    variant = variant or spec.get("variant", "simple")
    secs = spec.get("sections", [])
    apps = spec.get("appendices", [])
    sm = spec["summary"]
    toc = [("resumen", T["summary"])] + [(s.get("id") or slug(s["title"]), s["title"]) for s in secs] \
        + [(s.get("id") or slug(s["title"]), f'{T["appendix"]} {chr(65 + i)}: {s["title"]}') for i, s in enumerate(apps)]
    toc_html = ('<nav class="r-toc" aria-label="%s"><span class="b-label">%s</span><ol>%s</ol></nav>'
                % (T["contents"], T["contents"], "".join(f'<li><a href="#{i}">{esc(t)}</a></li>' for i, t in toc)))
    inline_toc = toc_html.replace('class="r-toc"', 'class="r-toc r-toc-inline"')

    meta = []
    if spec.get("status"):
        meta.append(f'<li><strong>{T["status"]}:</strong> {esc(spec["status"])}</li>')
    if spec.get("date"):
        meta.append(f'<li><strong>{T["date"]}:</strong> {esc(spec["date"])}</li>')
    aud = spec.get("audience", "internal")
    meta.append(f'<li><strong>{T["audience"]}:</strong> {T["client"] if aud == "client" else T["internal"]}</li>')
    if spec.get("author"):
        meta.append(f'<li>{esc(spec["author"])}</li>')
    if spec.get("illustrative"):  # a chip in the meta row, not inside the eyebrow
        meta.append(f'<li><span class="b-chip info">{T["illus"]}</span></li>')
    eyebrow = spec.get("eyebrow", "")

    mast = f'<header class="r-masthead">{{{{LOGO}}}}<p class="b-eyebrow">{esc(eyebrow)}</p></header>'
    title = (f'<div class="r-title"><hr class="r-rule"><h1>{esc(spec["title"])}</h1>'
             + (f'<p class="r-standfirst">{esc(spec["subtitle"])}</p>' if spec.get("subtitle") else "")
             + f'<ul class="r-meta">{"".join(meta)}</ul></div>')

    summary = (f'<section id="resumen" class="r-hero" aria-labelledby="resumen-h"><h2 id="resumen-h">{T["summary"]}</h2>'
               + (f'<p class="r-verdict">{esc(sm["verdict"])}</p>' if sm.get("verdict") else "")
               + "".join(f"<p>{esc(p)}</p>" for p in sm.get("text", []))
               + (kpis(sm["kpis"]) if sm.get("kpis") else "") + "</section>")

    body_main = summary + "".join(section(s, i + 1, lang) for i, s in enumerate(secs))
    body_main += "".join(section(s, i + 1, lang, True) for i, s in enumerate(apps))
    show_toc = variant != "scorecard" and len(secs) + len(apps) + 1 > 3
    tocs = inline_toc if show_toc else ""
    if variant == "sidebar":
        layout = mast + f'<div class="r-layout">{toc_html}<div class="r-shell">{title}{tocs}<main id="main">{body_main}</main></div></div>'
    else:
        layout = mast + f'<div class="r-shell">{title}{tocs}<main id="main">{body_main}</main></div>'
    src = f'<p>{T["source"]}: {esc(spec["source"])}</p>' if spec.get("source") else ""
    foot = (f'<footer class="r-foot"><div class="r-foot-in">{{{{LOGO}}}}<div>{src}<p>{esc(spec.get("footer", ""))}'
            f'{" " + T["illus"] + "." if spec.get("illustrative") else ""}</p></div></div></footer>')
    return build(layout + foot, spec["title"], lang, spec.get("description", spec.get("subtitle", "")), dark, CSS + ((HERE.parent / "assets" / "report-dark.css").read_text() if dark else "")) \
        .replace("<body>", f'<body data-variant="{variant}">', 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("out")
    ap.add_argument("--variant", choices=["simple", "sidebar", "scorecard"])
    ap.add_argument("--dark", action="store_true", help="opt-in dark theme: core tokens-dark.css + light/dark toggle + assets/report-dark.css")
    a = ap.parse_args()
    out = render(json.loads(Path(a.spec).read_text()), a.variant, a.dark)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(out)
    print("wrote", a.out, f"({len(out) // 1024} KB)")


if __name__ == "__main__":
    main()
