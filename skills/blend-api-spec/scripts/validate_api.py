#!/usr/bin/env python3
"""Validate a blend-api-spec folder (index.html + openapi.json|yaml + vendor/).

Usage: validate_api.py DIR [--dark {auto,required,off}] [--strict] [--no-render]
Runs blend-web-core validate.py (--kind api) on DIR/index.html, then the API-specific checks A1-A8.
Output PASS/WARN/FAIL/SKIP; exit 1 on any FAIL (or WARN with --strict). Stdlib only (PyYAML and
openapi-spec-validator are used when installed, otherwise the fallback is said out loud).

Note: core validate.py is pointed at index.html, not the folder, so the vendored swagger-ui.css (third party,
hundreds of off-palette hex) does not drown the palette check; vendor weight is reported by A8.
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE_VALIDATE = HERE.parent.parent / "blend-web-core" / "scripts" / "validate.py"
METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
FIXED_OPTS = {"deepLinking": r"deepLinking\s*:\s*true", "docExpansion": r"docExpansion\s*:\s*['\"]list['\"]",
              "supportedSubmitMethods": r"supportedSubmitMethods\s*:\s*\[\s*\]", "validatorUrl": r"validatorUrl\s*:\s*null"}
SECRETS = {"JWT": r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}", "AWS key": r"AKIA[0-9A-Z]{16}",
           "AWS ARN with account": r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:", "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
           "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}", "client_secret value": r"client_secret[\"']?\s*[:=]\s*[\"'][^\"'<>\s]{8,}",
           "Bearer token value": r"Bearer\s+(?!<)[A-Za-z0-9._~+/=-]{24,}", "Slack token": r"xox[abprs]-[A-Za-z0-9-]{10,}"}

rows = []
def add(n, name, st, msg=""): rows.append((n, name, st, msg))


def load_spec_file(p):
    t = p.read_text()
    if p.suffix.lower() == ".json":
        return json.loads(t), "json"
    try:
        import yaml
    except ImportError:
        return None, "yaml-no-pyyaml"
    return yaml.safe_load(t), "yaml"


def operations(spec):
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict): continue
        for m in METHODS:
            if m in item: yield path, m, item[m], item


def resolve(spec, ref):
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node: return None
        node = node[part]
    return node


def walk_refs(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str): out.append(v)
            else: walk_refs(v, out)
    elif isinstance(node, list):
        for v in node: walk_refs(v, out)


def has_example(node, spec, depth=0):
    """True if the media-type/schema node carries an example (directly or through a $ref)."""
    if depth > 6 or not isinstance(node, dict): return False
    if "$ref" in node:
        return has_example(resolve(spec, node["$ref"]) or {}, spec, depth + 1) if node["$ref"].startswith("#/") else False
    if "example" in node or "examples" in node: return True
    if "schema" in node and has_example(node["schema"], spec, depth + 1): return True
    if node.get("type") == "array" and has_example(node.get("items", {}), spec, depth + 1): return True
    props = node.get("properties")
    return bool(props) and all(has_example(v, spec, depth + 1) for v in props.values())


def check_spec(spec, label):
    """A1 structure/validity, A2 refs, A3 examples for one parsed spec."""
    if not isinstance(spec, dict):
        add("A1", f"spec {label}", "FAIL", "not an object"); return
    try:
        from openapi_spec_validator import validate  # type: ignore
        validate(spec)
        add("A1", f"spec {label}", "PASS", "openapi-spec-validator: valid")
    except ImportError:
        errs = []
        if not str(spec.get("openapi", "")).startswith(("3.0", "3.1")) and "swagger" not in spec: errs.append("openapi version missing/unsupported")
        info = spec.get("info") or {}
        for k in ("title", "version"):
            if not info.get(k): errs.append(f"info.{k}")
        if not spec.get("paths"): errs.append("paths empty")
        ids, ops = set(), 0
        for path, m, op, item in operations(spec):
            ops += 1
            if not op.get("responses"): errs.append(f"{m.upper()} {path}: no responses")
            if not op.get("summary"): errs.append(f"{m.upper()} {path}: no summary")
            oid = op.get("operationId")
            if not oid: errs.append(f"{m.upper()} {path}: no operationId")
            elif oid in ids: errs.append(f"duplicate operationId {oid}")
            ids.add(oid)
        add("A1", f"spec {label}", "FAIL" if errs else "WARN",
            ("; ".join(errs[:5])) if errs else f"{ops} operations; minimal structure only (openapi-spec-validator not installed, so full schema validation did NOT run)")
    except Exception as e:  # validator raised: the spec is invalid
        add("A1", f"spec {label}", "FAIL", f"openapi-spec-validator: {str(e)[:160]}")
    refs = []; walk_refs(spec, refs)
    bad = [r for r in refs if not r.startswith("#/") or resolve(spec, r) is None]
    add("A2", f"$refs {label}", "FAIL" if bad else "PASS", ("unresolved/external: " + ", ".join(sorted(set(bad))[:5])) if bad else f"{len(refs)} refs, all resolve locally")
    missing, total = [], 0
    for path, m, op, item in operations(spec):
        total += 1
        rb = (op.get("requestBody") or {})
        if "$ref" in rb: rb = resolve(spec, rb["$ref"]) or {}
        ok_req = (not rb) or any(has_example(c, spec) for c in (rb.get("content") or {}).values())
        resp_ok = False
        for code, r in (op.get("responses") or {}).items():
            if isinstance(r, dict) and "$ref" in r: r = resolve(spec, r["$ref"]) or {}
            if str(code).startswith("2") and any(has_example(c, spec) for c in ((r or {}).get("content") or {}).values()): resp_ok = True
            if str(code).startswith("2") and not (r or {}).get("content"): resp_ok = True  # 204 and friends: nothing to exemplify
        if not (ok_req and resp_ok): missing.append(f"{m.upper()} {path}")
    if total and len(missing) == total: add("A3", f"examples {label}", "FAIL", "no operation has request/response examples")
    elif missing: add("A3", f"examples {label}", "WARN", f"{len(missing)}/{total} operations lack an example: " + ", ".join(missing[:4]))
    else: add("A3", f"examples {label}", "PASS", f"all {total} operations have request and 2xx response examples")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir"); ap.add_argument("--dark", default="auto", choices=["auto", "required", "off"])
    ap.add_argument("--strict", action="store_true"); ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    d = Path(a.dir); index = d / "index.html"
    if not index.is_file(): sys.exit(f"no {index}")
    html = index.read_text(errors="ignore")

    # core
    cp = subprocess.run([sys.executable, str(CORE_VALIDATE), str(index), "--kind", "api", "--dark", a.dark] + ([] if a.no_render else ["--render"]), capture_output=True, text=True)
    print("== blend-web-core validate.py (--kind api) on index.html ==")
    print(cp.stdout.rstrip()); print(cp.stderr.rstrip() if cp.stderr.strip() else "", end="")
    core_fail = cp.returncode != 0
    core_warn = any(re.match(r"\s*\d+ \S+\s+WARN", l) for l in cp.stdout.splitlines())

    # specs: files in folder + inline
    spec_files = [p for p in sorted(d.glob("openapi*.json")) + sorted(d.glob("openapi*.y*ml"))]
    specs = []
    for p in spec_files:
        try:
            s, kind = load_spec_file(p)
        except Exception as e:
            add("A1", f"spec {p.name}", "FAIL", f"cannot parse: {str(e)[:120]}"); continue
        if kind == "yaml-no-pyyaml": add("A1", f"spec {p.name}", "WARN", "YAML not parsed (PyYAML missing); checks A1-A3 skipped for this file")
        else: specs.append((p.name, s))
    for m in re.finditer(r'<script type="application/json" id="spec">(.*?)</script>', html + (d / "propuesta.html").read_text(errors="ignore") if (d / "propuesta.html").exists() else html, re.S):
        try: json.loads(m.group(1))
        except Exception as e: add("A1", "inline spec", "FAIL", f"embedded JSON invalid: {str(e)[:100]}")
    if not spec_files and not re.search(r'id="spec"', html): add("A1", "spec", "FAIL", "no openapi.json/yaml and no inline #spec")
    for name, s in specs: check_spec(s, name)
    if re.search(r'id="spec"', html) and spec_files:
        try:
            inline = json.loads(re.search(r'<script type="application/json" id="spec">(.*?)</script>', html, re.S).group(1)) if "spec:" in html else None
            first = next((s for n, s in specs if n == "openapi.json"), None)
            if inline is not None and first is not None:
                add("A1", "inline == file", "PASS" if inline == first else "FAIL", "embedded spec equals openapi.json" if inline == first else "embedded spec differs from openapi.json")
        except Exception: pass

    # A4 secrets across html + specs
    blob = html + "".join(p.read_text(errors="ignore") for p in spec_files)
    hits = [k for k, v in SECRETS.items() if re.search(v, blob)]
    add("A4", "secrets", "FAIL" if hits else "PASS", ("found: " + ", ".join(hits)) if hits else "no JWT/AWS key/ARN/token patterns in html or spec (regex only; read the spec for real client data)")

    # A5 no floating CDN, local pinned vendor
    srcs = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', html)
    cdn = [u for u in srcs if re.match(r"https?://", u) and not re.match(r"https?://(fonts\.googleapis\.com|fonts\.gstatic\.com)", u)
           and not re.search(r"cdnjs\.cloudflare\.com/.*/\d+\.\d+\.\d+/", u)]
    swagger_local = bool(re.search(r'<script[^>]+src="vendor/swagger-ui-bundle\.js"', html) or re.search(r'<script[^>]+src="\./?[\w./-]*swagger-ui-bundle[\w.]*\.js"', html))
    if not swagger_local:  # compare shell: swagger lives in the iframes' pages
        swagger_local = all(re.search(r'src="vendor/swagger-ui-bundle\.js"', (d / n).read_text(errors="ignore")) for n in ("actual.html", "propuesta.html") if (d / n).exists()) and (d / "actual.html").exists()
    bundle = d / "vendor" / "swagger-ui-bundle.js"; vcss = d / "vendor" / "swagger-ui.css"; ver = (d / "vendor" / "VERSION")
    problems = []
    if cdn: problems.append("floating/unapproved external: " + ", ".join(cdn[:3]))
    if re.search(r"unpkg\.com|swagger-ui-dist@\d+(?!\.\d)|@latest", blob): problems.append("unpkg or unpinned swagger-ui-dist reference")
    if not swagger_local: problems.append("index does not reference vendor/swagger-ui-bundle.js")
    if not bundle.is_file() or not vcss.is_file(): problems.append("vendor bundle/css missing")
    vtxt = ver.read_text().strip() if ver.is_file() else ""
    if not re.fullmatch(r"5\.\d+\.\d+", vtxt): problems.append("vendor/VERSION is not an exact 5.x.y")
    elif bundle.is_file() and vtxt not in bundle.read_text(errors="ignore"): problems.append(f"bundle does not contain version string {vtxt}")
    add("A5", "pinned local swagger", "FAIL" if problems else "PASS", "; ".join(problems) if problems else f"swagger-ui-dist {vtxt} local, no unpkg/@5/@latest")

    # A6 fixed options
    pages = [index] + [d / n for n in ("actual.html", "propuesta.html") if (d / n).exists()]
    if re.search(r"SwaggerUIBundle", html) or len(pages) > 1:
        bad = []
        for pg in pages:
            t = pg.read_text(errors="ignore")
            if "SwaggerUIBundle(" not in t: continue
            bad += [f"{pg.name}:{k}" for k, rx in FIXED_OPTS.items() if not re.search(rx, t)]
        add("A6", "fixed options", "FAIL" if bad else "PASS", ("missing/changed: " + ", ".join(bad)) if bad else "deepLinking:true, docExpansion:'list', supportedSubmitMethods:[], validatorUrl:null")
    else:
        add("A6", "fixed options", "FAIL", "no SwaggerUIBundle(...) call in index.html")

    # A7 theme: .info .title color by CSS, and rendered via headless chromium when available
    css = re.sub(r"/\*.*?\*/", "", "\n".join(re.findall(r"<style>(.*?)</style>", html + "".join(p.read_text(errors="ignore") for p in pages[1:2]), re.S)), flags=re.S)
    theme_ok = False
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if re.search(r"\.swagger-ui\s+\.info\s+\.title\s*(,|$)", m.group(1).strip().split("\n")[-1].strip()) or re.search(r"\.swagger-ui \.info \.title\s*$", m.group(1).strip()):
            c = re.search(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{6})", m.group(2))
            if c and c.group(1).upper() == "#053057": theme_ok = True
    page_for_render = index if "SwaggerUIBundle(" in html else (d / "actual.html")
    chrome = None if a.no_render else (shutil.which("chromium") or shutil.which("google-chrome-stable") or shutil.which("google-chrome"))
    rendered = None
    if chrome and page_for_render.exists():
        probe = ("<script>addEventListener('load',function(){setTimeout(function(){var t=document.querySelector('.swagger-ui .info .title');"
                 "var n=document.querySelectorAll('.opblock').length;document.title='PROBE|'+(t?getComputedStyle(t).color:'none')+'|'+n+'|'+(window.__errs||[]).length+'|'+(document.documentElement.scrollWidth-document.documentElement.clientWidth);},800)});"
                 "window.__errs=[];addEventListener('error',function(e){window.__errs.push(e.message)});</script>")
        # injected before the other scripts so window.onerror sees their failures
        txt = page_for_render.read_text(errors="ignore").replace("<body", "<head-probe></head-probe><body", 1)
        txt = txt.replace("<head-probe></head-probe>", probe)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td); shutil.copytree(d, tmp / "site"); (tmp / "site" / "__probe.html").write_text(txt)
            try:
                out = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", f"--user-data-dir={tmp/'prof'}",
                                      "--virtual-time-budget=6000", "--window-size=1280,900", "--dump-dom", (tmp / "site" / "__probe.html").as_uri()],
                                     capture_output=True, text=True, timeout=90).stdout
                m = re.search(r"<title>PROBE\|([^|]*)\|(\d+)\|(\d+)\|(-?\d+)</title>", out)
                if m: rendered = (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            except Exception as e:
                rendered = None
    if rendered:
        color, nops, nerr, ovf = rendered
        add("A7", ".info .title color", "PASS" if color == "rgb(5, 48, 87)" else "FAIL", f"computed {color} (expected rgb(5, 48, 87)); css rule {'ok' if theme_ok else 'NOT found'}")
        add("A8", "render", "FAIL" if (nops < 1 or nerr or ovf > 1) else "PASS", f"{nops} operation blocks, {nerr} uncaught script errors, horizontal overflow {ovf}px (headless chromium, 1280 px)")
    else:
        why = "disabled" if a.no_render else ("no chromium found" if not chrome else "probe returned nothing")
        add("A7", ".info .title color", "PASS" if theme_ok else "FAIL", f"by CSS only ({why}): rule `.swagger-ui .info .title` color #053057 {'found' if theme_ok else 'NOT found'}; render not checked")
        add("A8", "render", "SKIP", f"{why}; look at the page in a browser and check the console")
    # weight of the whole publishable folder
    kb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1024
    add("A9", "folder weight", "FAIL" if kb > 5120 else ("WARN" if kb > 3072 else "PASS"), f"{kb:.0f} KB total including vendor (warn >3072, fail >5120)")

    print("\n== blend-api-spec checks ==")
    for n, c, s, m in rows: print(f"{n:<3} {c:<24} {s:<5} {m}")
    fail = core_fail or any(s == "FAIL" for _, _, s, _ in rows)
    warn = core_warn or any(s == "WARN" for _, _, s, _ in rows)
    print("\nRESULT:", "FAIL" if fail else ("WARN" if warn else "PASS"))
    sys.exit(1 if fail or (a.strict and warn) else 0)


if __name__ == "__main__":
    main()
