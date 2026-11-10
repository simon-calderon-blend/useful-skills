#!/usr/bin/env python3
"""Build a Blend portal/hub (self-contained index.html) from a JSON manifest.

Usage: build_portal.py MANIFEST.json OUT.html [--variant anchors|tabs|sidebar] [--dark] [--no-check-files]
The manifest's "variant" is used unless --variant overrides it. Stdlib only. Reuses blend-web-core
(tokens.css, components.css, logo.svg, blend_web.build). See ../SKILL.md for the manifest schema.

Links: an item has exactly one of "slug" (-> https://share.blend360.com/<slug>/), "url" (absolute, https)
or "file" (relative path inside this share). `.blend360.app` URLs are rejected. Everything is escaped.
"""
import argparse, html, json, re, sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL.parent / "blend-web-core" / "scripts"))
import blend_web  # noqa: E402

SHARE = "https://share.blend360.com/"
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OK = {"live", "ready", "active", "published", "available"}
WARN = {"beta", "draft", "wip", "pilot", "in progress", "preview", "planned"}
BAD = {"deprecated", "retired", "blocked", "archived"}
E = html.escape


def chip_class(status):
    s = status.lower()
    return "ok" if s in OK else "warn" if s in WARN else "bad" if s in BAD else ""


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "item"


class Problems(Exception):
    pass


def load(path, check_files):
    m = json.loads(Path(path).read_text())
    errs, warns = [], []
    for k in ("title", "items"):
        if not m.get(k):
            errs.append(f"manifest: '{k}' is required")
    groups = m.get("groups") or [{"id": "resources", "title": "Resources"}]
    gids = [g["id"] for g in groups]
    if len(set(gids)) != len(gids):
        errs.append("manifest: duplicate group ids")
    seen, base = set(), Path(path).resolve().parent
    for i, it in enumerate(m.get("items", [])):
        n = it.get("title") or f"#{i}"
        if not it.get("title"):
            errs.append(f"item #{i}: title is required")
        keys = [k for k in ("slug", "url", "file") if it.get(k)]
        if len(keys) != 1:
            errs.append(f"item '{n}': give exactly one of slug/url/file (got {keys or 'none'})")
            continue
        it["id"] = it.get("id") or slugify(it.get("title", ""))
        if it["id"] in seen:
            errs.append(f"item '{n}': duplicate id '{it['id']}'")
        seen.add(it["id"])
        it["group"] = it.get("group") or gids[0]
        if it["group"] not in gids:
            errs.append(f"item '{n}': unknown group '{it['group']}'")
        if "slug" in it:
            if not SLUG_RE.match(it["slug"]):
                errs.append(f"item '{n}': invalid slug '{it['slug']}'")
            it["href"] = f"{SHARE}{it['slug']}/"
        elif "url" in it:
            u = urlparse(it["url"])
            if u.scheme != "https" or not u.netloc:
                errs.append(f"item '{n}': url must be absolute https ({it['url']})")
            elif u.netloc.endswith(".blend360.app"):
                errs.append(f"item '{n}': .blend360.app is rejected, use {SHARE}<slug>/ ({it['url']})")
            elif u.netloc != "share.blend360.com":
                warns.append(f"item '{n}': external host {u.netloc} (not a Blend share)")
            it["href"] = it["url"]
        else:
            f = it["file"]
            if f.startswith(("/", "http")) or ".." in Path(f).parts:
                errs.append(f"item '{n}': file must be a relative path inside the share ({f})")
            elif check_files and not (base / f).exists():
                warns.append(f"item '{n}': file '{f}' not found next to the manifest")
            it["href"] = f
        for a in it.get("actions", []):
            if not str(a.get("url", "")).startswith(("https://", "./", "#")) and not re.match(r"^[\w./-]+$", str(a.get("url", ""))):
                errs.append(f"item '{n}': bad action url {a.get('url')}")
            if urlparse(a.get("url", "")).netloc.endswith(".blend360.app"):
                errs.append(f"item '{n}': .blend360.app action url rejected")
    if errs:
        raise Problems("\n".join(errs))
    m["groups"] = groups
    return m, warns


def search_text(it):
    parts = [it["title"], it.get("description", ""), it.get("type", ""), it.get("status", ""), it.get("owner", ""), " ".join(it.get("tags", []))]
    return E(" ".join(parts).lower(), quote=True)


