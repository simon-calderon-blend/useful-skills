#!/usr/bin/env python3
"""Validate a Blend article or commercial page: core validate.py + editorial checks.

Usage: validate_editorial.py PATH --kind article|one-pager|landing [--client] [--pages N] [--strict] [--render]
Runs ../../blend-web-core/scripts/validate.py (subprocess, same --kind), then adds:
 E1 prose measure 42-56ch (60-80 characters in PP Telegraf) | E2 body line-height >= 1.6 | E3 body font >= 16px | E4 exactly one h1
 E5 CTA present (one-pager, landing) | E6 @page defined + sheet count (one-pager)
 E7 co-branding: topbar "Blend x client", img alt, client image <= 200 KB (auto when --client or a cobrand element exists)
 E8 no horizontal scroll at 375 px (Playwright; otherwise SKIP: use chrome-devtools resize_page 375)
Exit 1 on any FAIL (WARN with --strict). Stdlib only.
"""
import argparse, base64, re, subprocess, sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "blend-web-core" / "scripts" / "validate.py"
ap = argparse.ArgumentParser()
ap.add_argument("path"); ap.add_argument("--kind", default="article", choices=["article", "one-pager", "landing"])
ap.add_argument("--client", action="store_true"); ap.add_argument("--pages", type=int)
ap.add_argument("--strict", action="store_true"); ap.add_argument("--render", action="store_true")
a = ap.parse_args()

p = Path(a.path)
index = p / "index.html" if p.is_dir() else p
cmd = [sys.executable, str(CORE), str(p), "--kind", a.kind] + (["--strict"] if a.strict else []) + (["--render"] if a.render else [])
core = subprocess.run(cmd, capture_output=True, text=True)
print(core.stdout.rstrip())
print("-- editorial checks")

raw = index.read_text(errors="ignore")
if p.is_dir():
    raw += "\n".join(f.read_text(errors="ignore") for f in p.rglob("*.css"))
code = re.sub(r"data:[a-z/+.-]+;base64,[A-Za-z0-9+/=]+", "data:B64", raw)
css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", code, re.S | re.I)) + "\n" + (code if p.is_dir() else "")
css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
rows = []
add = lambda n, s, m: rows.append((n, s, m))


def vars_(c):
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", c)}


V = vars_(css)


def resolve(v, depth=0):
    m = re.fullmatch(r"var\((--[\w-]+)(?:\s*,[^)]*)?\)", v.strip())
    return resolve(V[m[1]], depth + 1) if m and m[1] in V and depth < 5 else v.strip()


def rules(c):
    return [(s.strip(), b) for s, b in re.findall(r"([^{}@]+)\{([^{}]*)\}", c)]


# E1 prose measure: any rule whose selector mentions prose/article/lede/measure sets max-width in ch (42-56) or px (460-620).
# The target is 60-80 characters per line. `ch` is the width of the 0, which in PP Telegraf is 1.5x the average letter
# (measured 2026-11-13: 68ch = 104 characters), so the ch range that gives 60-80 characters is 42-56.
meas = []
for sel, body in rules(css):
    if re.fullmatch(r"[.\w\s>,-]*(prose|article|post|body-copy|copy|measure|content|lede)[\w\s>,.-]*", sel.strip(), re.I) or re.search(r"(^|[\s>,])p$", sel.strip()):
        for m in re.finditer(r"max-width\s*:\s*([^;]+)", body):
            meas.append((sel[:30], resolve(m[1])))
ok_ch, ok_px, bad = [], [], []
for sel, v in meas:
    m = re.fullmatch(r"([\d.]+)(ch|px)", v)
    if not m: continue
    n = float(m[1])
    (ok_ch if m[2] == "ch" and 42 <= n <= 56 else ok_px if m[2] == "px" and 460 <= n <= 620 else bad).append(f"{sel}={v}")
if ok_ch: add("E1 prose measure", "PASS", f"{ok_ch[0]}")
elif ok_px: add("E1 prose measure", "WARN", f"{ok_px[0]} is in px (about 60-80 characters); prefer ch")
elif bad: add("E1 prose measure", "FAIL", "outside 42-56ch (60-80 characters in PP Telegraf): " + ", ".join(bad[:3]))
else: add("E1 prose measure", "FAIL", "no max-width on a prose/article container")


# E2/E3 body line-height and font size
def px(v, base=16):
    m = re.fullmatch(r"([\d.]+)(px|rem|em)", resolve(v))
    return float(m[1]) * (1 if m[2] == "px" else base) if m else None


lh = fs = None
for sel, body in rules(css):
    if re.fullmatch(r"(html\s*,\s*)?body|html|body\s*,\s*html|:root", sel):
        m = re.search(r"font\s*:\s*[^;]*?([\d.]+(?:px|rem|em)?)\s*/\s*([\d.]+(?:px|rem|em)?)", body)
        if m:
            fs = px(m[1]) if re.search(r"[a-z]", m[1]) else fs
            lh = float(m[2]) if not re.search(r"[a-z]", m[2]) else lh
        m1 = re.search(r"(?<![-\w])line-height\s*:\s*([^;]+)", body)
        if m1:
            r = resolve(m1[1]); lh = float(r) if re.fullmatch(r"[\d.]+", r) else (px(r) and px(r) / (fs or 16))
        m2 = re.search(r"(?<![-\w])font-size\s*:\s*([^;]+)", body)
        if m2: fs = px(m2[1]) or fs
