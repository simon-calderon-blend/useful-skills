# Delivery checklist

Run before handing over any Blend web page. Each type skill adds its own lines in its SKILL.md.
**Block** items stop delivery; **Review** items need a look and a reason if you keep them.

## Brand fidelity (block)

- [ ] Logo is the inline SVG from `assets/logo.svg`, unmodified; navy on light, white on navy or dark.
- [ ] Every colour is a token or a `color-mix()` of tokens. No `#003059`, no off-token cyan.
- [ ] Font stack starts with PP Telegraf, embedded; weight 400 only.
- [ ] No cyan or soft-cyan text on a light background. Text contrast is 4.5:1 or better (3:1 for 24px and up).
- [ ] Sample data carries the "Illustrative" label; no client data, secrets or ARNs.
- [ ] `validate.py --kind <type>` has no FAIL, and the type validator has none either.

## Composition (review)

- [ ] Squint: one primary element per screen, and it is the right one.
- [ ] One left line from header to footer; prose inside the measure.
- [ ] No two neighbouring sections share a skeleton more than twice; no section is a heading and one paragraph.
- [ ] No orphan card on a last row; no half-empty screen above the footer.
- [ ] No card inside a card; no side-stripe callouts; one separation device per seam.
- [ ] One eyebrow on the page; other labels in sentence case.
- [ ] Cyan appears only on the primary action, the selection, the masthead rule and text on navy.
- [ ] One filled button per view.

## Type and data (review)

- [ ] Spacing and font sizes come from the tokens; nothing below 12px.
- [ ] Headings say what the reader gets; none ends on a one-word line at 390px.
- [ ] Every figure has a unit, a label and a qualifier; no number is repeated in three places.
- [ ] Tables: numbers right-aligned and tabular, headers do not wrap, a caption states the claim.
- [ ] Chart form fits the data; no pie, donut, gauge or dual axis.

## Behaviour (block)

- [ ] No horizontal page scroll at 390px and 1440px (`validate.py --render`, or screenshots).
- [ ] Every control shows hover, focus-visible, active and disabled; tab order follows the page.
- [ ] Hit targets are 44px on touch; button and nav labels stay on one line.
- [ ] Content is readable with JavaScript off; empty and error states are written.
- [ ] Only `transform`, `opacity` and colour animate; the page is still under reduced motion.
- [ ] `lang`, `<title>`, meta description, one `h1`, heading levels step by one, a skip link on long pages.

## Last look

- [ ] Read only the headings: they tell the story.
- [ ] Hide the logo: the page still reads as Blend through its navy regions, its type and its restraint, not
  through an accent colour on a generic template.
- [ ] Check 11 "craft" warnings in `validate.py` are each fixed or explained.