def attrs(it):
    return (f'data-item data-type="{E(it.get("type", "").lower(), quote=True)}" '
            f'data-status="{E(it.get("status", "").lower(), quote=True)}" data-search="{search_text(it)}"')


def status_chip(it):
    return f'<span class="b-chip {chip_class(it["status"])}">{E(it["status"])}</span>' if it.get("status") else ""


def actions(it, embed=False):
    label = f' aria-label="Open {E(it["title"], quote=True)}"'
    if embed:
        out = [f'<a class="b-btn p-btn" href="#/{E(it["id"], quote=True)}"{label}>Open here</a>',
               f'<a class="b-btn p-btn ghost" href="{E(it["href"], quote=True)}" target="_blank" rel="noopener" aria-label="Open {E(it["title"], quote=True)} in a new tab">New tab</a>']
    else:
        out = [f'<a class="b-btn p-btn" href="{E(it["href"], quote=True)}"{label}>Open</a>']
    for a in it.get("actions", []):
        out.append(f'<a class="b-btn p-btn ghost" href="{E(a["url"], quote=True)}">{E(a["label"])}</a>')
    return '<div class="p-actions">' + "".join(out) + "</div>"


def meta(it):
    bits = []
    if it.get("owner"): bits.append(f"<span>Owner: {E(it['owner'])}</span>")
    if it.get("updated"): bits.append(f"<span>Updated: {E(it['updated'])}</span>")
    return '<p class="p-meta">' + "".join(bits) + "</p>" if bits else ""


def card(it, embed=False):
    tags = '<ul class="p-tags" aria-label="Tags">' + "".join(f"<li>{E(t)}</li>" for t in it.get("tags", [])) + "</ul>" if it.get("tags") else ""
    badge = f'<span class="p-badge">{E(it["type"])}</span>' if it.get("type") else "<span></span>"
    return (f'<article class="b-card p-card" {attrs(it)} data-counted>'
            f'<div class="p-card-top">{badge}{status_chip(it)}</div>'
            f'<h3 class="p-card-title">{E(it["title"])}</h3>'
            f'<p class="p-card-desc">{E(it.get("description", ""))}</p>{tags}{meta(it)}{actions(it, embed)}</article>')


def table(g, items, embed=False):
    rows = []
    for it in items:
        d = f'd-{it["id"]}'
        detail = it.get("detail") or it.get("description", "")
        tags = " ".join(f"<li>{E(t)}</li>" for t in it.get("tags", []))
        tags = f'<ul class="p-tags">{tags}</ul>' if tags else ""
        rows.append(
            f'<tbody class="p-row" {attrs(it)} data-counted>'
            f'<tr class="p-r1"><td data-label="Resource"><strong class="p-t-title">{E(it["title"])}</strong>'
            f'<span class="p-t-desc">{E(it.get("description", ""))}</span></td>'
            f'<td data-label="Type">{E(it.get("type", ""))}</td><td data-label="Status">{status_chip(it)}</td>'
            f'<td data-label="Owner">{E(it.get("owner", ""))}</td>'
            f'<td class="p-togcell"><button type="button" class="p-toggle" aria-expanded="false" aria-controls="{E(d, quote=True)}">Details<span class="p-sr"> for {E(it["title"])}</span></button></td></tr>'
            f'<tr class="p-detail" id="{E(d, quote=True)}" hidden><td colspan="5"><div class="p-detail-in">'
            f'<p>{E(detail)}</p>{tags}{meta(it)}{actions(it, embed)}</div></td></tr></tbody>')
    return ('<div class="b-table-wrap"><table class="b-table p-table">'
            f'<caption class="p-sr">{E(g["title"])}</caption>'
            '<thead><tr><th scope="col">Resource</th><th scope="col">Type</th><th scope="col">Status</th><th scope="col">Owner</th>'
            '<th scope="col"><span class="p-sr">Details</span></th></tr></thead>' + "".join(rows) + "</table></div>")


def group_body(g, items, embed=False):
    if g.get("layout") == "table":
        return table(g, items, embed)
    return '<div class="p-grid">' + "".join(card(i, embed) for i in items) + "</div>"


