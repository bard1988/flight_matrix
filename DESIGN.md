---
name: FlightMatrix
description: A flexible-date, any-destination fare board that compares many trips at once
colors:
  ink: "#0b0b0b"
  ink-secondary: "#52514e"
  ink-muted: "#6c6960"
  paper: "#f9f9f7"
  paper-raised: "#fcfcfb"
  gridline: "#e1e0d9"
  axis: "#c3c2b7"
  hairline: "rgba(11, 11, 11, 0.1)"
  marker-yellow: "#f2b705"
  verified-green: "#0ca30c"
  error-red: "#d03b3b"
  advisory-amber: "#fab219"
  fare-0: "#12603d"
  fare-1: "#19773f"
  fare-2: "#278d41"
  fare-3: "#bb7c24"
  fare-4: "#e0875c"
  fare-5: "#f99885"
  fare-6: "#fbb7b4"
typography:
  display:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "normal"
    fontFeature: "tabular-nums"
  headline:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  label:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "0.02em"
  numeric:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "9px"
    fontWeight: 400
    lineHeight: 1.6
    fontFeature: "tabular-nums"
rounded:
  cell: "2px"
  chip: "3px"
  sm: "4px"
  control: "6px"
  container: "8px"
spacing:
  hair: "2px"
  xs: "4px"
  sm: "6px"
  md: "10px"
  lg: "16px"
components:
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper-raised}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-primary-stale:
    backgroundColor: "{colors.marker-yellow}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "5px 8px"
  card:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.container}"
    padding: "7px 9px 8px"
  tag:
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.chip}"
    padding: "0 3px"
  matrix-cell:
    rounded: "{rounded.cell}"
    height: "17px"
    width: "26px"
    typography: "{typography.numeric}"
---

# Design System: FlightMatrix

## Overview

**Creative North Star: "The Departures Board"**

FlightMatrix looks like the analog board in an airport concourse: tabular, glanceable, numbers first, and stripped of decoration. The interface's whole job is to get out of the way of a dense grid of prices so the eye can scan across destinations and date pairs and land on the cheap one. Every element is sized to the information it carries — a fare cell is 26×17px because that is what a four-digit price needs, not a pixel more — and the chrome around the grid is deliberately quiet: hairline borders, a faint warm-paper ground, one weight of one typeface doing all the hierarchy.

The stance is **a quiet instrument, explicitly not a consumer travel site**. There are no hero images, no gradients, no urgency banners, no "1 seat left" theatre, no decorative colour. The one place colour is loud — the green-to-red fare heatmap — is load-bearing data, and even there the number is always printed on the cell so colour is never the only signal. The product's voice is candid about its own limits (estimates are a ranking, not a quote; a hatched cell means "no data", not "expensive") and the design carries that honesty: states are labelled in words, warnings ship with text, and nothing is styled to look more certain than it is.

Density is high and calculated. Several destination cards sit side by side, each matrix scrolls inside its own fixed viewport rather than stretching the card, and the page fills the viewport edge to edge like a tool rather than sitting in a document column. Motion is minimal — a panel slide, a locate pulse — and surfaces are flat.

**Key Characteristics:**
- Numbers-first: tabular figures everywhere comparison happens; the grid is the hero.
- One typeface, one warm-neutral palette, hairline separation — the chrome recedes.
- Flat by default: depth is a 1px border or a tonal step, not a shadow.
- Colour is a second channel, never the only one; yellow is reserved for the "cheapest" marker.
- Honest states: labelled in words, never over-styled for false confidence.
- Light and dark are equal citizens (system-following, with a manual override).

## Colors

A warm near-monochrome — cream-tinted paper, near-black ink, warm greys — with colour admitted only where it carries meaning: the fare heatmap, the reserved "cheapest" yellow, and three small status hues.

### Primary
- **Ink** (`#0b0b0b`): Primary text, and the fill of the primary (Search) button and emphasised borders. A near-black that reads as black but is a touch softer.

### Neutral
- **Paper** (`#f9f9f7`): The page ground and the fill of every input and secondary button. A faint cream warmth, not a cool grey — this is the system's neutral character and is intentional.
- **Paper Raised** (`#fcfcfb`): Cards, the sticky header, the side panel, the tooltip — one step lighter than Paper so raised surfaces separate by tone alone.
- **Ink Secondary** (`#52514e`): Body-weight secondary text — status line, panel values, weekend header emphasis.
- **Ink Muted** (`#6c6960`; `#97938a` in dark): Field labels, filter-group headers, tags, status hints, card metadata — present but not competing. Darkened from a paler grey so it clears WCAG AA (≥ 5:1 on both surfaces) at the small sizes it runs at.
- **Gridline** (`#e1e0d9`): Table rules, dividers, the neutral "no scale available" cell, cross-hair header wash.
- **Axis** (`#c3c2b7`): Input and button borders at rest, scrollbar thumbs, the dotted week-diagonal guide.
- **Hairline** (`rgba(11, 11, 11, 0.1)`): The default 1px border on cards, panels, tags and the tooltip — a translucent ink so it sits correctly on any near-white.

