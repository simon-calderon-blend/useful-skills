#!/usr/bin/env python3
"""Validate a Blend portal/hub: runs blend-web-core validate.py --kind portal, then portal-specific checks.

Usage: validate_portal.py PATH [--slugs-file FILE | --shares-dir DIR] [--strict] [--dark {auto,required,off}]
PATH is an index.html or a folder with index.html. Output PASS/WARN/FAIL/SKIP per check; exit 1 on any FAIL
(or any WARN with --strict). Stdlib only.

P1 links       every link is share.blend360.com, or a relative path that exists. `.blend360.app` and plain http FAIL.
               Other external hosts WARN (real hubs link SharePoint/Jira; review them).
P2 slugs       every linked share slug exists. Needs a list: --slugs-file (one slug per line or a JSON list, e.g.
               saved from the blend-share MCP list_shares) or --shares-dir (a folder of downloaded shares, one
               sub-folder per slug). With neither: SKIP, and the slugs to check with check_path are printed.
P3 tabs        role=tablist/tab/tabpanel wiring (aria-selected, aria-controls <-> id, aria-labelledby, one tabbable tab).
P4 logo        core check 4 plus: no data:image base64 payload over 100 KB (FAIL).
P5 hex         #003059, #00ECEC, #0d5666 (and the core's forbidden list) must not appear.
P6 a11y        search input labelled, iframes titled, a single h1 on the home page.
"""
import argparse, base64, importlib.util, json, re, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse, unquote

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent / "blend-web-core" / "scripts" / "validate.py"
spec = importlib.util.spec_from_file_location("core_validate", CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)  # defines functions only; main() runs under __main__

PORTAL_FORBIDDEN = {"003059": "docx navy", "00ECEC": "off-token cyan", "0D5666": "latisphase1b accent, off-brand"}
IMG_LIMIT = 100 * 1024
SKIP_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com", "www.w3.org"}
rows = []


def add(n, name, status, msg):
    rows.append((n, name, status, msg))


def collect(p):
    if p.is_dir():
        files = [f for f in p.rglob("*") if f.is_file() and f.suffix in (".html", ".js", ".json", ".css")]
        index = p / "index.html"
    else:
        files, index = [p], p
    return files, index


def refs_in(text):
    """(attribute-ish links) from live code: href/src plus the data-href used by the sidebar router."""
    t = core.strip_data(text)
    return re.findall(r"""(?:href|src|data-href)\s*=\s*["']([^"']*)["']""", t, re.I), re.findall(r"""https?://[^\s"'<>)\\]+""", t)


