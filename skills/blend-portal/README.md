# blend-portal

Portal/hub skill built on `../blend-web-core`. Created 2026-11-10 from `informe-portal-demo.md` (Parts 1 and 3.2).
Local only, nothing published.

## RESOLVED (user decisions, 2026-11-10; see [../blend-web-core/README.md](../blend-web-core/README.md))

- Dark mode: stays optional. `--dark` adds `tokens-dark.css`, `portal-dark.css` and the core light/dark toggle (the portal body has no theme button of its own). None of the 9 canonical portals has dark mode, so `--dark` output has no reference to compare to.
- PP Telegraf: inherited from the core, embedded in base64 by default. License not independently verified; the user authorized bundling it.
- Logo: the one used by almost all shares (`blend-web-core/assets/logo.svg`). Portal note: the sidebar variant has the logo in the sticky header only, not in the sidebar.
- Status colors ok/warn/bad (`007676`, `B86A12`, `C8412B`): accepted as derived from the Design System (no official guide).

## PENDIENTE (still open, specific to this skill)

- Partner color tags (as in ai-native-program-hub) are not implemented; the user has not decided whether the canon wants them.

## Limits

- Manifest is JSON only (no YAML: stdlib). No `catalog.json` + `app.js` generator; the HTML is rendered at build time.
- `validate_portal.py` cannot call MCP. Slug existence needs a slug list file or a folder of downloaded shares; without
  one P2 is SKIP. `list_shares` returns only the user's own shares, so confirming other people's slugs means
  `check_path` one by one.
- P1 treats links to other hosts (SharePoint, Jira, intranet) as WARN, not FAIL; `.blend360.app` and plain http are FAIL.
- Sidebar variant frames only files of the same share; absolute share links open on their own page.
- Rendering was checked in Chrome through chrome-devtools at about 1700 px and, for 390 px, in 390 px iframes
  (the window could not be resized). Not tested: Safari/Firefox, print.
- Spark and ai-native-program-hub link to hosts outside share.blend360.com and fail or warn some checks: see the baseline.