### Tertiary — status hues (each used on a tiny area, always with a word or icon alongside)
- **Verified Green** (`#0ca30c`): The `LIVE` tag and its cell border — a price confirmed on Google Flights.
- **Error Red** (`#d03b3b`): Error text in the status line only.
- **Advisory Amber** (`#fab219`): Coverage/horizon warnings (as a left border on a text hint), the "price is stale" dot, the drift badge, and the Search button when a pending change needs a re-run.

### The Fare Heatmap (`fare-0` … `fare-6`)
A seven-step green → amber → red ramp from **`#12603d` (deep green, cheapest)** through **`#bb7c24` (gold, mid)** to **`#fbb7b4` (faded warm red, dearest)**. Its **OKLCH lightness is strictly monotonic** cheapest → dearest (L 0.43 → 0.84, minimum step ΔL 0.065), which is what carries the scale when hue is lost. The **cheap end owns the salience**: a dark, saturated green that jumps off the warm-white field, so the eye lands on the good dates first; the dear end recedes toward the surface. Scaled *per matrix* — each card runs its own cheapest to its own dearest. Each step ships a matched ink token (`--qi0`…`--qi6`, black or white by measured contrast, minimum label contrast 4.66:1). Dark theme mirrors it on the near-black ground: cheap = the brightest green (L 0.83), dearest = a deep muted red (L 0.40). Derive and re-validate with `data/emit_fare_ramp.py`; full step values and tonal context in `.impeccable/design.json`.

### Named Rules
**The Colour-Is-Second Rule.** Every priced cell prints its price, and the fare ramp's OKLCH lightness is strictly monotonic cheapest → dearest, so the scale still separates every step with hue removed — green, amber and red otherwise collapse together under deuteranopia. Any ramp change must keep the lightness monotone (min step ΔL ≥ 0.06) and re-run `data/emit_fare_ramp.py`. Never ship a state where colour is the only carrier of meaning.

**The Reserved Yellow Rule.** `marker-yellow` (`#f2b705`, `#ffcf33` in dark) marks the cheapest cell — a ring on each card's own cheapest, a thicker ring plus card border on the board-wide cheapest. It appears **nowhere** in the fare ramp, so a yellow ring can never be misread as a price level.

**The Per-Matrix Scale Rule.** Heatmap colour ranks date pairs *within one destination*, never across cards. A green cell on an expensive city can cost more than a red cell on a cheap one. Cross-card comparison is by headline price and cheapest-first order only — never imply otherwise in UI copy or legend.

## Typography

**Display / Body / Label Font:** `system-ui` (with `-apple-system, 'Segoe UI', sans-serif`) — one native UI stack for everything. No web font is loaded; there is no separate display or mono face.

**Character:** Neutral, legible, invisible. The typeface is not expressing anything — hierarchy is carried entirely by size and weight, and precision by numerals. Because numbers are the content, `font-variant-numeric: tabular-nums` is applied to every figure that gets scanned or compared.

### Hierarchy
- **Display** (600, 26px): The single large price in the detail panel — the one big number on the surface.
- **Headline** (600–700, 15–16px, −0.01em): The wordmark, destination card titles (`h2`), and the panel heading. The ceiling for type size in the chrome.
- **Body** (400, 14px, 1.45): Default text — inputs, status line, panel prose, the footnote.
- **Label** (400, 11px, +0.02em, UPPERCASE): Field labels above every control; filter-group headers at 11px/600.
- **Tag** (600, 11px, +0.03em, UPPERCASE): `EST` / `KIWI` / `LIVE` provenance chips.
- **Numeric / cell** (400, 9px, tabular-nums): The price printed in each fare cell, and the matrix's own date-axis headers (9px, 500). This is the **one place below the 11px functional-text floor** — it's the dense data grid, sized so many cards fit on one screen, and contrast still clears WCAG AA.

### Named Rules
**The 11px Floor Rule.** Functional text (labels, tags, hints, buttons, meta) is never below 11px. The only exception is inside the fare matrix — its cell values and date-axis headers run at 9px because it is a dense data grid and 11px would break its density.