def section(n, g, items, embed=False, extra="", hidden=False):
    gid = E(g["id"], quote=True)
    desc = f'<p class="p-gdesc">{E(g["description"])}</p>' if g.get("description") else ""
    head = (f'<header class="p-sec-head"><span class="p-num">{n:02d}</span><h2 id="h-{gid}">{E(g["title"])}</h2>'
            f'<span class="p-count"><span data-count>{len(items)}</span> listed</span></header>')
    return (f'<section class="p-group" id="g-{gid}" data-group="{gid}" aria-labelledby="h-{gid}"{extra}{" hidden" if hidden else ""}>'
            f'{head}{desc}{group_body(g, items, embed)}<p class="p-none" hidden>No resources match the current search or filters.</p></section>')


def hero(m, items):
    stats = m.get("stats")
    if stats is None:
        stats = [{"value": len(items), "label": "resources"}, {"value": len(m["groups"]), "label": "groups"}]
        live = sum(1 for i in items if chip_class(i.get("status", "")) == "ok")
        if live: stats.append({"value": live, "label": "live"})
    st = "".join(f'<li><span class="v">{E(str(s["value"]))}</span><span class="l">{E(s["label"])}</span></li>' for s in stats)
    ill = '<p class="p-sub" style="margin-top:1rem"><strong>Illustrative.</strong> Sample content generated by blend-portal; not a real catalog.</p>' if m.get("illustrative") else ""
    return (f'<section class="b-hero p-hero"><div class="p-wrap"><div class="b-eyebrow">{E(m.get("eyebrow", "Blend360"))}</div>'
            f'<h1>{E(m["title"])}</h1>' + (f'<p class="p-sub">{E(m["subtitle"])}</p>' if m.get("subtitle") else "") +
            f'{ill}<ul class="p-stats" aria-label="Portal summary">{st}</ul></div></section>')


def toolbar(items):
    types = sorted({i["type"] for i in items if i.get("type")}, key=str.lower)
    stat = sorted({i["status"] for i in items if i.get("status")}, key=str.lower)

    def chips(kind, vals, label):
        if not vals: return ""
        c = "".join(f'<button type="button" class="b-chip p-fchip" data-filter="{kind}" data-value="{E(v.lower(), quote=True)}" aria-pressed="false">{E(v)}</button>' for v in vals)
        return f'<div class="p-filters" role="group" aria-label="Filter by {label}"><span class="p-flabel">{label}</span>{c}</div>'
    return ('<div class="p-tools"><label class="p-search"><span class="p-sr">Search resources</span>'
            '<input id="p-q" type="search" placeholder="Search title, description, tag or owner" autocomplete="off"></label>'
            f'{chips("type", types, "Type")}{chips("status", stat, "Status")}'
            '<p class="p-status"><span id="p-status" aria-live="polite"></span> <button type="button" class="p-clear" id="p-clear" hidden>Clear filters</button></p></div>')


def footer(m):
    t = m.get("footer") or f"{m['title']} | Blend360"
    return f'<footer class="b-footer">{E(t)}</footer>'


def by_group(m):
    out = []
    for g in m["groups"]:
        out.append((g, [i for i in m["items"] if i["group"] == g["id"]]))
    return out


def render(m, variant, dark=False):
    items = m["items"]; groups = by_group(m); title = E(m["title"], quote=True)
    if variant == "sidebar":
        return render_sidebar(m, groups, title)
    tools = toolbar(items)
    if variant == "anchors":
        nav = "".join(f'<a href="#g-{E(g["id"], quote=True)}" data-navfor="{E(g["id"], quote=True)}">{E(g["title"])}<span class="p-n" data-tabcount="{E(g["id"], quote=True)}">{len(its)}</span></a>'
                      for g, its in groups)
        body = (f'<main data-portal data-variant="anchors" data-title="{title}">{hero(m, items)}'
                f'<nav class="p-subnav" aria-label="Sections"><div class="p-wrap">{nav}</div></nav>'
                f'<div class="p-wrap">{tools}{"".join(section(n, g, its) for n, (g, its) in enumerate(groups, 1))}</div></main>{footer(m)}')
    else:  # tabs
        tabs, panels = [], []
        for n, (g, its) in enumerate(groups, 1):
            gid = E(g["id"], quote=True); first = n == 1
            tabs.append(f'<button type="button" role="tab" class="p-tab" id="tab-{gid}" data-gid="{gid}" aria-controls="panel-{gid}" '
                        f'aria-selected="{"true" if first else "false"}" tabindex="{0 if first else -1}">{E(g["title"])}'
                        f'<span class="p-n" data-tabcount="{gid}">{len(its)}</span></button>')
            panels.append(f'<div role="tabpanel" class="p-panel" id="panel-{gid}" aria-labelledby="tab-{gid}" tabindex="0"{"" if first else " hidden"}>'
                          f'{section(n, g, its)}</div>')
        body = (f'<main data-portal data-variant="tabs" data-title="{title}">{hero(m, items)}<div class="p-wrap">{tools}</div>'
                f'<div class="p-tabs-bar"><div class="p-wrap"><div role="tablist" aria-label="Groups">{"".join(tabs)}</div></div></div>'
                f'<div class="p-wrap">{"".join(panels)}</div></main>{footer(m)}'
                '<noscript><style>[role="tabpanel"][hidden]{display:block !important}</style></noscript>')
    return body


