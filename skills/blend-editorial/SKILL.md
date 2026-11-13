---
name: blend-editorial
description: Builds Blend360 editorial and commercial web pages as self-contained HTML (Blend Share): articles, essays, whitepapers, eBooks and briefings (kind=article), and one-pagers, landing pages, case studies, proposals and deliverable previews with optional client co-branding (kind=commercial). Ships a JSON-driven generator, editorial CSS on top of blend-web-core, and validate_editorial.py. Use when the user asks for a Blend article, blog post, whitepaper, one-pager, landing page, case study or commercial leave-behind, or to check such a page.
---

# blend-editorial

Two kinds on the shared base `../blend-web-core` (tokens, components, logo, `blend_web.build`, `validate.py`). Nothing is copied from the core.

## Inputs to ask the user

- **article**: title, dek, sections (text, figures, pull quotes), author/date, closing CTA (optional).
- **commercial**: thesis/offer (h1 in one sentence), audience, 3-6 blocks (KPIs, cards, engagement steps), CTA (label + href, required), contact.
- **client** (co-branding): name, whether a logo may be used (permission), confidentiality. No permission means text only. Never commit a real client logo to the repo: use `assets/client-logo-placeholder.svg`.
- Sub-type for commercial: `one-pager` (Letter, `@page`, N pages) or `landing`. Case study, proposal and deliverables preview use the landing build with sections/steps/KPIs.

## Workflow

1. Write a JSON spec (see `examples/*-spec.json`; block types in the docstring of `scripts/build_editorial.py`).
2. `python3 scripts/build_editorial.py spec.json out/index.html [--dark]`
3. `python3 scripts/validate_editorial.py out/index.html --kind article|one-pager|landing [--client] [--pages N]`
4. Look at it at 1280, 390 and 375 px; for a one-pager, print to PDF and count pages.

## What it produces

- article (Read page): sticky topbar with section nav, navy hero (the page's one eyebrow in cyan, white h1, soft-cyan dek), sections separated by space with self-announcing h2s (no numbers, no per-section labels), prose at 48ch (about 72 characters in PP Telegraf) / 17px / 1.7, pull quote under a short cyan rule, tinted callout, figure + caption (inline SVG), table, closing band, footer.
- commercial (Persuade page): same shell plus one hero CTA (cyan button, navy text) repeated in the closing band with the same words, and three block builds that never share a skeleton: `cards` as open columns under a navy rule, `kpis` as a figure row parted by hairlines (`[value, label, qualifier]`), `steps` as numbered rows. "Illustrative" pill in the hero meta, footer with `Confidential`. One-pager adds `.e-sheet` blocks (8.5x11 in, `break-after: page`) and `@page`.
- co-branding: topbar `Blend logo | x | client` (client text in mono caps, or an `<img>` with alt, white tile, never recolored); footer carries `Confidential` when set.

## Tokens and components

Core: `--blend-*` tokens, `.b-kpis/.b-kpi`, `.b-card`, `.b-callout`, `.b-table`, `.blend-logo`. Own (`assets/editorial.css`, `assets/onepager.css`): `.e-topbar`, `.e-cobrand`, `.e-hero`, `.e-prose`, `.e-quote`, `.e-figure`, `.e-cards`, `.e-steps`, `.e-pill`, `.e-cta`, `.e-footer`, `.e-sheet`. Cyan is only text on navy. Topbar, hero, sections and footer share one left line (`--e-pad`).

## Design checklist (before delivery)

Run the core [delivery checklist](../blend-web-core/references/delivery-checklist.md), then:

- [ ] The h1 is the promise or thesis in one sentence, 3 lines at most at 390 px; the dek adds a fact, it does not restate the title.
- [ ] Section `label`s are one word (they are the nav); headings say what the reader gets.
- [ ] Commercial: one action, worded the same in the hero and the closing band; nothing else is a filled button.
- [ ] Commercial: no two neighbouring sections use the same block (cards, kpis, steps); `steps` only for a real sequence.
- [ ] Every KPI has a qualifier (third item); `cards` text is one or two sentences of similar length.
- [ ] Article: one pull quote at most per section; figures carry a caption that states the point.
- [ ] One-pager: print to PDF and count pages; nothing is clipped at the sheet edge.

## Size limits

article 2 MB, one-pager 500 KB, landing 3 MB, error over 5 MB (core check 8). No embedded video: link out or use a poster image.

## Reference shares (read-only, in blend-share-files/)

- article: `critical-7` (eBook, canon), `harnesspatterns`, `before-the-agent-starts-building`, `self-learning-systems`.
- commercial: `synthetic-intelligence-layer` (one-pager, @page), `synthetic-studio-engagement-model` (stages/lanes), `uascctlaunchpad-deliverables-demo` (co-brand + "Illustrative" + Confidential), `aiforgoodemea` (co-brand cases; do not copy client logos, 5 MB is too heavy), `diageo-dbx` (structure only: its font falls back to system-ui).
- Duplicates counted once: `agent-friendly-knowledge-sharing` = `agentic-knowledge-sharing-stars`; `diageo-dbx` = `diageo-dbx-blend`.

## Validation

`validate_editorial.py` runs the core `validate.py` (11 checks) and adds E1 prose measure 42-56ch, which is 60-80 characters in PP Telegraf (px 460-620 is a WARN), E2 line-height >= 1.6, E3 body >= 16px, E4 one h1, E5 CTA (commercial), E6 `@page` + sheet count (one-pager), E7 co-branding (topbar, alts, client image <= 200 KB, Confidential), E8 no horizontal scroll at 375 px (Playwright; SKIP otherwise, then measure with chrome-devtools `emulate viewport 375x800x1,mobile` and compare `scrollWidth`). Results: [references/validation-baseline.md](references/validation-baseline.md). See [README.md](README.md) for PENDIENTE and limits.
