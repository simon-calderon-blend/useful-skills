#!/usr/bin/env python3
"""Validate a Blend web document (single HTML file or a folder with index.html).

Usage: validate.py PATH [--kind KIND] [--dark {auto,required,off}] [--strict] [--render] [--json]
KIND sets the weight limit: presentation, article, one-pager, landing, dashboard, report, guide,
portal, api, demo (default: generic, 5 MB).
Exit code 1 on any FAIL (or any WARN with --strict). Stdlib only.
"""
import argparse, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = (HERE.parent / "assets" / "tokens.css").read_text()
BRAND = {h.upper() for h in re.findall(r"#([0-9a-fA-F]{6})\b", TOKENS)}
FORBIDDEN = {"003059": "docx navy, not for web", "1DF4F4": "cyan off-token", "00ECEC": "cyan off-token",
             "0B1E3D": "off-brand navy", "00D4C8": "off-brand teal", "F3F3F0": "docx paper", "304550": "docx slate",
             "0E2841": "Design System content navy, use only inside a product theme"}
LIMITS_KB = {"presentation": 2048, "article": 2048, "one-pager": 500, "landing": 3072, "dashboard": 2048,
             "report": 2048, "guide": 2048, "portal": 2048, "api": 3072, "demo": 3072, "generic": 5120}
HARD_KB = 5120
ALLOWED_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com"}
PINNED = re.compile(r"(@\d+\.\d+\.\d+|/\d+\.\d+\.\d+/)")
OFFPALETTE_WARN = 20