def load_slugs(a):
    if a.slugs_file:
        raw = Path(a.slugs_file).read_text()
        try:
            data = json.loads(raw)
            data = data.get("shares", data) if isinstance(data, dict) else data
            return {(d["path"] if isinstance(d, dict) else d).strip("/") for d in data}
        except (json.JSONDecodeError, KeyError, TypeError):
            return {l.strip().strip("/") for l in raw.splitlines() if l.strip()}
    if a.shares_dir:
        return {d.name for d in Path(a.shares_dir).iterdir() if d.is_dir()}
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path"); ap.add_argument("--slugs-file"); ap.add_argument("--shares-dir")
    ap.add_argument("--strict", action="store_true"); ap.add_argument("--render", action="store_true"); ap.add_argument("--dark", default="auto", choices=["auto", "required", "off"])
    a = ap.parse_args()
    p = Path(a.path)
    if not p.exists():
        sys.exit(f"not found: {p}")
    files, index = collect(p)
    base = index.parent
    text = {f: f.read_text(errors="ignore") for f in files}
    html = text.get(index, "")

    # ---- core checks (subprocess) ----
    cmd = [sys.executable, str(CORE), str(p), "--kind", "portal", "--dark", a.dark] + (["--render"] if a.render else [])
    print("== blend-web-core validate.py --kind portal ==")
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.rstrip() or r.stderr.rstrip())
    core_fail = r.returncode != 0
    core_warn = " WARN " in r.stdout

    # ---- P1 links / P2 slugs ----
    bad_app, bad_http, external, missing, slugs = [], [], {}, [], set()
    for f, t in text.items():
        attrs, urls = refs_in(t)
        for u in set(urls):
            u = u.rstrip(".,;")
            h = urlparse(u)
            host = h.netloc
            if host in SKIP_HOSTS:
                continue
            if host.endswith(".blend360.app"):
                bad_app.append(u)
            elif u.startswith("http://"):
                bad_http.append(u)
            elif host == "share.blend360.com":
                seg = h.path.strip("/").split("/")[0]
                if seg and "." not in seg:  # "favicon.svg" etc. is a root asset, not a share
                    slugs.add(seg)
            else:
                external.setdefault(host, []).append(u)
        if f.suffix != ".html":
            continue
        for ref in attrs:
            if not ref or ref.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "http://", "https://", "//")):
                continue
            path = unquote(ref.split("#")[0].split("?")[0])
            if path in ("", ".", "./"):
                continue
            if not (f.parent / path).exists():
                missing.append(ref)
    if bad_app or bad_http or missing:
        msg = []
        if bad_app: msg.append("`.blend360.app` links (use https://share.blend360.com/<slug>/): " + ", ".join(sorted(set(bad_app))[:4]))
        if bad_http: msg.append("plain http: " + ", ".join(sorted(set(bad_http))[:3]))
        if missing: msg.append("relative links with no file: " + ", ".join(sorted(set(missing))[:5]))
        add("P1", "links", "FAIL", "; ".join(msg))
    elif external:
        add("P1", "links", "WARN", "links outside share.blend360.com (confirm they are intended): " +
            ", ".join(f"{h} x{len(set(v))}" for h, v in sorted(external.items())[:5]))
    else:
        add("P1", "links", "PASS", f"{len(slugs)} share slug(s) linked, all relative links resolve, no .blend360.app")

    known = load_slugs(a)
    own = base.name
    if not slugs:
        add("P2", "slugs", "PASS", "no links to other shares")
    elif known is None:
        add("P2", "slugs", "SKIP", "no --slugs-file/--shares-dir. Check these with blend-share check_path: " + ", ".join(sorted(slugs)))
    else:
        gone = sorted(s for s in slugs if s not in known and s != own)
        add("P2", "slugs", "FAIL" if gone else "PASS",
            ("slug(s) not found: " + ", ".join(gone)) if gone else f"all {len(slugs)} linked slug(s) exist in the list ({len(known)} known)")

    # ---- P3 tabs ----
    markup = re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S | re.I)
    tl = len(re.findall(r'role="tablist"', markup)); tabs = re.findall(r"<[^>]+role=\"tab\"[^>]*>", markup)
    panels = re.findall(r"<[^>]+role=\"tabpanel\"[^>]*>", markup)
    if not tl and not tabs and not panels:
        add("P3", "tabs", "PASS", "no tabs in this page (anchors/sidebar variant); nothing to check")
    else:
        probs = []
        ids = set(re.findall(r'\bid="([^"]+)"', markup))
        if not tl: probs.append("no role=tablist")
        for t in tabs:
            if "aria-selected" not in t: probs.append("tab without aria-selected")
            c = re.search(r'aria-controls="([^"]+)"', t)
            if not c or c[1] not in ids: probs.append(f"tab aria-controls -> missing id {c[1] if c else '(none)'}")
        for pn in panels:
            lb = re.search(r'aria-labelledby="([^"]+)"', pn)
            if not lb or lb[1] not in ids: probs.append("tabpanel without valid aria-labelledby")
        if len(tabs) != len(panels): probs.append(f"{len(tabs)} tabs vs {len(panels)} panels")
        sel = [t for t in tabs if 'aria-selected="true"' in t]
        js = "\n".join(t for f, t in text.items() if f.suffix in (".js", ".html"))
        if tl and not tabs: probs.append("role=tablist has no role=tab children")
        elif len(sel) > 1 or (not sel and not re.search(r"setAttribute\(\s*['\"]aria-selected", js)):
            probs.append(f"{len(sel)} tabs selected (need 1, or set by script)")
        keys = "ArrowRight" in js and "ArrowLeft" in js
        if probs:
            add("P3", "tabs", "FAIL", "; ".join(sorted(set(probs))[:4]))
        elif not keys:
            add("P3", "tabs", "WARN", f"{len(tabs)} tabs wired, but no ArrowLeft/ArrowRight keyboard handling found")
        else:
            add("P3", "tabs", "PASS", f"{len(tabs)} tabs/{len(panels)} panels: roles, aria-selected/controls/labelledby, arrow keys")

    # ---- P4 logo weight ----
    big, big_child = [], []
    for f, t in text.items():
        for m in re.finditer(r"data:image/[a-z+.-]+;base64,([A-Za-z0-9+/=]+)", t):
            size = len(m.group(1)) * 3 // 4
            if size > IMG_LIMIT:
                (big if f == index or f.suffix != ".html" else big_child).append(f"{f.name}: {size // 1024} KB")
    logo_ok = bool(re.search(r'viewBox="0 0 572 110"', "\n".join(text.values())))
    if big:
        add("P4", "logo/image", "FAIL", "base64 image over 100 KB (use the inline SVG logo, not a bitmap): " + ", ".join(big[:3]))
    elif not logo_ok:
        add("P4", "logo/image", "FAIL", "Blend logo SVG (viewBox 0 0 572 110) not present")
    elif big_child:
        add("P4", "logo/image", "WARN", "child pages embed base64 images over 100 KB (the hub itself is clean): " + ", ".join(sorted(set(big_child))[:3]))
    else:
        add("P4", "logo/image", "PASS", "logo present; no base64 image over 100 KB")

    # ---- P5 forbidden hex ----
    live = "\n".join(core.strip_data(t) for t in text.values())
    found = {core.hex6(h) for h in re.findall(r"#([0-9a-fA-F]{3,8})\b", live) if len(h) in (3, 6)}
    hit = {h: w for h, w in PORTAL_FORBIDDEN.items() if h in found}
    add("P5", "hex", "FAIL" if hit else "PASS",
        ("forbidden: " + ", ".join(f"#{h} ({w})" for h, w in hit.items())) if hit else "no #003059, #00ECEC or #0d5666")

    # ---- P6 a11y basics ----
    probs = []
    for m in re.finditer(r"<input\b[^>]*type=\"search\"[^>]*>", html):
        iid = re.search(r'\bid="([^"]+)"', m.group(0))
        labelled = "aria-label" in m.group(0) or (iid and re.search(r'for="%s"' % re.escape(iid[1]), html)) or re.search(r"<label\b[^>]*>(?:(?!</label>).)*" + re.escape(m.group(0)), html, re.S)
        if not labelled: probs.append("search input has no label")
    for m in re.finditer(r"<iframe\b[^>]*>", html):
        if "title=" not in m.group(0): probs.append("iframe without title")
    if len(re.findall(r"<h1[\s>]", html)) > 1: probs.append("more than one h1")
    add("P6", "a11y", "FAIL" if probs else "PASS", "; ".join(sorted(set(probs))) or "search labelled, iframes titled, one h1")

    print("\n== blend-portal checks ==")
    for n, c, s, m in rows:
        print(f"{n:>2} {c:<12} {s:<4} {m}")
    fail = core_fail or any(s == "FAIL" for _, _, s, _ in rows)
    warn = core_warn or any(s == "WARN" for _, _, s, _ in rows)
    verdict = "FAIL" if fail else ("WARN" if warn else "PASS")
    print(f"\nRESULT: {verdict}")
    sys.exit(1 if fail or (a.strict and warn) else 0)


if __name__ == "__main__":
    main()