for sel, body in rules(css):  # prose rules may override
    if re.fullmatch(r"\.[\w-]*prose", sel.strip(), re.I):
        m1 = re.search(r"(?<![-\w])line-height\s*:\s*([\d.]+)\s*(?:;|$)", body)
        if m1: lh = float(m1[1])
        m2 = re.search(r"(?<![-\w])font-size\s*:\s*([^;]+)", body)
        if m2 and px(m2[1]): fs = px(m2[1])
if lh is None: add("E2 line-height", "FAIL", "no body/prose line-height found")
else: add("E2 line-height", "PASS" if lh >= 1.6 else "FAIL", f"{lh:.2f} (min 1.6)")
if fs is None: add("E3 body font", "WARN", "no explicit body font-size (browser default 16px assumed)")
else: add("E3 body font", "PASS" if fs >= 16 else "FAIL", f"{fs:.1f}px (min 16)")

# E4 one h1
n = len(re.findall(r"<h1[\s>]", code, re.I))
add("E4 single h1", "PASS" if n == 1 else "FAIL", f"{n} h1")

# E5 CTA
links = re.findall(r"<(a|button)\b([^>]*)>", code, re.I)
cta = [x for t, x in links if re.search(r"class=\"[^\"]*(btn|cta)", x) and (t.lower() == "button" or re.search(r"href=\"(https?://|mailto:|#)[^\"]+", x))]
if a.kind == "article": add("E5 CTA", "PASS", "not required for article" + (f" ({len(cta)} found)" if cta else ""))
else: add("E5 CTA", "PASS" if cta else "FAIL", f"{len(cta)} CTA link(s)" if cta else "no a/button with btn|cta class and href/mailto")

# E6 @page
if a.kind == "one-pager":
    pg = re.search(r"@page\s*\{[^}]*size\s*:\s*([^;}]+)", css)
    sheets = len(re.findall(r'class="[^"]*\be-sheet\b', code))
    msg = []
    if not pg: add("E6 @page", "FAIL", "no @page { size } rule")
    else:
        msg.append(f"@page size {pg[1].strip()}")
        msg.append(f"{sheets or '?'} sheet(s)")
        if a.pages and sheets != a.pages: add("E6 @page", "FAIL", ", ".join(msg) + f"; expected {a.pages}")
        else: add("E6 @page", "PASS" if sheets else "WARN", ", ".join(msg) + ("" if sheets else "; no .e-sheet markers, page count unverified"))
else: add("E6 @page", "PASS", "n/a (not a one-pager)")

# E7 cobranding
has_cb = bool(re.search(r'class="[^"]*cobrand', code)) or a.client
if has_cb:
    probs = []
    top = re.search(r"<header[^>]*class=\"[^\"]*(topbar|b-header)[^\"]*\"[^>]*>(.*?)</header>", code, re.S | re.I)
    if not top: probs.append("no topbar header")
    else:
        txt = re.sub(r"<[^>]+>", " ", re.sub(r"<svg.*?</svg>", " ", top[2], flags=re.S))
        has_logo = "<svg" in top[2]
        if not has_logo: probs.append("Blend logo missing in topbar")
        if not re.search(r"[×x✕]", txt + top[2]): probs.append("no x separator")
        if not (re.search(r"<img[^>]+alt=\"[^\"]+\"", top[2]) or re.sub(r"[×x\s]", "", txt)): probs.append("client name/logo missing")
    for m in re.finditer(r"<img\b([^>]*)>", raw):
        at = m[1]
        if not re.search(r"\balt=\"[^\"]+\"", at): probs.append("img without alt")
        d = re.search(r"base64,([A-Za-z0-9+/=]+)", at)
        if d and len(d[1]) * 3 / 4 / 1024 > 200: probs.append("client image > 200 KB")
    if re.search(r"confidential", code, re.I) is None: add("E7 co-branding", "WARN", "no 'Confidential' marker in footer" + ("; " + ", ".join(probs) if probs else ""))
    else: add("E7 co-branding", "FAIL" if probs else "PASS", ", ".join(probs) or "topbar Blend x client, alts ok, footer confidential")
else: add("E7 co-branding", "PASS", "n/a (no client)")

# E8 375 px
if a.render:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 375, "height": 800}); pg.goto(index.resolve().as_uri()); pg.wait_for_timeout(300)
            ov = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"); b.close()
        add("E8 375px", "FAIL" if ov > 1 else "PASS", f"horizontal overflow {ov}px")
    except ImportError:
        add("E8 375px", "SKIP", "playwright not installed; use chrome-devtools resize_page 375 and compare scrollWidth")
else:
    add("E8 375px", "SKIP", "run with --render (Playwright) or measure with chrome-devtools at 375 px")

for n, s, m in rows: print(f"{n:<18} {s:<4} {m}")
fail = core.returncode != 0 or any(s == "FAIL" for _, s, _ in rows)
warn = any(s == "WARN" for _, s, _ in rows)
sys.exit(1 if fail or (a.strict and warn) else 0)
