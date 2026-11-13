---
name: blend-portal
description: Builds Blend360-branded portals and hubs (self-contained HTML for Blend Share) that index other resources and shares, from a JSON manifest. Gives a sticky header with logo, navy hero, resource cards with type and status badges, search, filter chips, ARIA tabs, an expandable table and a footer, in three navigation variants (anchors, tabs, sidebar with iframe and #/slug routing). Includes validate_portal.py to check links, share slugs, tabs, logo weight and forbidden colors. Use when the user asks for a hub, portal, catalog, index or landing page that links to other Blend Shares or documents.
---

# blend-portal

Produces one `index.html` (CSS and JS inline, no libraries) from a manifest. It sits on top of
[blend-web-core](../blend-web-core/SKILL.md): tokens, components, logo and `blend_web.build()` are reused, not copied.

## Inputs to ask the user

Title, subtitle, groups (id, title, optional description, optional `"layout": "table"`), and for each item: title,
description, type, status, where it points (exactly one of `slug`, `url`, `file`), tags, owner, group. Also the
navigation variant. Defaults: tabs when there are 3 to 6 groups, anchors for one long page, sidebar when the items are
pages inside the same share.

## Manifest (JSON)

```json
{"title": "...", "subtitle": "...", "eyebrow": "...", "variant": "tabs|anchors|sidebar", "lang": "en",
 "illustrative": true, "footer": "...", "stats": [{"value": "12", "label": "resources"}],
 "groups": [{"id": "programs", "title": "Programs", "description": "...", "layout": "cards|table"}],
 "items": [{"title": "...", "description": "...", "type": "Portal", "status": "Live", "group": "programs",
            "slug": "other-share", "tags": ["a"], "owner": "...", "updated": "2026-11",
            "detail": "table rows only", "actions": [{"label": "Guide", "url": "https://share.blend360.com/x/"}]}]}
```

- `slug` becomes `https://share.blend360.com/<slug>/`. `url` must be absolute https; `*.blend360.app` is rejected
  by the builder. `file` is a relative path inside the share (sidebar variant opens it in the iframe; a `slug`/`url`
  item opens on its own page, since other shares may refuse framing).
- Status colors: live/ready/active -> ok, beta/draft/pilot/planned -> warn, deprecated/retired -> bad. Text is
  always shown, never color alone.
- `stats` is optional (default: resources, groups, live). `illustrative: true` adds the "Illustrative" banner.
- YAML is not supported (stdlib only). Convert to JSON.

## Flow

1. Gather inputs, write `manifest.json`. Real slugs only: confirm each with the blend-share MCP `check_path`
   (`available:false` = it exists) and save the confirmed slugs, one per line, to a file.
2. `python3 scripts/build_portal.py manifest.json out/index.html [--variant V] [--dark] [--no-check-files]`
3. `python3 scripts/validate_portal.py out/ --slugs-file slugs.txt` (or `--shares-dir <downloaded shares>`).
   Without a slug list, P2 is SKIP and the slugs to check are printed.
4. Look at it at 1280 and 390 px; fix the manifest, not the HTML.
5. Upload with the blend-share tools only if the user asks; this skill never publishes.

## Variants

| Variant | Structure | Reference |
|---|---|---|
| `anchors` | sticky sub-nav with scrollspy, numbered sections | spark |
| `tabs` | `role=tablist` with arrow keys, one panel per group, `#group` deep link | ai-native-program-hub |
| `sidebar` | sidebar + iframe, `#/id` deep link, mobile menu with scrim | latisphase1b (mechanics only: its palette is off-brand) |

Data in the page: all items are rendered as HTML by the builder (so validators and no-JS readers see them). For a
catalog that changes often, skill-marketplace shows the alternative: `catalog.json` + `app.js` rendered at load. The
builder does not generate that form; validate_portal.py does scan `.json` and `.js` files for links.

## Components (assets/portal.css, assets/portal.js)

`p-hero` (compact navy banner with the page's one eyebrow; summary counts as one quiet line), `p-tools` (search,
`p-fchip` filters, live count), `p-group` + `p-sec-head` (count, no numbering), `p-card` (the title is the link and
covers the card; + `p-badge` type, `b-chip` status, `p-tags`, `p-meta`, `p-actions` for secondary links), `p-table` with
`p-toggle`/`p-detail` rows, `p-subnav`, `p-tab`, `p-shell`/`p-side`/`p-stage`. Core classes used: `b-header`, `b-hero`,
`b-card`, `b-chip`, `b-btn`, `b-table`, `b-footer`. Only tokens, no hex in `portal.css`. Dark mode is optional (decided 2026-11-10): only with `--dark`, which adds the core light/dark toggle. PP Telegraf comes embedded from the core.

## Design checklist (before delivery)

A portal is an Operate page. Run the core [delivery checklist](../blend-web-core/references/delivery-checklist.md), then:

- [ ] The first screen shows the search or the first group, not only the hero; `stats` are omitted unless they help someone choose.
- [ ] Each item is opened by its title. No filled button per card; `actions` are verb-plus-object links ("Read the guide").
- [ ] Descriptions say what the reader gets in one or two lines of similar length; type and status are words, never colour alone.
- [ ] Groups with 7 or more items, or items people compare, use `"layout": "table"`; a group with one item joins another group.
- [ ] Filter to nothing: the empty message says how to get results back.
- [ ] Tabs, filters and row toggles work with the keyboard; with JavaScript off every item is still listed.

## Validation

`validate_portal.py` runs the core `validate.py --kind portal` (11 checks) and adds P1 links (share.blend360.com or
existing relative; `.blend360.app` and http FAIL, other hosts WARN), P2 slugs exist, P3 tabs ARIA, P4 logo present and
no base64 image over 100 KB, P5 no `#003059`/`#00ECEC`/`#0d5666`, P6 search labelled and iframes titled.
Baseline on the example and on spark and ai-native-program-hub: [references/validation-baseline.md](references/validation-baseline.md).

## Examples

- `examples/manifest.json` -> `examples/tabs/index.html`, `examples/anchors/index.html` (Illustrative data, real slugs).
- `examples/sidebar/` (manifest, `index.html`, two child pages).
- Canon to look at: `spark` (hero, anchors, tabs), `ai-native-program-hub` (cards, filters, search),
  `skill-marketplace` (catalog.json), `synthetic-personas-sales-portal` (items with actions).
