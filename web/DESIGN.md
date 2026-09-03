---
name: Farma Precios Ecuador
description: Comparador de precios de medicamentos en Ecuador, con la voz visual de una factura — no de un panel SaaS.
colors:
  paper: "#f7f3ea"
  paper-edge: "#e8e0cc"
  paper-raised: "#fffdf7"
  ink: "#17160f"
  ink-muted: "#57503f"
  ink-faint: "rgba(23, 22, 15, 0.2)"
  stamp: "#244f59"
  stamp-dark: "#16333a"
  stamp-bg: "#dee9ea"
  deal: "#2f6b4f"
  deal-dark: "#1f4d38"
  deal-bg: "#e3ede6"
  warn: "#6b4a15"
  warn-bg: "#f3e9d4"
typography:
  hero:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "clamp(2.1rem, 5.4vw, 3.35rem)"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.032em"
  display:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "1.55rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "0.96rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "IBM Plex Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "0.7rem"
    fontWeight: 700
    letterSpacing: "0.08em"
  price:
    fontFamily: "IBM Plex Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "1.18rem"
    fontWeight: 600
    letterSpacing: "normal"
rounded:
  sm: "3px"
  pill: "999px"
spacing:
  xs: "0.4rem"
  sm: "0.85rem"
  md: "1.25rem"
  lg: "1.75rem"
components:
  ledger-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    padding: "0.85rem 0"
  ledger-row-cheapest:
    backgroundColor: "{colors.deal-bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
  chip:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.4rem 0.8rem"
  cta-button:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper-raised}"
    rounded: "{rounded.sm}"
    padding: "0.32rem 0.65rem"
  stamp-badge:
    backgroundColor: "{colors.deal}"
    textColor: "{colors.paper-raised}"
    rounded: "{rounded.pill}"
    padding: "0.18rem 0.5rem"
---

# Design System: Farma Precios Ecuador

## Overview

**Creative North Star: "La Factura"**

Farma Precios Ecuador reads like a real Ecuadorian receipt, not a health-tech dashboard. The category defaults to one of two costumes: rounded-card SaaS-blue, or clinical hospital-white. Both borrow authority from somewhere else. A factura doesn't need to borrow it — a receipt is already the most credible object in commerce: exact, itemized, verifiable, never inventing a number that isn't printed on it. The product's own governing rule ("nunca calcular ni inventar precios — publicar exactamente lo que muestra cada farmacia") *is* the receipt's rule, so the visual system just makes that promise legible at a glance.

The palette is warm cream paper and near-black ink, with a single ink-stamp red used sparingly, the way a real stamp only appears once per document. Rows are ledger lines, not cards — thin hairline rules instead of shadows and radius, because a ledger's credibility comes from alignment and repetition, not ornament. Motion exists to reinforce the metaphor of a document being produced in front of you (rows "print in," prices "roll" into place like a mechanical counter, a best-price stamp lands with impact) rather than to decorate an otherwise static page — the brief explicitly rejected a static, simple feel.

Confirmed visual anti-references: no rounded SaaS cards with soft drop shadows; no neon/glow treatment (considered and rejected by the user as "not serious enough" for a health-pricing tool); no gradient text or hero illustration; no emoji or glyph icon system.

**Key Characteristics:**
- Warm cream paper background, near-black ink text, one disciplined red accent
- Ledger rows (hairline rules) instead of cards (radius + shadow)
- IBM Plex Sans for prose, IBM Plex Mono for anything numeric or labeled
- Regulatory data (precio techo) always lives in its own labeled line, visually separated from farmacia prices, never merged into the comparison
- Motion reads as "the document is being produced," not as generic fade-ins

## Colors

Warm, desaturated, paper-and-ink — one accent used with real restraint.

