# Validation baseline

validate_dashboard.py run on 2026-11-10 after the core change that embeds PP Telegraf by default (core check 9 SKIP: no Playwright). Canon output left as is; nothing loosened. Both canonical shares predate this skill: neither has `data-kpi` tiles, so D1/D2 are WARN, not PASS. `blend-events` keeps its data under `DATA.events`, which D2 does not read.

```
$ python3 scripts/validate_dashboard.py examples/illustrative-dashboard.html
validate: examples/illustrative-dashboard.html  kind=dashboard
 1 palette      PASS 16 brand hex, 6 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    PASS lang/title/viewport/description/h1 ok
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS both blocks present
 8 weight       PASS 106 KB (limit 2048 KB for 'dashboard', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
D1 data         PASS DATA parses; 95 rows
D2 kpis         PASS 5 KPI(s) match the embedded data
D3 pii          PASS no PII column names or patterns (regex only; still review the content)
D4 scripts      PASS no external scripts
D5 charts       PASS rules ok
RESULT PASS
exit=0
```

```
$ python3 scripts/validate_dashboard.py /home/simoncl20/Work/blend/bld/blend-share-files/blend-events/index.html
validate: /home/simoncl20/Work/blend/bld/blend-share-files/blend-events/index.html  kind=dashboard
 1 palette      PASS 7 brand hex, 0 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         PASS logo SVG (572x110) present
 5 contrast     PASS token pairs >= 4.5:1; no cyan text on light detected (heuristic)
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 191 KB (limit 2048 KB for 'dashboard', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
D1 data         PASS DATA parses; no rows
D2 kpis         WARN no tiles with data-kpi: KPIs cannot be checked against the data
D3 pii          PASS no PII column names or patterns (regex only; still review the content)
D4 scripts      PASS no external scripts
D5 charts       PASS no charts (table/KPI page)
RESULT WARN
exit=0
```

```
$ python3 scripts/validate_dashboard.py /home/simoncl20/Work/blend/bld/blend-share-files/hackathon-anthropic-api-usage-tracker/index.html
validate: /home/simoncl20/Work/blend/bld/blend-share-files/hackathon-anthropic-api-usage-tracker/index.html  kind=dashboard
 1 palette      PASS 5 brand hex, 6 derived/off-palette
 2 font         PASS PP Telegraf embedded (base64)
 3 structure    WARN meta description missing (none of the canonical shares has one)
 4 logo         PASS logo SVG (572x110) present
 5 contrast     WARN cyan/turquoise as text where the rule has no dark background (verify): .sub; .sub b; .updated b; .tile .label
 6 resources    PASS 0 external urls, all allowed/pinned; local refs resolve
 7 dark         PASS no dark (optional by decision; use --dark to build with it)
 8 weight       PASS 82 KB (limit 2048 KB for 'dashboard', error over 5120 KB)
 9 render       SKIP run with --render (needs playwright) or check 1280/390 px manually
10 secrets/PII  PASS no secrets, tokens, ARNs or e-mails detected (regex only; review content for client data)
D1 data         WARN no `const DATA` (static page or data loaded elsewhere): D2 cannot verify KPIs
D2 kpis         WARN skipped: no embedded data
D3 pii          PASS no PII column names or patterns (regex only; still review the content)
D4 scripts      PASS no external scripts
D5 charts       PASS no charts (table/KPI page)
RESULT WARN
exit=0
```

```
--- negative test: tampered KPI + unpinned unpkg script
D1 data         PASS DATA parses; 95 rows
D2 kpis         FAIL orders: shown '20,999', data gives 20,300
D3 pii          PASS no PII column names or patterns (regex only; still review the content)
D4 scripts      FAIL script src not on cdnjs with exact version: https://unpkg.com/chart.js@4
D5 charts       PASS rules ok
RESULT FAIL
exit=1
```

## Design pass 2026-11-13

The runs above predate the design pass and show 10 core checks. The core validator now has check 11 "craft"
(warnings only) and the examples were regenerated. Results on the regenerated examples:

| Target | Exit | FAIL | WARN | Warnings |
|---|---|---|---|---|
| `illustrative-dashboard.html` | 0 | 0 | 0 | none |

The canonical shares were not re-run; expect check 11 to warn on them (side stripes, uppercase labels, text under 12px).