### Named Rules
**The Two Family Rule.** (Supersedes the One Family Rule, which required a single
`system-ui` stack and banned monospace outright.) Exactly two families, each with one job:
**Geist** for all chrome, **Geist Mono** for every numeral a user might compare, sort or
watch update. Both are self-hosted in `frontend/fonts/`, so the board makes no
third-party font request. Weight (400/500/600/700) and size still carry hierarchy inside
each family. Do not add a third family, and do not use the mono for prose: the panel's
definition list and the flight-leg lines carry words next to their figures and stay in the
sans with `tabular-nums`. Numeric surfaces are enumerated in one selector list at the top
of `styles.css`; add to that list rather than setting `font-family` ad hoc.

**The Tabular Numbers Rule.** Any number a user might compare, sort, or watch update uses `font-variant-numeric: tabular-nums` so digits stay column-aligned. This is already on the matrix, every headline price, the panel, and the table view.

## Layout

**Full-bleed, not a column.** The app fills the viewport edge to edge (`main` padding 14–16px desktop, 10px mobile). There is no max-width — this is a tool, not a document.

**The board is a responsive card grid.** `grid-template-columns: repeat(auto-fill, minmax(420px, 1fr))`, 10px gap, `align-items: start`. On desktop 2–3 destination cards sit side by side; at ≤720px it collapses to a single column.

**Each matrix is its own scroll viewport.** A card does not grow to fit its date grid. The grid lives in `.matrix-wrap` at `max-height: min(46vh, 268px)` with both-axis overflow, `overscroll-behavior: contain`, `scrollbar-gutter: stable both-edges`, and deliberately **visible** thin scrollbars (styled, not overlay-hidden) so it is obvious the grid scrolls and how far through it you are. Scroll position survives re-renders. Pushing ~160px past an edge requests a wider date window from the backend (widening costs live API calls, so it must be deliberate).

**Pinned axes.** While a matrix scrolls, `thead th` (departure row), `th.row` (return column), and `th.corner` stay stuck via `position: sticky` with a z-order of corner (3) > header row (2) > row header (1).

**Header.** Sticky at the top on desktop (`z-index: 30`); on mobile it is `position: static` and scrolls away (the control bar is several rows tall there), with an "Options" toggle that collapses all but the essential fields.

**Spacing rhythm.** Two scales in play: a tight `2 / 3 / 4px` micro-scale inside the grid (`border-spacing: 2px`, 2px cell radius) and a `6 / 10 / 14 / 16px` scale for the chrome (control gaps `10px 14px`, board gap 10px, card-head gap 8px).

**Breakpoint.** One, at `max-width: 720px`. Below it: single-column board, matrices grow and the page scrolls (only the return-date column stays pinned, for horizontal scroll), inputs go to 16px (no iOS zoom) with larger tap targets, the side panel becomes a full-screen sheet, and the hover tooltip is disabled entirely.

## Elevation & Depth

The system is **flat**. Surfaces separate by a 1px border and a one-step tonal shift (`paper` → `paper-raised`), not by shadow. Selected and focused states are shown with hard, offset **rings** (`box-shadow` spread with a surface-coloured inner gap, or `outline` with `outline-offset`). The side panel slides in over the board with a left border and **no** shadow.

### Shadow Vocabulary
- **Tooltip ambient** (`box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18)`): The only true drop shadow in the system. It belongs to `#tooltip` — the one element that genuinely floats free above everything and follows the cursor.
- **Selection rings** (`box-shadow: 0 0 0 1px var(--paper-raised), 0 0 0 3px var(--marker-yellow)` and heavier for the board best): not elevation — a spread outline that reads as a marker.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest. If you reach for a `box-shadow`, stop: use a 1px border or a tonal step instead. The tooltip is the single sanctioned exception, because it is the single element that actually floats.

**The Ring, Not Glow Rule.** Focus, selection and "you are here" are hard offset rings (crisp, 1–5px spread, often with a 1px surface-coloured gap), never a soft blurred glow. Hover on a fare cell is a 2px ink `outline` at `outline-offset: 1px`.

## Shapes

Rounding is gentle and **tracks element size**: `8px` for containers (cards, panel elements, tooltip), `6px` for controls (buttons, inputs, selects), `4px` for small toggles (day-of-week, locate, fill), `3px` for chips and badges, `2px` for fare cells. The dense grid stays crisp because its tiles are barely rounded and sit in a 2px mesh (`border-spacing: 2px` on a `separate` table).