### Primary
- **Petroleo / Deep Petrol Blue** (`#244f59`, deep variant `#16333a`, wash `#dee9ea`): the single accent. Was a brick red (`#a6362a`) until 2026-09 — changed because red read as "sale/e-commerce" to the product owner, the exact register the brand wants to avoid. Petrol blue keeps the same one-accent role: brand band, focus rings, link hover states, the mono "EC" wordmark badge, and price figures inside preview cards. A warm gold (`#dcae5c`) is used only as the em-accent inside the hero headline on the colored band, where the deep blue background needs a warm counterpoint rather than another cool tone.

### Secondary
- **Verde Trato / Deal Green** (`#2f6b4f`, deep variant `#1f4d38`, wash `#e3ede6`): reserved exclusively for "this is the best price here" signals — the "Mejor precio" stamp badge and the generic-drug (GEN) tag. Its meaning is fixed: green only ever means a validated best-price or generic-equivalence signal, never decoration.
- **Ámbar Aviso / Warn Amber** (`#6b4a15` on `#f3e9d4`): the legal/medical disclaimer bar only. Deliberately unglamorous so it reads as a notice, not a call to action.

### Neutral
- **Papel / Paper** (`#f7f3ea`): page background.
- **Papel Elevado / Raised Paper** (`#fffdf7`): logo circles, chips, CTA text-on-dark — the "brighter sheet" surface.
- **Papel Borde / Paper Edge** (`#e8e0cc`): chip and "MARCA" tag background.
- **Tinta / Ink** (`#1c1b18`): primary text, primary CTA background.
- **Tinta Tenue / Muted Ink** (`#57503f`): secondary text, timestamps, sub-labels. Raised from `#746b57` on 2026-09-02: the old value measured 4.0:1 on paper, under the 4.5:1 floor for body text, and was the single biggest reason the page read "washed out" rather than "serious".
- **Tinta Fantasma / Faint Ink** (`rgba(23,22,15,0.2)`): all hairline borders and dividers. **Never used as a text color** — at 20% opacity it disappears. The search placeholder used to be set in this token and was effectively invisible.

### Named Rules
**The One Stamp Rule (revised).** The accent's original rule ("never fills a background larger than a badge") no longer holds since the header/footer became a full-width brand band — that was a deliberate later decision, documented in Layout section below, not a violation. What still holds: outside the brand band and its cards, the accent stays a small mark (focus rings, links, badges), never a large fill on the paper background itself.

**The Green-Means-Verified Rule.** Deal green only appears next to a claim the data actually supports (lowest price within a genuinely comparable set, or a confirmed generic). It never decorates.

## Typography

**Display/Body Font:** IBM Plex Sans (self-hosted via `@fontsource`, weights 400/500/600/700)
**Label/Mono Font:** IBM Plex Mono (self-hosted, weights 400/500/600)

**Character:** Plex Sans carries prose and product names with quiet confidence — no display face, no italic flourish. Plex Mono marks anything that functions like a printed figure on a receipt: prices, stock labels, field labels, breadcrumbs, the brand's "EC" stamp. The pairing is the typographic version of the whole system: one voice for what's being said, one voice for what's being counted.

### Hierarchy
- **Display** (700, 1.55rem, tight -0.015em tracking): page `<h1>` — drug name, principio activo name.
- **Title** (600, 0.96rem): ledger row product names.
- **Body** (400, 0.9rem, 1.6 line-height): descriptive paragraphs, disclaimers, notes.
- **Price** (600, 1.18rem, IBM Plex Mono, tabular-nums): every price figure, no exceptions — prices are never set in the sans face.
- **Label** (700, 0.7rem, IBM Plex Mono, 0.08em tracking, uppercase): field labels ("Buscar medicamento", "Búsquedas frecuentes"), stock status, tags (GEN/MARCA).

### Named Rules
**The Mono-Means-Data Rule.** If a value could change per medicamento/farmacia (price, stock, a tag, a field label), it's set in IBM Plex Mono. If it's authored prose, it's Plex Sans. This is how the page signals "this part is real data, not copy" without an icon.