def render_sidebar(m, groups, title):
    items = m["items"]
    nav, n = [], 0
    for g, its in groups:
        nav.append(f'<p class="p-navgroup">{E(g["title"])}</p>')
        for it in its:
            n += 1
            embed = "file" in it
            nav.append(f'<a class="p-nav" href="#/{E(it["id"], quote=True)}" data-id="{E(it["id"], quote=True)}" data-title="{E(it["title"], quote=True)}" '
                       f'data-href="{E(it["href"], quote=True)}" data-embed="{1 if embed else 0}" {attrs(it)}><span class="p-num">{n:02d}</span><span>{E(it["title"])}</span></a>')
    secs = "".join(section(k, g, its, embed=True) for k, (g, its) in enumerate(groups, 1))
    return (f'<div data-portal data-variant="sidebar" data-title="{title}" class="p-shell">'
            f'<aside class="p-side" id="p-side" aria-label="Resources"><h2>{E(m["title"])}</h2><nav aria-label="Resources">{"".join(nav)}</nav></aside>'
            '<div class="p-scrim" id="p-scrim"></div>'
            '<div class="p-main"><div class="p-topbar"><button type="button" class="p-menu" id="p-menu" aria-controls="p-side" aria-expanded="false">Menu</button>'
            '<div class="p-crumb" id="p-crumb">Overview</div>'
            '<a class="b-btn p-btn ghost" id="p-newtab" href="#" target="_blank" rel="noopener" hidden>Open in new tab</a></div>'
            f'<div class="p-stage"><main class="p-home" id="p-home">{hero(m, items)}<div class="p-wrap">{toolbar(items)}{secs}</div>{footer(m)}</main>'
            '<iframe id="p-frame" title="Resource viewer" hidden></iframe>'
            '<div class="p-linkout" id="p-linkout" hidden><h2 id="p-outtitle"></h2><p>This resource is a separate share and is opened on its own page.</p>'
            '<a class="b-btn p-btn" id="p-outlink" href="#">Open</a></div></div></div></div>')


def build(manifest_path, out, variant=None, dark=False, check_files=True):
    m, warns = load(manifest_path, check_files)
    variant = variant or m.get("variant", "tabs")
    if variant not in ("anchors", "tabs", "sidebar"):
        raise Problems(f"unknown variant '{variant}'")
    body = render(m, variant, dark)
    css = (SKILL / "assets" / "portal.css").read_text()
    if dark:
        css += (SKILL / "assets" / "portal-dark.css").read_text()
    js = (SKILL / "assets" / "portal.js").read_text()
    page = blend_web.build(body + f"\n<script>\n{js}\n</script>", m["title"], m.get("lang", "en"),
                           m.get("description") or m.get("subtitle", ""), dark, css)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(page)
    return variant, warns


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest"); ap.add_argument("out")
    ap.add_argument("--variant", choices=["anchors", "tabs", "sidebar"])
    ap.add_argument("--dark", action="store_true"); ap.add_argument("--no-check-files", action="store_true")
    a = ap.parse_args()
    try:
        v, w = build(a.manifest, a.out, a.variant, a.dark, not a.no_check_files)
    except Problems as e:
        print("build_portal: manifest errors\n" + str(e), file=sys.stderr); sys.exit(1)
    except (OSError, json.JSONDecodeError) as e:
        print(f"build_portal: {e}", file=sys.stderr); sys.exit(1)
    for x in w:
        print("WARN", x)
    print(f"wrote {a.out} (variant={v})")
