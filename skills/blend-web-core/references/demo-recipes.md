# Demo recipes

Demos, prototypes and apps do not get their own skill: the nine shares use three different systems. Build
them from `blend-web-core` plus one of these recipes. Always: logo in the header, "Illustrative" label on
mock data, works offline (CDNs only with exact versions), no real client data.

## A. Product mockup (Blenda family)

Uses the brand tokens and adds a product layer: type scale 40/28/20/16/14/12/11 px, radii 6 to 28 px and pill,
elevations, `--bg-raised` / `--bg-sunken` surfaces, a left rail with icons, search with Cmd+K, tabs, KPI tiles,
pills. Frames carry a number and a label. Refs: `blenda-ui-mocks`, `blenda-holdouts`. (`blenda-and-critical-7`
is a compiled game; document it as a special case, do not template it.)

## B. Guided demo (stepper, chat, simulation)

Stepper with Continue or Play/Step/Reset and an n/N counter; chat bubbles with tool-call rows; side log;
scenario tabs, each with a trigger and "what to watch for". Parameters:
- `product_theme`: default is the Blend brand. A client product theme (as in `smart-analyst-thinking-*`)
  must still declare `--blend-navy` and show the Blend logo.
- `client_logo`: co-branding in a navy topbar with a cyan hairline, "Blend x Client", logo with `alt`.
Refs: `smart-analyst-thinking-fast` (product theme, chat), `uascctdemo1` (agent orchestration, co-brand;
its Georgia/Courier fonts are a deviation, use the brand font).

## C. Scored assessment

Question cards, tiers, badges (`blocker`, `gate`, `flag` using the state tokens), a chart and export.
Chart.js 4.4.1 and xlsx 0.18.5 from cdnjs with the exact version in the URL. Ref: `crc-ml-underwriting-readiness-assessment`
(closest to the canon).

## Special cases (document only)

`blend-brb-screen` (full-screen break timer; consumes the Design System bundle: Montserrat + Space Mono),
`wrens-workshop` (animatic, off brand). Not templated.