## Layout

One container, `--page-w: 1320px` (1500px above 1700px viewports), mobile-first, and **everything hangs off its single left edge** — header, disclaimer text, hero, sections, footer.

**The page is wide on purpose.** An earlier note here argued for a narrow column because "a factura is a vertical document". That was the metaphor talking over the product: this is a comparison tool, and screen width is the advantage — more rows and more columns visible at once. At 980px the site used ~68% of a 1440 screen and read as a newspaper column. Reading measure is still protected per prose block (`.prose`, 62ch), never by shrinking the page.

**Wide layouts must be filled with content, not air.** Widening alone stretched the ledger row until a huge gap opened between the pharmacy name and its price. The fix was not to cap the row but to give the width something to hold: above 1080px the medicamento page splits into the comparison plus an aside (other presentations, related drugs), divided by a hairline rather than a card. This replaced an arrangement where wide sections lived at 1180px and reading content in a 760px column centered inside it: two centered boxes of different widths share no edge, so on desktop nothing lined up with anything. Reading measure is now constrained per prose block (`.prose`, 62ch) instead of by narrowing the whole page, because ledger rows read better wide, with the price anchored to the right edge. Content padding is `1.1rem` horizontal on mobile, unchanged at desktop width since the column itself never exceeds 720px. Vertical rhythm runs on a small set of steps: `0.4rem` (tight label-to-control), `0.85rem` (row padding), `1.25rem` (section gaps), `1.75rem` (major section breaks, marked visually by the `.tear` perforation divider).

Ledger rows use a 3-column CSS grid (`auto 1fr auto`): logo mark, name/detail block, price/CTA block — identical structure across the home search, medicamento, and principio-activo pages so the eye never has to relearn the row shape.

## Elevation & Depth

Flat by default. The system does not use card elevation or hover-lift; depth is conveyed by paper tone shifts (`--paper` → `--paper-raised`) and hairline borders, the way a receipt shows structure through print, not through shadow. The one shadow token in use (`--shadow-sm`, `0 1px 2px rgba(28,27,24,0.09)`) is reserved for the small circular pharmacy-logo marks and the best-price stamp badge — both objects meant to read as physically stamped/pinned onto the page, not as floating UI chrome.

### Named Rules
**The No-Card Rule.** Nothing in this system gets a rounded card with a soft shadow. Rows are separated by a 1px hairline (`--ink-faint`), not by elevation.

## Shapes

Corners are nearly square: `3px` radius on chips, tags, CTAs, and the regulation box — just enough to soften a hard edge, never enough to read as "rounded." The one full-pill shape (`border-radius: 999px`) is reserved for the stamp badge, echoing an actual ink stamp's rounded outline. The precio-techo regulation line is the one bordered box in the system (`1px dashed var(--ink-faint)`), deliberately distinct from the ledger's plain hairline rows — the dash signals "this is a separate, official line item," the same way a tax line is boxed differently from the item list on a real invoice.

## Components

### Ledger Row (signature component)
The core repeating unit across all three page types (search results, medicamento comparison, principio-activo list).
- **Shape:** no radius, no border on the row itself — just a `1px solid var(--ink-faint)` bottom rule, with the group's first row also getting a top rule.
- **Layout:** 3-column grid (logo mark → name block → price block), `0.9rem` gap, `0.85rem` vertical padding.
- **Best-price state:** background becomes a soft left-to-right wash of `--deal-bg` fading to transparent, plus a `stamp-badge` pinned to the top-left corner with a small rotation (`-2deg`) and an impact keyframe on entry.
- **Motion:** rows enter with `print-in` (translateY -6px → 0, opacity 0 → 1) staggered by `45ms` per row, capped at `360ms` — reads as lines being printed in sequence, not popping in at once.

### Odometer (signature component)
Every price and every stat figure is wrapped in `.odometer.roll-in`. On mount it clips (`overflow: hidden`) and slides the figure up from 65% of its own height while fading in, evoking a mechanical counter settling into place rather than a generic fade.