**Borders are the primary separator:** 1px solid, almost always `hairline` (10% ink), `axis`, or `gridline`. No element uses a border heavier than 1px except the emphasised ink border on a verified cell.

**Recurring geometry — the triangular wedge.** Stops are shown by a small right-angled triangle in a cell's top-right corner, built from CSS borders (`border-top` + transparent `border-left`); a bigger wedge means 2+ stops. The same wedge shape appears in the legend. It is the system's one piece of iconographic vocabulary.

## Components

Controls should feel **refined and restrained** — quiet, considered, a little soft; state changes are calm, nothing bounces.

### Buttons
- **Shape:** 6px radius (`control`), 1px `axis` border.
- **Secondary (default):** `paper` background, `ink` text, `6px 12px` padding. Hover lifts the border to `ink-muted` — no background change, no transition.
- **Primary (`.primary`):** inverted — `ink` background, `paper-raised` text, `ink` border. Used for Search and other commit actions.
- **Primary · running (`.running`):** `opacity: 0.75` while a search streams.
- **Primary · stale (`.stale`):** background flips to `marker-yellow` with `ink` text — "a change you made needs a new search". This is the one place a button changes colour to signal state.
- **Small variants:** `.locate` (3×7px pad, 12px), `.fillbtn` (2×7px, 10px, 4px radius), day-of-week toggles (20px-wide squares, 4px radius; `.on` = solid `ink` fill).

### Chips / Tags
- **`.tag`:** hollow — 1px `hairline` border, 3px radius, `0 3px` padding, 11px/600 uppercase, `ink-muted` text.
- **`.tag.live`:** text and border to `verified-green`. **`.tag.real`:** to `ink-secondary` / `ink-muted`.
- **`.drift`:** filled — `advisory-amber` background, `ink` text, 3px radius. A louder badge for "sources disagree".

### Cards / Containers
- **Corner style:** 8px radius (`container`).
- **Background:** `paper-raised` on the `paper` page.
- **Border:** 1px `hairline`. **Winner (`.is-winner`):** border to `marker-yellow` plus a 1px `marker-yellow` ring.
- **Shadow strategy:** none (see Elevation).
- **Internal padding:** `7px 9px 8px` — tight, because the matrix inside owns the space.

### Inputs / Fields
- **Style:** `paper` background, 1px `axis` border, 6px radius, `5px 8px` padding. Label sits above in 11px uppercase `ink-muted`.
- **Focus:** currently the browser default. *(Gap — a defined focus treatment, a calm border shift to `ink` or a soft ring, would match the "refined and restrained" intent and the a11y target.)*
- **Mobile:** full-width, 16px text, `9px 10px` padding.

### Navigation
There is no nav. The control surface is the sticky header: a `controls-primary` row that always shows the whole task path (From · dates · travellers · Search) and a **Filters** disclosure (`aria-expanded`, chevron rotates, goes solid-`ink` when open) holding everything else in three labelled groups, closed by default at every width. A board's full search is serialised to the query string, so a board is bookmarkable and shareable and re-runs on load.

