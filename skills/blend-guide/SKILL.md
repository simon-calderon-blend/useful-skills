---
name: blend-guide
description: Builds Blend360 guides, documentation and interactive courses. Short guides become one self-contained HTML (sticky TOC, numbered steps, copy-button code blocks, callouts, flow diagrams); long guides become a Starlight (Astro) site with the Blend theme, Pagefind and mermaid; `course` mode adds modules, progress saved in localStorage (with try/catch) and a quiz per module. Includes validate_guide.py. Use when asked for a Blend guide, how-to, documentation site, onboarding, or course. Builds on blend-web-core.
---

# blend-guide

Produces a guide or a course in one of two formats, on top of `../blend-web-core` (tokens, components, logo, `blend_web.py`, `validate.py`; nothing copied).

| Format | When | Output |
|---|---|---|
| Single HTML | short guide, up to about 8 pages of content | `index.html`, about 30 KB, no JS dependencies |
| Starlight site | long guide (more than about 8 pages), search needed | Astro project themed with `blend-theme.css`, built to `dist/` |

Mode `course` (either format): modules, per-module quiz, progress in the browser.

## Ask the user for

Content tree (sections, or modules for a course), audience, language (`lang`), short or long (picks the format), whether dark mode is wanted (single HTML: off by default, `--dark` adds a toggle; Starlight: native Auto/Light/Dark, kept; dark stays optional, decided 2026-11-10), for a course the minutes and quizzes. Label sample data "Illustrative"; no client or ADRES content.

## Single HTML flow

1. Write a JSON spec (see `examples/guide.json`, `examples/course.json`). Top level: `title`, `lang`, `eyebrow`, `intro`, `description`, `footer`, `sections`; course adds `"mode": "course"`, `storage_key`, `minutes`. Each section has `title`, optional `id`, and `blocks`.
2. Blocks (one key each): `p`, `h3`, `list`, `code {lang,title,text}`, `callout {kind: note|warn|bad,title,text}`, `steps [{title,body,code}]`, `table {head,rows,caption}`, `diagram {flow: ["Title|sub",...] | svg, caption}`, `quiz {q,options,answer,why}`, `html`. Inline: `` `code` ``, `**bold**`, `[text](url)`.
3. `python3 scripts/build_guide.py spec.json out/index.html [--dark]`.
4. `python3 scripts/validate_guide.py out/ --kind guide` and read every FAIL/WARN.
5. Look at it at 1280 and 390 px.

Course mode: each section is a module (`data-mod`); the generator warns if a module has no quiz. Progress key = `storage_key`; every storage access is in try/catch and the page works without it. Passing a quiz marks the module; the hero shows a progress bar and a reset button.

## Starlight flow

Copy `assets/starlight/` (theme, config, package.json, symbol logos, favicon) and follow `references/starlight-theme.md` (commands are documented, not run by the skill). Reuse the Blend tokens, PP Telegraf (bundled in the theme, `src/assets/fonts`), accent `#075089` light / `#00c6c6` dark. Course on Starlight: the content tree is the module list (see `ds-onboarding`); add the `.blend-quiz` styles already in the theme if quizzes are needed.

## Components and tokens

From the core: `--blend-*` tokens, `.b-header`, `.b-callout`, `.b-table`, `.b-card`, `.b-kpi`, `.b-chip`. Own (`assets/guide.css`, `guide.js`, `theme.js`): `.g-layout`, `.g-toc`, `.g-steps`, `.g-code`, `.g-flow`, `.g-quiz`, `.g-hero`, `.g-progress`. Cyan is never text on light backgrounds (hero and code blocks are dark).

## Reference shares

`ds-best-practices` and `ai-eng-best-practices` (Starlight theme canon), `ds-onboarding` and `agentic-engineering-course` (courses; the latter is the richest), `welcome`, `sow-best-practices`. ADRES shares: structure only. `blendx-living-docs` deviates (cyan accent over the default Starlight theme): do not imitate. Details in `references/references.md`.

## Validation

`scripts/validate_guide.py PATH [--kind guide] [--course] [--dark ...]` runs the core `validate.py` and adds: G1 one h1 per page; G2 internal links and anchors resolve (strips the `/<slug>/` base); G3 TOC when more than 3 sections; G4 code blocks have a language (mermaid excluded); G5 Starlight `blend-theme.css` has the `--blend-*` tokens and the two accents (source project: also `customCss`); G6 course: localStorage in try/catch, at least one quiz per module. Exit 1 on FAIL. Baseline and its reading: `references/validation-baseline.md`. See also `README.md`.
