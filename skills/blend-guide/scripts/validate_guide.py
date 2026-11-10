#!/usr/bin/env python3
"""Validate a Blend guide or course: runs blend-web-core validate.py, then the guide-specific checks.

Usage: validate_guide.py PATH [--kind guide] [--course] [--dark {auto,required,off}] [--strict]
PATH is an HTML file, a folder with index.html (single page or built Starlight site), or a Starlight
source project (astro.config.* present). Output PASS/WARN/FAIL, exit 1 on FAIL. Stdlib only.
Guide checks (G1-G6): one h1 per page, internal links/anchors resolve, TOC when >3 sections, code blocks with a
language, Starlight theme tokens (--blend-*), course (localStorage in try/catch, >=1 quiz per module).
"""
import argparse, re, subprocess, sys
from pathlib import Path

STARLIGHT_MAX_KB = 8192
CORE = Path(__file__).resolve().parent.parent.parent / "blend-web-core" / "scripts" / "validate.py"
rows = []


def add(n, name, st, msg): rows.append((n, name, st, msg))


def pages(p):
    return sorted(p.rglob("*.html")) if p.is_dir() else [p]


def strip(t):
    t = re.sub(r"<(script|style)\b.*?</\1>", "", t, flags=re.S | re.I)
    return re.sub(r"<!--.*?-->", "", t, flags=re.S)


def ids_of(t):
    return set(re.findall(r'\bid=["\']([^"\']+)["\']', t)) | set(re.findall(r'<a\b[^>]*\bname=["\']([^"\']+)["\']', t))


