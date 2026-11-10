#!/usr/bin/env python3
"""Validate a Blend presentation: blend-web-core validate.py (--kind presentation) plus deck checks.

Usage: validate_presentation.py PATH [--strict] [--no-render] [--dark {auto,required,off}]
Extra checks (E1-E6): interaction (keydown/hashchange/touch/reduced-motion/@media print), unique hex <= 20,
no forbidden hex, no overflow per slide at 1280x720 (headless chromium; WARN if no browser), title/lang/aria,
slide counter. Exit 1 on any FAIL (or WARN with --strict). Stdlib only.
"""
import argparse, re, shutil, subprocess, sys, tempfile, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent / "blend-web-core" / "scripts" / "validate.py"
sys.path.insert(0, str(CORE.parent))
import validate as core  # noqa: E402  (FORBIDDEN, strip_data, hex6)

MAX_HEX = 20
PROBE = r"""<style>*,*::before,*::after{transition:none!important;animation:none!important}</style>
<script>window.addEventListener('load',function(){setTimeout(function(){
var res=[],ss=[].slice.call(document.querySelectorAll('.slide'));
ss.forEach(function(s,i){ss.forEach(function(o){o.classList.remove('active')});s.classList.add('active');
 var W=innerWidth,H=innerHeight,issue=[];
 if(s.scrollWidth>s.clientWidth+1)issue.push('scrollW '+s.scrollWidth+'>'+s.clientWidth);
 if(s.scrollHeight>s.clientHeight+1)issue.push('scrollH '+s.scrollHeight+'>'+s.clientHeight);
 [].slice.call(s.querySelectorAll('*')).some(function(el){var r=el.getBoundingClientRect();
  if(r.width>0&&r.height>0&&(r.right>W+2||r.bottom>H+2)&&getComputedStyle(el).position!=='fixed'){issue.push('<'+el.tagName.toLowerCase()+'.'+(el.className&&el.className.baseVal===undefined?el.className:'')+'> beyond viewport');return true}});
 if(issue.length)res.push((i+1)+': '+issue.join('; '))});
var p=document.createElement('pre');p.id='__probe';p.textContent=JSON.stringify({n:ss.length,issues:res});document.body.appendChild(p)},300)});</script>"""


def browser():
    for b in ("chromium", "google-chrome-stable", "google-chrome", "chrome"):
        if shutil.which(b):
            return shutil.which(b)


def overflow(index):
    b = browser()
    if not b:
        return "WARN", "no chromium/chrome found; check 1280x720 manually"
    with tempfile.TemporaryDirectory() as d:
        src = index.read_text(errors="ignore")
        src = src.replace("</body>", PROBE + "</body>", 1) if "</body>" in src else src + PROBE
        f = Path(d) / "probe.html"
        f.write_text(src)
        try:
            out = subprocess.run([b, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={d}/u",
                                  "--window-size=1280,720", "--virtual-time-budget=4000", "--dump-dom", f.as_uri()],
                                 capture_output=True, text=True, timeout=60).stdout
        except subprocess.TimeoutExpired:
            return "WARN", "browser timed out"
    m = re.search(r'<pre id="__probe">(.*?)</pre>', out, re.S)
    if not m:
        return "WARN", "probe did not run (page script error?)"
    import html as h
    data = json.loads(h.unescape(m[1]))
    if not data["n"]:
        return "FAIL", "no .slide elements found"
    if data["issues"]:
        return "FAIL", f"{len(data['issues'])}/{data['n']} slides overflow at 1280x720: " + " | ".join(data["issues"][:3])
    return "PASS", f"{data['n']} slides, none overflow at 1280x720"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--strict", action="store_true"); ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--dark", default="auto", choices=["auto", "required", "off"])
    a = ap.parse_args()
    p = Path(a.path)
    index = p / "index.html" if p.is_dir() else p

    core_cmd = [sys.executable, str(CORE), a.path, "--kind", "presentation", "--dark", a.dark] + (["--strict"] if a.strict else []) + ([] if a.no_render else ["--render"])
    cp = subprocess.run(core_cmd, capture_output=True, text=True)
    print("== blend-web-core validate.py --kind presentation ==")
    print(cp.stdout.rstrip())
    if cp.stderr.strip():
        print(cp.stderr.rstrip())

    raw = index.read_text(errors="ignore")
    t = core.strip_data(raw)
    rows = []

    miss = [k for k, pat in [("keydown", r"addEventListener\(\s*['\"]keydown|onkeydown"), ("ArrowLeft/ArrowRight", r"ArrowLeft[\s\S]*ArrowRight|ArrowRight[\s\S]*ArrowLeft"),
            ("Home/End", r"['\"]Home['\"][\s\S]*['\"]End['\"]|['\"]End['\"][\s\S]*['\"]Home['\"]"), ("hashchange", r"hashchange"),
            ("touch", r"touchstart[\s\S]*touchend|touchend[\s\S]*touchstart"), ("prefers-reduced-motion", r"prefers-reduced-motion"),
            ("@media print", r"@media\s+print")] if not re.search(pat, t)]
    rows.append(("E1", "interaction", "FAIL" if miss else "PASS", ("missing: " + ", ".join(miss)) if miss else "keydown(arrows,Home/End), hashchange, touch, reduced-motion, @media print present"))

    found = {core.hex6(h) for h in re.findall(r"#([0-9a-fA-F]{3,8})\b", t) if len(h) in (3, 6)}
    rows.append(("E2", "hex unique", "PASS" if len(found) <= MAX_HEX else "FAIL", f"{len(found)} unique hex (max {MAX_HEX})"))
    bad = sorted(h for h in found if h in core.FORBIDDEN)
    rows.append(("E3", "forbidden hex", "FAIL" if bad else "PASS", ", ".join(f"#{h}" for h in bad) or "none"))

    rows.append(("E4", "overflow", *(("WARN", "skipped (--no-render)") if a.no_render else overflow(index))))

    probs = []
    if not re.search(r"<html[^>]*\blang=", raw, re.I): probs.append("lang")
    if not re.search(r"<title>[^<]+</title>", raw, re.I): probs.append("title")
    nav = len(re.findall(r"aria-label=|aria-labelledby=|role=", t))
    if nav < 3: probs.append(f"few aria/role attributes ({nav})")
    if not re.search(r"aria-live", t): probs.append("no aria-live (counter)")
    rows.append(("E5", "title/lang/aria", "FAIL" if probs else "PASS", ", ".join(probs) or f"lang/title ok, {nav} aria/role attrs, aria-live present"))

    ns = len(re.findall(r'class="slide[\s"]', t))
    counter = bool(re.search(r"\d+\s*/\s*\d+|counter", t))
    rows.append(("E6", "slides/counter", "PASS" if ns >= 3 and counter else "WARN", f"{ns} .slide elements; n/N counter {'found' if counter else 'not found'}; notes {'yes' if re.search(r'notes', t, re.I) else 'no'}"))

    print("\n== presentation checks ==")
    for n, c, s, m in rows:
        print(f"{n:<3} {c:<15} {s:<4} {m}")
    fail = cp.returncode != 0 or any(s == "FAIL" for _, _, s, _ in rows)
    warn = any(s == "WARN" for _, _, s, _ in rows)
    verdict = "FAIL" if fail or (a.strict and warn) else "PASS"
    print(f"\nRESULT: {verdict}")
    sys.exit(1 if verdict == "FAIL" else 0)


if __name__ == "__main__":
    main()