def hex6(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return h.upper()


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


class R:
    def __init__(self): self.rows = []
    def add(self, n, name, status, msg=""): self.rows.append((n, name, status, msg))


def strip_data(t):
    """Drop base64 payloads and comments so only live code is scanned."""
    t = re.sub(r"data:[a-z/+.-]+;base64,[A-Za-z0-9+/=]+", "data:BASE64", t)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"<!--.*?-->", "", t, flags=re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--kind", default="generic")
    ap.add_argument("--dark", default="auto", choices=["auto", "required", "off"])
    ap.add_argument("--strict", action="store_true"); ap.add_argument("--render", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--base", default=None, help="URL base path the site is served under (e.g. /my-guide); default: auto-detect for absolute refs")
    ap.add_argument("--max-kb", type=int, default=None, help="override the weight limit (warn limit and hard limit), e.g. for Starlight dist with mermaid + Pagefind")
    a = ap.parse_args()
    p = Path(a.path)
    files = sorted(p.rglob("*.html")) if p.is_dir() else [p]
    if not files:
        sys.exit("no .html files")
    index = p / "index.html" if p.is_dir() else p
    html = index.read_text(errors="ignore")
    allhtml = "\n".join(f.read_text(errors="ignore") for f in files)
    css_files = [f.read_text(errors="ignore") for f in (p.rglob("*.css") if p.is_dir() else [])]
    raw = allhtml + "\n".join(css_files)
    t = strip_data(raw)
    r = R()

    def local_ref_exists(ref):
        """Resolve a local ref; absolute refs (/base/x) are tried as-is, without --base, and without their first segment."""
        if not ref.startswith("/"):
            return (index.parent / ref).exists()
        root = p if p.is_dir() else index.parent
        rel = ref.lstrip("/"); cands = [root / rel]
        if a.base and rel.startswith(a.base.strip("/") + "/"):
            cands.insert(0, root / rel[len(a.base.strip("/")) + 1:])
        elif not a.base and "/" in rel:
            cands.append(root / rel.split("/", 1)[1])
        return any(c.exists() for c in cands)

    # 1 hex inventory
    found = {hex6(h) for h in re.findall(r"#([0-9a-fA-F]{3,8})\b", t) if len(h) in (3, 6)}
    bad = {h: FORBIDDEN[h] for h in found if h in FORBIDDEN}
    off = sorted(found - BRAND - {"FFFFFF", "000000"} - set(FORBIDDEN))
    if bad:
        r.add(1, "palette", "FAIL", "forbidden: " + ", ".join(f"#{h} ({w})" for h, w in bad.items()))
    elif not (found & BRAND):
        r.add(1, "palette", "FAIL", "no Blend token hex found at all")
    elif len(off) > OFFPALETTE_WARN:
        r.add(1, "palette", "WARN", f"{len(off)} off-palette hex (limit {OFFPALETTE_WARN}); first: " + ", ".join("#" + h for h in off[:8]))
    else:
        r.add(1, "palette", "PASS", f"{len(found & BRAND)} brand hex, {len(off)} derived/off-palette")

    # 2 font
    stacks = re.findall(r"font-family\s*:\s*([^;}{]+)", t) + re.findall(r"--font[\w-]*\s*:\s*([^;}{]+)", t)
    tel = any("pp telegraf" in s.lower() for s in stacks)
    mont = any("montserrat" in s.lower() for s in stacks)
    embedded = bool(re.search(r"@font-face[^}]*PP Telegraf[^}]*data:|@font-face[^}]*data:[^}]*PP Telegraf", t, re.S | re.I))
    ff_file = [u for blk in re.findall(r"@font-face\s*\{[^}]*\}", t, re.I) if re.search(r"PP Telegraf", blk, re.I)
               for u in re.findall(r"url\(\s*['\"]?([^)'\"]+\.(?:otf|woff2?|ttf))", blk, re.I) if not u.startswith(("http", "data:"))]
    file_ok = bool(ff_file) and all(local_ref_exists(u.split("?")[0]) for u in ff_file)
    if tel and embedded:
        r.add(2, "font", "PASS", "PP Telegraf embedded (base64)")
    elif tel and file_ok:
        r.add(2, "font", "PASS", "PP Telegraf loaded from a bundled font file via @font-face (" + ff_file[0].rsplit("/", 1)[-1] + ")")
    elif tel and mont:
        r.add(2, "font", "WARN", "PP Telegraf declared but not embedded: it only renders if installed, otherwise Montserrat/system (use blend_web.py --font embed)")
    elif tel:
        r.add(2, "font", "WARN", "PP Telegraf declared but neither embedded nor Montserrat fallback")
    else:
        r.add(2, "font", "FAIL", "font stack does not start from PP Telegraf")

    # 3 html structure
    probs = []
    if not re.search(r"<html[^>]*\blang=", html, re.I): probs.append("lang")
    if not re.search(r"<title>[^<]+</title>", html, re.I): probs.append("title")
    if not re.search(r'<meta[^>]+name=["\']viewport', html, re.I): probs.append("viewport")
    nodesc = not re.search(r'<meta[^>]+name=["\']description', html, re.I)
    nh1 = len(re.findall(r"<h1[\s>]", html, re.I))
    if nh1 != 1 and a.kind not in ("presentation", "api", "portal"): probs.append(f"h1 count={nh1}")
    if probs:
        r.add(3, "structure", "FAIL", ", ".join(probs))
    elif nodesc:
        r.add(3, "structure", "WARN", "meta description missing (none of the canonical shares has one)")
    else:
        r.add(3, "structure", "PASS", "lang/title/viewport/description/h1 ok")

    # 4 logo
    logo = re.search(r'viewBox="0 0 572 110"', allhtml) and len(re.findall(r"<path", allhtml)) >= 8
    r.add(4, "logo", "PASS" if logo else "FAIL", "logo SVG (572x110) present" if logo else "official Blend logo SVG missing (assets/logo.svg)")

    # 5 contrast: token pairs + heuristic cyan text on light
    pairs = [("1A1A1A", "F4F3F0"), ("314550", "F4F3F0"), ("053057", "F4F3F0"), ("FFFFFF", "053057"),
             ("00EDED", "053057"), ("075089", "F4F3F0"), ("00C6C6", "0B0D0E"), ("F4F3F0", "0B0D0E")]
    weak = [f"{x}/{y}={contrast(x, y):.1f}" for x, y in pairs if contrast(x, y) < 4.5]
    cyan_text = []
    css_text = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", t, re.S | re.I) + [strip_data(c) for c in css_files])
    for m in re.finditer(r"([^{}]{1,300})\{([^{}]{0,2000})\}", css_text):
        sel, body = m.group(1), m.group(2)
        c = re.search(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{6}|var\(--[\w-]+\))", body)
        if not c: continue
        v = c.group(1).upper()
        if v in ("#00EDED", "#A2F3F3", "VAR(--BLEND-CYAN)", "VAR(--BLEND-CYAN-SOFT)", "VAR(--NEON-TURQUOISE)", "VAR(--LIGHT-TURQUOISE)"):
            bg = re.search(r"background(?:-color)?\s*:\s*([^;]+)", body)
            dark = bg and re.search(r"053057|0B0D0E|1A1A1A|navy|black|washed|dark|gray", bg.group(1), re.I)
            ctx_dark = re.search(r"hero|band|slide|dark|cta|topbar|footer", sel, re.I)
            if not dark and not ctx_dark:
                cyan_text.append(sel.strip()[:40])
    if weak:
        r.add(5, "contrast", "FAIL", "token pairs below 4.5:1: " + ", ".join(weak))
    elif cyan_text:
        r.add(5, "contrast", "WARN", "cyan/turquoise as text where the rule has no dark background (verify): " + "; ".join(cyan_text[:4]))
    else:
        r.add(5, "contrast", "PASS", "token pairs >= 4.5:1; no cyan text on light detected (heuristic)")

    # 6 external resources
    loaders = re.findall(r"""<(?:script|img|iframe|source|video|audio)\b[^>]*\bsrc\s*=\s*["'](https?://[^"']+)""", t, re.I)
    loaders += re.findall(r"""<link\b[^>]*\bhref\s*=\s*["'](https?://[^"']+)""", t, re.I)
    urls = set(loaders) | set(re.findall(r"url\(\s*['\"]?(https?://[^)'\"]+)", t))
    badx = []
    for u in urls:
        host = re.match(r"https?://([^/]+)", u)[1]
        if host == "share.blend360.com":
            continue
        if host not in ALLOWED_HOSTS or (host == "cdnjs.cloudflare.com" and not PINNED.search(u)):
            badx.append(u[:70])
    broken = []
    base = index.parent
    for ref in re.findall(r"""(?:src|href)\s*=\s*["']([^"'#:?]+\.(?:css|js|svg|png|jpe?g|webp|json|csv|woff2?|ttf|otf))["']""", t):
        if not local_ref_exists(ref):
            broken.append(ref)
    if badx or broken:
        r.add(6, "resources", "FAIL", ("unpinned/disallowed: " + ", ".join(sorted(badx)[:4]) + ". ") * bool(badx) + ("missing local: " + ", ".join(broken[:4])) * bool(broken))
    else:
        r.add(6, "resources", "PASS", f"{len(urls)} external urls, all allowed/pinned; local refs resolve")

    # 7 dark
    has_media = "prefers-color-scheme" in t
    has_attr = bool(re.search(r"\[data-theme", t))
    if a.dark == "off":
        r.add(7, "dark", "PASS", "dark not requested")
    elif has_media != has_attr:
        r.add(7, "dark", "FAIL", "only one of prefers-color-scheme / [data-theme] present (need both)")
    elif a.dark == "required" and not has_media:
        r.add(7, "dark", "FAIL", "dark required but missing")
    else:
        r.add(7, "dark", "PASS", "both blocks present" if has_media else "no dark (optional by decision; use --dark to build with it)")

    # 8 weight
    size_kb = sum(f.stat().st_size for f in (p.rglob("*") if p.is_dir() else [p]) if f.is_file()) / 1024
    lim = a.max_kb or LIMITS_KB.get(a.kind, HARD_KB)
    hard = a.max_kb or HARD_KB
    st = "FAIL" if size_kb > hard else ("WARN" if size_kb > lim else "PASS")
    r.add(8, "weight", st, f"{size_kb:.0f} KB (limit {lim} KB for '{a.kind}', error over {hard} KB)")

    # 9 render
    if a.render and re.search(r"""(?:src|href)\s*=\s*["']/(?!/)[^"']+\.(?:css|js|otf|woff2?)""", html):
        r.add(9, "render", "SKIP", "root-absolute asset paths (site base path): file:// cannot load them; serve the folder over http and check 1280/390 px")
    elif a.render:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            msgs = []
            with sync_playwright() as pw:
                b = pw.chromium.launch()
                for w, h in ((1280, 720), (390, 844)):
                    pg = b.new_page(viewport={"width": w, "height": h}); errs = []
                    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                    pg.goto(index.resolve().as_uri()); pg.wait_for_timeout(400)
                    ov = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    if ov > 1 and a.kind != "presentation": msgs.append(f"{w}px overflow {ov}px")
                    if errs: msgs.append(f"{w}px console errors: {errs[0][:60]}")
                b.close()
            r.add(9, "render", "FAIL" if msgs else "PASS", "; ".join(msgs) or "1280 and 390 px: no horizontal overflow, console clean")
        except ImportError:
            r.add(9, "render", "SKIP", "playwright not installed; take 1280/390 px screenshots with chrome-devtools instead")
    else:
        r.add(9, "render", "SKIP", "run with --render (needs playwright) or check 1280/390 px manually")

    # 10 secrets / PII
    pats = {"AWS key": r"AKIA[0-9A-Z]{16}", "JWT": r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}",
            "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}", "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            "AWS account ARN": r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:"}
    hits = [k for k, v in pats.items() if re.search(v, t)]
    emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", t)) - {"you@example.com"}
    emails = {e for e in emails if not e.lower().endswith((".png", ".svg", ".jpg"))}
    if hits:
        r.add(10, "secrets/PII", "FAIL", "found: " + ", ".join(hits))
    elif emails:
        r.add(10, "secrets/PII", "WARN", f"{len(emails)} e-mail address(es) in the page; confirm they may be public")
    else:
        r.add(10, "secrets/PII", "PASS", "no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)")

    if a.json:
        print(json.dumps([dict(n=n, check=c, status=s, msg=m) for n, c, s, m in r.rows], indent=1))
    else:
        print(f"validate: {index}  kind={a.kind}")
        for n, c, s, m in r.rows:
            print(f"{n:>2} {c:<12} {s:<4} {m}")
    fail = any(s == "FAIL" for _, _, s, _ in r.rows)
    warn = any(s == "WARN" for _, _, s, _ in r.rows)
    sys.exit(1 if fail or (a.strict and warn) else 0)


if __name__ == "__main__":
    main()