def resolve(root, page, href):
    """Return True if the internal href resolves inside the site, None if it is external/ignored."""
    if re.match(r"^(https?:|mailto:|tel:|data:|javascript:)", href) or href.startswith("//"):
        return None
    path, _, frag = href.partition("#"); path = path.split("?")[0]
    if not path:
        target = page
    elif path.startswith("/"):
        rel = path.lstrip("/")
        parts = rel.split("/")
        cands = [root / rel]
        if len(parts) > 1:  # site served under /<slug>/ (Blend Share base path): the folder may be named anything (dist)
            cands.insert(0 if parts[0] == root.name else len(cands), root / "/".join(parts[1:]))
        target = next((c for c in cands if c.exists()), cands[0])
    else:
        target = (page.parent / path)
    if target.is_dir():
        if path in ("./", ".", "/") and not (target / "index.html").exists():
            return True  # link to the site root while the file is checked on its own
        target = target / "index.html"
    if not target.exists() and not target.suffix:
        alt = Path(str(target) + ".html")
        target = alt if alt.exists() else target
    if not target.exists():
        return False
    if frag and target.suffix == ".html":
        return frag in ids_of(target.read_text(errors="ignore"))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--kind", default="guide")
    ap.add_argument("--course", action="store_true", help="force course checks (auto when data-mod is found)")
    ap.add_argument("--dark", default="auto", choices=["auto", "required", "off"])
    ap.add_argument("--strict", action="store_true"); ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    p = Path(a.path).resolve()
    source_proj = p.is_dir() and any(p.glob("astro.config.*"))
    print(f"validate_guide: {p}  kind={a.kind}")

    # core
    core_rc = None
    if not source_proj:
        cmd = [sys.executable, str(CORE), str(p), "--kind", a.kind, "--dark", a.dark] + (["--render"] if a.render else [])
        if p.is_dir() and any('content="Starlight' in f.read_text(errors="ignore") for f in list(p.glob("*.html"))[:3]):
            cmd += ["--max-kb", str(STARLIGHT_MAX_KB)]  # mermaid + Pagefind make a Starlight dist 6+ MB; the core's 5 MB hard limit does not fit it
        r = subprocess.run(cmd, capture_output=True, text=True)
        core_rc = r.returncode
        fails = [l for l in r.stdout.splitlines() if re.match(r"\s*\d+ \S+\s+FAIL", l)]
        if "--max-kb" in cmd and len(fails) == 1 and re.match(r"\s*4 logo", fails[0]):
            core_rc = 0  # Starlight header uses the Blend symbol (canon: ds-best-practices), not the 572x110 wordmark
            r.stdout += "\n(note: check 4 FAIL is expected on a Starlight build: the header carries the Blend symbol, not the full logo; not counted)"
        print("--- blend-web-core validate.py ---"); print(r.stdout.rstrip()); print("--- guide checks ---")

    css_dirs = [p] if p.is_dir() else []
    htmls = [] if source_proj else pages(p)
    texts = {f: f.read_text(errors="ignore") for f in htmls}
    starlight = source_proj or any('content="Starlight' in t for t in texts.values())

    if htmls:
        # G1 single h1 per page
        bad = [f for f, t in texts.items() if len(re.findall(r"<h1[\s>]", strip(t), re.I)) != 1 and f.name != "404.html"]
        add("G1", "one h1", "FAIL" if bad else "PASS",
            f"{len(bad)}/{len(htmls)} page(s) without exactly one h1: " + ", ".join(str(f.relative_to(p) if p.is_dir() else f.name) for f in bad[:3]) if bad else f"{len(htmls)} page(s), one h1 each")

        # G2 internal links and anchors
        root = p if p.is_dir() else p.parent
        broken = []
        for f, t in texts.items():
            for href in re.findall(r'<a\b[^>]*\bhref=["\']([^"\']+)["\']', strip(t)):
                if resolve(root, f, href) is False:
                    broken.append(f"{f.name}:{href[:50]}")
        add("G2", "links/anchors", "FAIL" if broken else "PASS",
            (f"{len(broken)} unresolved, first: " + "; ".join(broken[:4])) if broken else "all internal links and #anchors resolve")

        # G3 TOC when more than 3 sections (h2)
        short = []
        for f, t in texts.items():
            s = strip(t)
            if len(re.findall(r"<h2[\s>]", s, re.I)) > 3:
                navs = re.findall(r"<nav\b[^>]*>", s, re.I)
                ok = any(re.search(r'aria-label=["\'][^"\']*(contents|table of|on this page|toc|sidebar|navigation)', n, re.I) or re.search(r'class=["\'][^"\']*(toc|sidebar)', n, re.I) for n in navs) \
                    or re.search(r'class=["\'][^"\']*\b(toc|g-toc|sl-sidebar|right-sidebar)\b', s)
                if not ok:
                    short.append(f.name)
        add("G3", "toc", "FAIL" if short else "PASS", f"{len(short)} page(s) with >3 sections and no TOC: " + ", ".join(short[:3]) if short else "TOC present wherever there are more than 3 sections")

        # G4 code blocks with lang
        nolang, total = [], 0
        for f, t in texts.items():
            for m in re.finditer(r"<pre\b([^>]*)>(.*?)</pre>", strip(t), re.S | re.I):
                attrs, inner = m.group(1), m.group(2)
                if re.search(r'class=["\'][^"\']*\bmermaid\b', attrs):
                    continue
                total += 1
                if not (re.search(r'data-(?:lang|language)=["\'][\w+#.-]+', attrs) or re.search(r'<code[^>]*class=["\'][^"\']*language-[\w+-]+', inner)):
                    nolang.append(f.name)
        add("G4", "code lang", "FAIL" if nolang else "PASS", f"{len(nolang)}/{total} code block(s) without a language" if nolang else f"{total} code block(s), all with a language")

    # G5 Starlight theme
    if starlight:
        themes = [f for f in p.rglob("blend-theme.css")] if p.is_dir() else []
        if themes:
            c = themes[0].read_text()
            need = ["--blend-neon", "--blend-washed-blue", "--blend-light-turquoise", "--blend-off-white", "--blend-cool-gray", "#075089", "#00c6c6"]
            miss = [n for n in need if n.lower() not in c.lower()]
            add("G5", "theme", "FAIL" if miss else "PASS", f"{themes[0].name}: missing {', '.join(miss)}" if miss else f"{themes[0].name} defines the --blend-* tokens, accent #075089 / #00c6c6")
        else:
            cands = [f for f in p.rglob("*.css") if "--blend-neon" in f.read_text(errors="ignore")] if p.is_dir() else []
            if cands:
                c = cands[0].read_text(errors="ignore")
                ok = "#075089" in c and "#00c6c6" in c
                add("G5", "theme", "WARN" if ok else "FAIL", f"no blend-theme.css (built site); tokens found in {cands[0].name}" + ("" if ok else " but accents #075089/#00c6c6 missing"))
            else:
                add("G5", "theme", "FAIL", "Starlight site without blend-theme.css or any CSS defining --blend-* tokens")
        if source_proj:
            cfg = next(p.glob("astro.config.*")).read_text()
            add("G5b", "customCss", "PASS" if "blend-theme.css" in cfg else "FAIL", "astro.config loads blend-theme.css" if "blend-theme.css" in cfg else "astro.config does not list blend-theme.css in customCss")

    # G6 course
    is_course = a.course or any(re.search(r"<section\b[^>]*data-mod=", t) for t in texts.values())
    if is_course:
        allt = "\n".join(texts.values())
        scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", allt, re.S | re.I)
        uses = [s for s in scripts if "localStorage" in s]
        if not uses:
            add("G6a", "storage key", "FAIL", "course without a localStorage progress key")
        else:
            unsafe = []
            for s in uses:
                for m in re.finditer(r"localStorage\.(?:get|set)Item\(", s):
                    if not re.search(r"try\s*\{[^{}]*$", s[max(0, m.start() - 200):m.start()], re.S):
                        unsafe.append(s[m.start():m.start() + 30])
            key = (re.search(r"""["']key["']\s*:\s*["']([\w.-]+)""", allt)  # progress key from g-config first (the core theme toggle also has a KEY)
                   or re.search(r"""\bKEY\s*=\s*["']([\w.-]+)""", allt))
            add("G6a", "storage key", "FAIL" if unsafe else "PASS",
                ("localStorage access outside try/catch: " + "; ".join(unsafe[:3])) if unsafe else f"all localStorage access inside try/catch; key {(key and key.group(1)) or '(set in config)'}")
        for f, t in texts.items():
            mods = re.findall(r'<section\b[^>]*data-mod=["\'][^"\']+["\'][^>]*>(.*?)</section>', t, re.S)
            if mods:
                noq = [i + 1 for i, m in enumerate(mods) if "data-quiz" not in m]
                add("G6b", "quiz per module", "FAIL" if noq else "PASS", f"{len(mods)} modules; modules without quiz: {noq}" if noq else f"{len(mods)} modules, each with at least one quiz")
                break
        else:
            add("G6b", "quiz per module", "FAIL", "no module sections ([data-mod]) found")

    for n, c, s, m in rows:
        print(f"{n:<4} {c:<16} {s:<4} {m}")
    fail = any(s == "FAIL" for _, _, s, _ in rows) or core_rc == 1
    warn = any(s == "WARN" for _, _, s, _ in rows)
    print("RESULT:", "FAIL" if fail else ("WARN" if warn else "PASS"))
    sys.exit(1 if fail or (a.strict and warn) else 0)


if __name__ == "__main__":
    main()