### Stamp Badge
Pill-shaped, `--deal` green background, uppercase Plex Mono label ("Mejor precio"), slight counter-rotation, entrance keyframe overshoots slightly past its resting scale/rotation before settling — reads as a rubber stamp hitting the page.

### Regulation Line (precio techo)
A dashed-border box, separate from the ledger, always labeled "Precio techo oficial · Consejo Nacional de Fijación de Precios (por unidad)" with an explicit note that it is not directly comparable to the presentation prices below it. This component exists specifically so official/regulatory data is never visually or numerically merged with scraped farmacia prices — see [[Precio techo]] in the project bitácora for why that separation is non-negotiable.

### Hero (home only, revised 2026-09)
No longer a paper hero with a metadata sidebar. It is now a two-column band in `--stamp`: left is the headline ("Buscá. Comparás. **Ahorrás.**", the em set in warm gold `#dcae5c` since blue-on-blue had no contrast left to give) plus a one-line subhead with the live product count; right is a context photo (never a medicine box close enough to read — ARCSA restricts that) with a **floating example card** overlapping its bottom edge (`margin-bottom: -2.4rem` on `>=860px`), showing one real medicamento's price across up to three pharmacies, deduped by pharmacy so it can never show the same chain twice at different prices (that bug shipped once and was caught in review, not by luck). Below the band, outside it, sits the search field — a full-width pill, not the old bare-underline field — so it stays visible when `.hero-d` hides during an active search.

### Freshness (footer, not header)
Moved out of the header (2026-09): it competed with the search bar and nav for first-glance attention. Now a plain line in `--ink-muted` at the top of the footer — "Precios actualizados el <fecha>" — still fed by the newest `price_snapshots.fecha`, still omitted rather than guessed if the query fails. The per-row staleness label (`.ledger-stale`, "precio del 5 de agosto") on comparison pages is the mechanism that actually protects against showing an old price as current; the header stamp was decoration on top of that, not the safeguard itself.

### Category Row
Categories are **ledger rows, not tiles**: a `auto 1fr auto` grid (icon in the category colour, name, count in Plex Mono) with a hairline under each, flowed into an `auto-fill` grid of ~240px columns. The earlier pastel rounded tiles violated this system's own No-Card Rule and were the main reason the home read as two visual languages arguing.