### Signature Component — the Fare Matrix
- **Cell:** 26×17px (32×22 on mobile), 2px radius, 9px tabular-nums, centred, 1px transparent border, per-step background + ink (`.q0`…`.q6`).
- **States:** `.priced` (pointer), `.nodata` (45° hatch on `paper-raised`, `hairline` border — "no data", *not* expensive), `.notasked` (plain, no border — a trip length you didn't ask for), `.best-here` / `.best-board` (yellow rings, weight 600/700), `.verified` (1px `ink` border), `.excluded` (opacity 0.22, rises to 0.7 on hover — ruled out by a constraint but still visible), `.week-diag` (dotted `axis` left border marking 7/14-night trips), `:hover` (2px `ink` outline).
- **Cross-hair:** hovering a cell washes its column and row with an inset `rgba(127,127,127,0.16)` and turns both date headers `ink`/700 on a `gridline` ground — faint on the data, emphatic on the dates, because "which date is outbound" is the question. Click to pin.
- **Corner wedge** (`.stopdot`): triangular, `currentColor`, `opacity 0.55` (0.8 and larger for 2+ stops). **Stale dot** (`.staledot`): 3px `advisory-amber` circle, bottom-left.
- **Locate flash:** `@keyframes locate-flash` pulses the marker ring 0.4s × 4 after jump-to-cheapest.
- **Keyboard / SR:** interactive cells are `role="button"` with a full `aria-label` (destination, dates, price, stops) and a roving `tabindex` — one tab stop per grid (the cheapest cell), arrow keys move between cells, Enter/Space prices one. `th` cells carry `scope`; the ◎ locate button hands focus to the cheapest cell.

### Detail Panel (`#panel`)
- 340px, fixed right, full-height. Slides in on `transform: translateX(100%)` → `none` over `0.16s ease`. 1px `hairline` left border, no shadow. Mobile: 100% width, no border — a full sheet.
- Contents: a `dl` on a `auto / 1fr` grid (4px 10px gap), the 26px `.big` price, and `.segments` — flight legs indented under a bold sector summary with a 2px `gridline` left rule and a bold muted leg number.

### Tooltip (`#tooltip`)
`position: fixed`, `paper-raised`, 1px `hairline`, 8px radius, `8px 10px` padding, 12px text, `pointer-events: none`, `max-width: 260px`, the one ambient shadow. Desktop only.

### Status bar
Below the header: 13px `ink-secondary`, one line per message stacked (`flex-direction: column`). Lead line is the streaming progress; then the legend (rule + key); then contextual `.growing` counts (11px `ink-muted`, tabular). Error text in `error-red`; advisory hints (`.hint`) lead with a 6px `advisory-amber` dot, message in normal text. Prose lines cap at ~74ch.

### Table view (`.tableview`, toggled by `body.show-table`)
Replaces the board entirely. Plain `<table>`, `border-collapse`, hairline row rules, 4px 10px cell padding, 13px, `tabular-nums`. Zebra is a ~3.5% ink wash on even rows (`color-mix`), hover ~9%. Numeric columns (Nights, Total) right-aligned. **Every heading sorts** — click toggles direction, `aria-sort` + a ↑/↓ marker show the active column; same column again flips. `Source` renders as a borderless `est` / `live` micro-label (`live` in `verified-green`). Header sticks below the app header on desktop; on mobile the table keeps a 600px min-width and scrolls sideways (sticky header drops there).

## Do's and Don'ts

### Do:
- **Do** print the number on anything that also uses colour to encode a value; the colour is the second channel.
- **Do** keep `font-variant-numeric: tabular-nums` on every comparable figure.
- **Do** separate surfaces with a 1px border (`hairline` / `axis` / `gridline`) and the `paper` → `paper-raised` tonal step.
- **Do** use hard offset rings for focus / selection / "you are here"; give the fare-cell hover a 2px `ink` outline.
- **Do** size an element to its content — the grid's tightness (2px gaps, 2px radius, 9px type) is deliberate.
- **Do** let colour rank *within* a card only; compare across cards by headline price and order.
- **Do** ship every warning and state with a word or icon, not colour alone; keep advisory things in `advisory-amber`, errors in `error-red`, verified in `verified-green`.
- **Do** keep the warm-paper neutrals (`#f9f9f7` / `#fcfcfb`); they are the system's character, not an accident.
- **Do** support light and dark equally — define every colour as a token in all three roots (`:root`, `prefers-color-scheme: dark`, `[data-theme='dark']`).

### Don't:
- **Don't** put functional text below 11px (labels, tags, hints, buttons, meta). The 9px fare matrix is the single sanctioned exception.
- **Don't** run `ink-muted` on `gridline` — it clears AA on the two paper surfaces, not on the mid-grey.
- **Don't** add a `box-shadow` to cards, the panel, buttons, or inputs. The tooltip is the only element that carries an ambient shadow.
- **Don't** use `marker-yellow` (`#f2b705` / `#ffcf33`) as a fill, a ramp step, or anything other than the "cheapest" marker.
- **Don't** introduce a *third* typeface, and don't put the mono on prose. Geist for chrome, Geist Mono for numerals, nothing else.
- **Don't** put the app in a centred max-width column; it is full-bleed.
- **Don't** box a destination in a card. Destinations are plain blocks separated by a 1px `gridline` rule; at this density a container per destination is four borders and a radius that the city name and its own matrix already do for free.
- **Don't** let a destination block grow to fit its matrix. The matrix scrolls inside a fixed viewport (`max-height: min(46vh, 268px)`) so blocks stay comparable.
- **Don't** hide the matrix scrollbars or make them overlay-only; their visibility tells the user there is more grid.
- **Don't** style an estimate to look as certain as a verified price, or a `nodata` cell to look expensive.
- **Don't** add gradients, hero imagery, urgency messaging, or decorative colour — this is an instrument, not a booking funnel.
- **Don't** animate beyond the sanctioned set (panel slide `0.16s`, chevron rotate, locate pulse, smooth locate-scroll). A global `@media (prefers-reduced-motion: reduce)` block damps all of it; keep new motion inside that guard.