### Preview Carousel (hover, never click)
Every category row and every marca row carries a hidden panel (`position: absolute; top: 100%`, clipped to the row's own column width so it can never overflow the viewport) that reveals a horizontal strip of real products — name, price — ending in a `Ver todo →` card in `--stamp`. It never triggers on click, only on `:hover`/`:focus-within`; the row's own click target still goes straight to the full category or marca page, unchanged. The slide distance is measured in JS per-row (`preview-carousel.ts`), not approximated in CSS, because each category or marca has a different number of products and a fixed-percentage keyframe would over- or under-shoot depending on the case. Respects `prefers-reduced-motion` by jumping straight to the end state instead of animating.

**Third instance, in the global header nav (2026-09).** The same component now also hangs off every `.cat-nav` item in `Layout.astro` — present on all 2293 pages, not just the home. Two things differ there from the home/marcas instances: the data comes from a module-level-cached `getPreviewPorCategoria()` (`categoria-preview.ts`), because without caching a layout used on every page would re-run the catalog's heaviest query once per page (measured elsewhere in this session: 217s uncached vs 11s cached, for a lighter query than this one). And the panel switches to `position: fixed` with JS-computed coordinates (`posicionFija` option) instead of the simple `absolute` used elsewhere, because `.cat-nav ul` has `overflow-x: auto` for its own horizontal scroll on narrow screens — confirmed by testing, that clips any `absolute` child that escapes its box, so `opacity: 1` alone wasn't enough to make it visible there. The `fixed` calculation also flips the panel to anchor from the trigger's right edge instead of its left when the default placement would overflow the viewport — verified against a forced edge case (narrow viewport, nav scrolled to its last item). **Revised again the same day**: the header instance does not reuse the horizontal slide from home/marcas. The user clarified they wanted a vertical dropdown there instead — each product falling into place one after another (a staggered `translateY` entrance, same `print-in` language the rest of the system already uses), not the same motion cramped into a narrow column. `preview-carousel.ts` gained a `desplazamientoHorizontal` option (default true, so home/marcas are untouched) that the header sets to false: the JS there only positions the panel, the stagger-in is a pure CSS `@keyframes` triggered by `:hover`/`:focus-within`, with each row's delay set inline from its index. Caught in the same pass: `.navcat-cp-item` is an `<a>` nested inside `.cat-nav`, so the header's own `.cat-nav a { color: ... }` rule (higher specificity — one class plus one element type beats one class alone) was silently winning and rendering the product name in near-white text on the panel's near-white background. Fixed by raising the selector's specificity and giving the name span its own explicit color, rather than trusting inheritance through a rule that can be re-specified elsewhere.

### Chips
Búsquedas-frecuentes chips: `--paper-raised` background, `1px solid --ink-faint` border, `3px` radius, hover shifts border and text to `--stamp`/`--stamp-dark`, plus a small lift (`translateY(-1px)`) and soft shadow.

### Search Field (revised 2026-09)
A full-width pill (`border-radius: 999px`), not the bare-underline field from the original factura direction — the underline read as too quiet once the search field had to work as the hero's main call to action rather than a quiet detail beneath a headline. `--paper-raised` background, hairline border that shifts to `--stamp` on focus, a solid `Comparar` button in `--ink` on the trailing edge.

### Navigation / Header (revised 2026-09)
Two-row brand band: top row is the wordmark plus the rotated mono "EC" stamp badge, a hairline-divided tagline ("Comparador independiente de precios", hidden below 700px), and — on every page except the home, where the hero's own search field already owns that job — a compact header search field. Second row, one shade darker (`--stamp-dark`), is the categories nav: it no longer stops at `--page-w` on its right edge, only its left edge is pinned to that measure (matching the wordmark above it) — the row itself runs to the true edge of the viewport, same principle as the wide-page decision below. A duplicate of the footer's fact ticker runs above the whole band, offset in its loop timing from the footer copy so the two never look like a synchronized mirror when both are in view.

## Do's and Don'ts

### Do:
- **Do** set every price and every count in IBM Plex Mono with `tabular-nums`.
- **Do** keep the precio-techo regulation line visually and structurally separate from the pharmacy-price ledger, in its own dashed box with its own explanatory note.
- **Do** stagger row entrance animation by list position (`45ms` steps, `360ms` cap) so multi-row lists read as sequential, not simultaneous.
- **Do** reserve `--deal` green strictly for signals the underlying data actually supports (validated cheapest-in-set, confirmed generic).

### Don't:
- **Don't** put a "cheapest" or "best price" badge on a result set that isn't guaranteed to be the same medicamento/presentación — an ungrouped free-text search result list must never claim a cross-product minimum as a fact.
- **Don't** introduce rounded cards, drop shadows, or hover-lift; depth comes from paper-tone shifts and hairlines only. This has been violated twice by "make it friendlier" passes and reverted both times — friendliness comes from the headline's voice and from colour in the ledger, not from tiles.
- **Don't** hard-code a count, total, or date into copy. The ticker once read "2,875 productos comparados" as a literal string and was quietly false within a day. Every figure on the page comes from the database or is omitted.
- **Don't** use any icon system beyond real pharmacy-chain logos and the geometric "F" favicon — no emoji, no glyph icon font.
- **Don't** reintroduce neon, glow, or saturated gradient treatments — explicitly rejected by the product owner as reading "not serious enough" for a medical-pricing tool.
