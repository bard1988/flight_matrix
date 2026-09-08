---
name: FlightMatrix
description: A flexible-date, any-destination fare board — a ranked list of destinations beside the selected one's departure × return price grid
colors:
  ink: "#0b0b0b"
  ink-secondary: "#52514e"
  ink-muted: "#6c6960"
  surface-raised: "#fcfcfb"
  surface-page: "#f9f9f7"
  surface-canvas: "#f4f3ef"
  gridline: "#e1e0d9"
  axis: "#c3c2b7"
  hairline: "rgba(11, 11, 11, 0.1)"
  marker-yellow: "#f2b705"
  verified-green: "#0a7d0a"
  error-red: "#c0261f"
  advisory-amber: "#fab219"
  hatch: "rgba(11, 11, 11, 0.05)"
  fare-0: "#0f9246"
  fare-1: "#7ebb42"
  fare-2: "#fdcb08"
  fare-3: "#f68e1f"
  fare-4: "#ef4723"
  fare-5: "#bc1f26"
  fare-6: "#7f0a13"
typography:
  display:
    fontFamily: "'Geist Mono', ui-monospace, 'SF Mono', monospace"
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.1
    fontFeature: "tabular-nums"
  headline:
    fontFamily: "'Geist', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "19px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  body:
    fontFamily: "'Geist', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "'Geist', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.3
  cell:
    fontFamily: "'Geist Mono', ui-monospace, 'SF Mono', monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tabular-nums"
rounded:
  cell: "0px"
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
    backgroundColor: "{colors.surface-page}"
    textColor: "{colors.ink}"
    border: "1px solid {colors.axis}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface-raised}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-primary-stale:
    backgroundColor: "{colors.marker-yellow}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  field:
    background: "none"
    borderBottom: "1px solid {colors.axis}"
    textColor: "{colors.ink}"
    padding: "4px 2px"
  list-row:
    background: "none"
    borderBottom: "1px solid {colors.gridline}"
    padding: "8px 8px 9px"
    selected: "fill {colors.surface-raised} + inset 2px {colors.ink} left rule"
  tag:
    textColor: "{colors.ink-muted}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.chip}"
    padding: "0 3px"
  matrix-cell:
    rounded: "{rounded.cell}"
    height: "23px"
    width: "32px"
    gap: "1px"
    typography: "{typography.cell}"
---

# Design System: FlightMatrix

## Overview

**Creative North Star: "The Departures Board"**

FlightMatrix looks like the analog board in an airport concourse: tabular, glanceable, numbers first, and stripped of decoration. Its job is to get out of the way of a dense grid of prices so the eye can scan across departure and return dates and land on the cheap one. Every element is sized to the information it carries — a fare cell is 32×23px because that is what a four-figure price needs, not a pixel more — and the chrome around the grid is deliberately quiet: hairline borders, a faint warm-paper ground, one workhorse typeface doing all the hierarchy by weight and size.

The stance is **a quiet instrument, explicitly not a consumer travel site**. No hero images, no gradients, no urgency banners, no "1 seat left" theatre, no decorative colour. The one place colour is loud — the green→red fare heatmap — is load-bearing data, and even there the number is always printed on the cell so colour is never the only signal. The voice is candid about the product's limits (estimates are a ranking, not a quote; a hatched cell means "no cached data", not "expensive") and the design carries that honesty: states are labelled in words, warnings ship with text, nothing is styled to look more certain than it is.

**The composition is master–detail, in a full-viewport app shell.** Once a search returns, the results take over the whole screen and the page itself stops scrolling. On the left, a fixed-width **ranked list** — one tight row per destination, cheapest first, each row carrying the essence of that destination's grid (name, country, cheapest fare, price ceiling, cheapest date pair). On the right, the **one selected destination's full departure × return grid**, filling its pane. The two panes scroll independently: running down the list never moves the grid. Pick a row and its grid loads beside it; on a phone the list is the whole screen and the grid slides in over it. This replaced an earlier layout of many small grids side by side — the deal-hunter's real task is *scan the list, then drill into one*, and one grid with room to breathe reads better than twenty that can only be scrolled past.

Motion is minimal — a panel slide, a locate pulse, a slow "searching" breathe, a card fade-in as each destination streams. Surfaces are flat.

**Key Characteristics:**
- Numbers-first: tabular figures everywhere comparison happens; the grid is the hero.
- Master–detail: a ranked list you scan, one grid you study. Independent scroll regions in a viewport-filling shell.
- Two families (Geist for chrome, Geist Mono for every numeral), one warm-neutral palette, hairline separation — the chrome recedes.
- Flat by default: depth is a 1px border or a tonal step, not a shadow.
- Colour is a second channel, never the only one; yellow is reserved for the "cheapest" marker.
- Honest states: labelled in words, never over-styled for false confidence.
- Light and dark are equal citizens (system-following, with a manual override).

## Colors

A warm near-monochrome — cream-tinted paper, near-black ink, warm greys — with colour admitted only where it carries meaning: the fare heatmap, the reserved "cheapest" yellow, and three small status hues. Every colour is a CSS custom property defined in all three roots (`:root`, `@media (prefers-color-scheme: dark)`, `:root[data-theme='dark']`).

### Grounds — three stepped surfaces
- **Canvas** (`#f4f3ef` light / `#0d0d0d` dark): the recessed results area — the list and the grid sit on this.
- **Page** (`#f9f9f7` / `#0d0d0d`): the document ground the first-run and controls sit on; the fill of every underlined field's dropdown.
- **Surface-raised** (`#fcfcfb` / `#1a1a19`): the control bar, the side panel, the tooltip, the country popover, a hovered/selected list row — one step up from Page so raised chrome separates by tone alone.

### Ink
- **Ink** (`#0b0b0b` / `#fcfcfb`): primary text; the fill of the primary (Search) button and of `.on` day-of-week toggles; emphasised borders and the "you are here" list-row rule.
- **Ink Secondary** (`#52514e` / `#c3c2b7`): status line, the cheapest-date line under a list row, panel values, weekend axis emphasis.
- **Ink Muted** (`#6c6960` / `#97938a`): field labels, filter-group headers, tags, country names, range figures, hints. Darkened from a paler grey so it clears WCAG AA (≥ 4.5:1) on both paper surfaces at the small sizes it runs at.

### Lines
- **Gridline** (`#e1e0d9` / `#2c2c2a`): list-row rules, table rules, the neutral "no scale available" cell, the section-label underline.
- **Axis** (`#c3c2b7` / `#383835`): field underlines and button borders at rest, scrollbar thumbs, the dotted week-diagonal guide.
- **Hairline** (`rgba(11,11,11,0.1)` / `rgba(255,255,255,0.1)`): the 1px border on the header, panel, popovers, tooltip and tags — a translucent ink so it sits correctly on any near-white or near-black.

### Status hues (each on a tiny area, always with a word or icon alongside)
- **Verified Green** (`#0a7d0a` / `#0ca30c`): the `LIVE` tag and the border of a live-priced cell.
- **Error Red** (`#c0261f` / `#ff8078`): error text in the status line only.
- **Advisory Amber** (`#fab219`, one value both themes): coverage/horizon hints (a 6px dot before the text), the "price is stale" dot, the calendar-drift badge, and the Search button when a pending change needs a re-run.

### The Fare Heatmap (`fare-0` … `fare-6`)
A seven-step green → yellow → red ramp, **one ramp for both themes**: `#0f9246` (deep green, cheapest) · `#7ebb42` · `#fdcb08` (yellow, mid) · `#f68e1f` · `#ef4723` · `#bc1f26` · `#7f0a13` (deep red, dearest). It is **art-directed, not lightness-monotonic**: q0–q5 are sampled verbatim from a supplied credit-score scale (Excellent → Very Bad) and q6 is a deeper red added at the same hue to pull the ends apart. Two costs are accepted knowingly and documented in `styles.css` and `.impeccable/design.json`:

1. **Lightness humps** (yellow q2 is the lightest band) instead of falling, so tone alone does not rank the scale. Cheapest-vs-dearest separation under deuteranopia is 18.9 ΔE (vs 38.8 for a monotonic green→red ramp); the worst adjacent pair is q1 vs q3 at 4.4 ΔE. Affordable **only** because every cell prints its price and the table view lists every value.
2. **q2 is yellow**, which brushes the Reserved Yellow Rule. It survives because the cheapest marker only ever lands on q0, is a *ring* not a fill, and carries a 1px ink edge.

Each step ships a matched ink token (`--qi0`…`--qi6`: black for q0–q4, white for q5–q6, chosen by measured contrast). Colour is scaled **per matrix** — the one grid on screen runs its own cheapest → its own dearest. Derive and re-validate any change with `data/emit_fare_ramp.py`.

### Named Rules
**The Colour-Is-Second Rule.** Every priced cell prints its price; the table view lists every value; the fare ramp is never the only carrier of meaning. This ramp trades lightness-monotonicity for exact reference colours, so the printed number is not optional — it is the primary channel and the colour is the accent.

**The Reserved Yellow Rule.** `marker-yellow` (`#f2b705` / `#ffcf33`) marks the cheapest cell only — a ring on the grid's own cheapest cell, a thicker ring-plus-ink-edge on the board-wide cheapest cell. It appears **nowhere** as a fill: not a ramp step, not a selection background, not a text-selection wash. The ranked list needs no yellow of its own — it is sorted cheapest-first, so the board's cheapest destination is always row 1.

**The Per-Matrix Scale Rule.** Heatmap colour ranks date pairs *within the destination on screen*, never across destinations. A green cell on an expensive city can cost more than a red cell on a cheap one. Cross-destination comparison is by the list's fares and its cheapest-first order only — never imply otherwise in copy or legend.

## Typography

**Two families, self-hosted, each with one job** (`frontend/fonts/*.woff2`, so the board makes no third-party font request):

- **Geist** (400/500/600/700) — all chrome: labels, headings, prose, buttons, the wordmark.
- **Geist Mono** (400/500/600) — every numeral a user might compare, sort, or watch update: the fare cells, the axis dates, list-row prices, the panel's big price, the table's numeric columns. Enumerated in one selector list at the top of `styles.css`; add to that list rather than setting `font-family` ad hoc.

**Character:** neutral, legible, invisible. The typeface expresses nothing — hierarchy is carried by size and weight, precision by `font-variant-numeric: tabular-nums` on every scanned figure (kept even though Geist Mono is fixed-advance, so the fallback stack still aligns if the webfont fails).

### Hierarchy
- **Display** (Mono, 600, 26px): the one big price in the detail panel.
- **Headline** (Geist, 600, 19px, −0.02em): the selected destination's name (`h2`) in the grid pane. The wordmark and panel heading sit just under it (15–18.5px).
- **Row title** (Geist, 600, 13.5px, −0.01em): a destination's name in the ranked list.
- **Body** (Geist, 400, 14px/1.45): inputs, status line, panel prose, the footnote.
- **Label** (Geist, 400, 11px): field labels above every control. Filter-group headers are 11px/600 uppercase with `0.04em` tracking. **Sentence case, not shouting** — a bar of uppercase wide-tracked labels is what made the search read as a database form.
- **Tag** (Geist, 600, 11px, +0.03em, UPPERCASE): `EST` / `KIWI` / `LIVE` provenance chips.
- **Cell / axis** (Mono, 400, 12px; axis 500 with `+0.01em` tracking): the price in each fare cell and the matrix's date headers. On the 11px functional-text floor, not under it.

### Named Rules
**The 11px Floor Rule.** Functional text — labels, tags, hints, buttons, meta, list-row detail, and now the fare matrix — is never below 11px. (The old 9px matrix exception is retired: it existed to fit many grids on one screen, and the master–detail layout shows one grid in a full pane, which buys the room to put the price on the floor at 12px. Mobile goes to 13px in a 38px cell.)

**The Tabular Numbers Rule.** Any number a user might compare, sort, or watch update carries `font-variant-numeric: tabular-nums`. Already on the matrix, every list-row price and range, the panel, and the table view.

## Layout

**Full-bleed, not a column.** No max-width anywhere. This is a tool.

**First run and empty state** flow as an ordinary document: the header, a one-line status strip, and the pitch. `main` has 14–16px padding, the first-run panel caps at 74ch.

**Once a board exists → the app shell** (`body.has-board`). `<html>` and `<body>` lock to `100dvh` with `overflow: hidden`; `<body>` becomes a flex column. The header and status strip are `flex: none` at the top (the header stops being sticky — it does not need to be, nothing scrolls past it). `<main>` takes the rest as a flex column and does **not** clip (the toolbar's country popover must be able to escape downward; the viewport cap on `<body>` is what prevents a page scrollbar).

**The board is a two-pane split** (`.board-split`, CSS Grid `minmax(240px, 300px) / minmax(0, 1fr)`, `flex: 1; min-height: 0` inside `<main>`):

- **List pane** (`.dlist`): `overflow-y: auto`, `overscroll-behavior: contain`, a 1px `border` on its right edge, a thin themed scrollbar. Flows down its own scroll; the page never moves.
- **Grid pane** (`.ddetail`): a flex column holding one `.card`. The card head is `flex: none`; the `.matrix-wrap` inside is `flex: 1; min-height: 0` and scrolls in **both** axes with pinned date headers. So the pane itself never scrolls as a block — only the matrix within it does — and there is no pane-height scrollbar at the window's edge.

**Pinned axes.** While the matrix scrolls, `thead th` (departure headers), `th.row` (return headers), `th.corner` stay stuck via `position: sticky` on `var(--canvas)`, z-order corner (3) > header row (2) > row header (1).

**Collapse the list** (desktop): a toolbar toggle sets `body.list-collapsed`, which hides `.dlist` and gives the grid the full width. The toggle's own label flips Hide list ⇄ Show list.

**Widen the dates** (per destination): a `± Nd` button in the grid head re-prices just this destination over a window a week wider at each end. Deliberate, because widening costs live API calls.

**Board toolbar** (`.board-tools`, shown only with results): list-collapse toggle · destination count · multi-select country filter (a `.ctry-combo` popover, none checked = all) · currency select · per-person checkbox · Table/Matrix toggle. 13–14px, `ink-secondary`.

**Breakpoints.** Two:
- **≤ 860px** — the split stacks. The list is the whole screen; tapping a destination adds `body.detail-open` and the grid slides in as a `position: fixed` layer with a **‹ All** control in its head. The Table view gets the same full-screen-layer treatment.
- **≤ 720px** — controls stack: search fields go full-width (When / Trip length / Travellers pair up two-per-row), inputs to 16px (no iOS zoom) with ≥40px tap targets, the filters panel is one column, the side panel is a full-screen sheet, the hover tooltip is disabled, the table keeps a 520px min-width and scrolls sideways.

**Spacing rhythm.** A tight `1 / 2 / 4px` micro-scale inside the grid (1px cell gap, 0px cell radius) and a `4 / 6 / 8 / 10 / 14 / 16px` scale for the chrome (control-group gaps `8px 10px`, pane padding `12px 18px`, list-row padding `8px`).

## Elevation & Depth

The system is **flat**. Surfaces separate by a 1px border and a one-step tonal shift, not by shadow. Selection, focus and "you are here" are hard offset **rings or rules**, never a glow.

### Shadow Vocabulary
- **Tooltip ambient** (`box-shadow: 0 6px 20px rgba(0,0,0,0.18)`): the only true drop shadow. `#tooltip` genuinely floats free and follows the cursor.
- **Popover shadow** (`0 8px 28px rgba(0,0,0,0.18)`): the country filter and the region tree — menus that overlay content and need a lift off it. Not elevation on a resting surface.
- **Panel scrim** (`box-shadow: 0 0 0 100vmax rgba(0,0,0,0.22)` on `#panel.open`): dims the board behind the side panel without blocking clicks. Dropped on mobile (the sheet is full-screen).
- **Marker rings** (`inset 0 0 0 1px currentColor, inset 0 0 0 3px var(--cheapest)` and heavier for the board best): not elevation — a spread inset that reads as a mark on the cheapest cell.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest. Reaching for a `box-shadow` on a card, pane, button, input or list row is wrong — use a 1px border or a tonal step. The tooltip, the two popovers, and the panel scrim are the only sanctioned shadows, and each is a thing that actually floats over content.

**The Ring, Not Glow Rule.** Focus and selection are crisp offset rings/rules (1–5px, often a 1px surface-coloured gap), never a blurred halo. Fare-cell hover and keyboard focus are a 2px ink `outline` at `outline-offset: 1px`; the selected list row is a fill plus a 2px inset ink rule on its leading edge; a list row's keyboard focus is a 2px ink `outline` inset by 2px.

## Shapes

Rounding is gentle and **tracks element size**: `8px` containers (panel elements, tooltip, popovers), `6px` controls (buttons, selects, the boxed destination combobox), `4px` small toggles (day-of-week, locate, widen), `3px` chips and tags, **`0px` fare cells**. The grid is a flush mesh — cells separated by a 1px hairline of canvas (`border-spacing: 1px` on a `separate` table), square-cornered, so a run of same-priced days still reads as distinct cells rather than one smear, without floating like chips.

**Borders are the primary separator:** 1px solid, almost always `hairline`, `axis`, or `gridline`. Nothing uses a border heavier than 1px except the emphasised ink border on a verified cell and the 2px inset rules that mark selection.

**Recurring geometry — the triangular wedge.** Stops are a small right-angled triangle in a cell's top-right corner, built from CSS borders (`border-top` + transparent `border-left`); a bigger wedge means 2+ stops. The same shape appears in the legend. It is the system's one piece of iconographic vocabulary — deliberate, not a decorative side border (detector waiver: `side-tab` on `styles.css`).

## Components

Controls feel **refined and restrained** — quiet, considered, a little soft; state changes are calm, nothing bounces.

### Search bar (`.controls-primary`)
The whole search on one row: **From** (3-letter origin) · **To** (a multi-select region combobox — type to filter countries/regions/continents, or open a checkable tree; empty = anywhere; selection shows as removable tags) · **When** (a month picker plus "Anytime (next 3 months)") · **Trip length** (presets: Weekend … About a month … Flexible; a preset sets the nights range, and Weekend / Long weekend also bias departure to Wed/Thu) · **Travellers** (two small steppers, each captioned "adults" / "kids"). Then Search / Stop and an **Options** disclosure holding everything else (exact dates, exact nights, stops, price cap, preferred days, flight times, result count, the Google-Flights live-pricing toggle) in labelled groups, closed by default.

Fields are **underlines, not boxes**: no fill, a 1px `axis` bottom rule, `4px 2px` padding, an 11px sentence-case label above. Hover darkens the rule to `ink-muted`; focus thickens it to 2px `ink` via an inset shadow (no layout shift). The To combobox is the one boxed field (it holds tags and needs an edge).

### Buttons
- **Shape:** 6px radius, 1px `axis` border, `6px 12px` padding.
- **Secondary (default):** `page` fill, `ink` text. Hover lifts the border to `ink-muted`. A 1px press translate (`translateY(1px)`), because most buttons start work that takes a second to show.
- **Primary (`.primary`):** inverted — `ink` fill, `surface-raised` text. Hover shifts the fill to `ink-secondary` (a filled button has no border to move). `.running` = `opacity 0.75`. `.stale` = fill flips to `marker-yellow` with `ink` text ("a change you made needs a new search") — the one place a button changes colour for state; hover keeps the yellow and takes a dark ring.
- **Small variants:** `.locate` (◎, 12px, `3px 7px`), `.fillbtn` (11px, `3px 8px`, 4px radius — the widen and ‹ All controls), day-of-week toggles (24px squares, 4px radius, `.on` = solid `ink`).
- **Focus:** `outline: none` plus a 1px `ink` ring for chrome buttons; a 2px inset ink outline for list rows and fare cells.

### Ranked list row (`.lrow`)
One destination per row, the whole thing a `<button>`. A two-column grid: **row 1** — city + a muted 11px country, and right-aligned the cheapest fare in Mono with a muted `–€X` ceiling; **row 2** — the cheapest date pair (`Fri 12 Dec → Mon 15 · 3n`) in 11px `ink-secondary`. `8px 8px 9px` padding, a 1px `gridline` bottom rule, no box. Hover = `surface-raised` fill. Selected (`.is-sel`, `aria-current`) = `surface-raised` fill + a 2px inset `ink` rule on the leading edge. No per-row "cheapest" marker — the list is sorted cheapest-first.

### Chips / Tags
- **`.tag`:** hollow — 1px `hairline`, 3px radius, `0 3px`, 11px/600 uppercase, `ink-muted`.
- **`.tag.live`:** text and border to `verified-green`. **`.tag.real`:** to `ink-secondary` / `ink-muted`.
- **`.drift`:** filled `advisory-amber` with `ink` text, 3px radius — a louder badge for "the estimate and the live price disagree".

### The grid pane's card (`.card` inside `.ddetail`)
Not a box — no border, no fill, no radius. It is a flex column filling the pane: a head row (`.card-head`) then the matrix. The head carries the city `h2` (19px), a muted country, the cheapest date pair and price, the drift/`unconfirmed` chip if any, and the controls (◎ locate, `± Nd` widen, and on mobile ‹ All). `flex-wrap` with a zero-height `::after` splits it into a title line and a metadata line with no extra markup.

### Signature Component — the Fare Matrix
- **Cell:** 32×23px desktop / 38×27px mobile, 0px radius, 12px (13px mobile) Mono tabular-nums, centred, 1px transparent border, per-step fill + measured ink (`.q0`…`.q6`). `--cell-w` is a floor — the table distributes the pane's width, so cells measure wider; the grid scrolls sideways for a wide date range.
- **States:** `.priced` (pointer) · `.nodata` (45° hatch on canvas, `hairline` border — "no cached data", *not* expensive; detector waiver `repeating-stripes-gradient`) · `.notasked` (plain, no border — a trip length you did not ask for) · `.void` (return before departure — a faint centred "–") · `.best-here` / `.best-board` (yellow inset rings, weight 600/700) · `.verified` (1px `currentColor` border, weight 600 — a live-priced cell; shows its price even when its trip length is outside the search) · `.excluded` (opacity 0.22 → 0.7 on hover — ruled out by a day/nights constraint but still visible; a verified cell is never dimmed) · `.week-diag` (dotted `axis` left border, 7/14-night trips) · `:hover` / `:focus-visible` (2px `ink` outline).
- **Cross-hair:** hovering a cell washes its column and row `rgba(127,127,127,0.16)` and turns both date headers `ink`/700 on `gridline` — faint on the data, emphatic on the dates. Click to pin.
- **Corner wedge** (`.stopdot`): triangular `currentColor`, `opacity 0.38` (`.many` bigger, 0.6). **Stale dot** (`.staledot`): 3px `advisory-amber` circle, bottom-left.
- **Locate:** opening a destination the first time scrolls its grid to the cheapest cell and pulses the marker ring (`@keyframes locate-flash`, 0.4s × 4); the ◎ button repeats it. Scroll position is then remembered per destination.
- **Keyboard / SR:** interactive cells are `role="button"` with a full `aria-label` (destination, dates, price, stops), a roving `tabindex` (one stop per grid, the cheapest cell), arrow keys between cells, Enter/Space to price one live. `th` cells carry `scope`.

### Detail Panel (`#panel`)
340px, fixed right, full-height. Slides `translateX(100%)` → `none` over `0.16s ease`. 1px `hairline` left border, no shadow (a `100vmax` scrim dims the board behind it, non-blocking). Mobile: 100% width, no border, no scrim — a full sheet with a 44px close control. Contents: a `dl` on `auto / 1fr` (4px 10px gap), the 26px `.big` price, and `.segments` — flight legs indented under a bold sector summary with a 2px `gridline` left rule.

### Tooltip (`#tooltip`)
`position: fixed`, `surface-raised`, 1px `hairline`, 8px radius, `8px 10px`, 12px, `pointer-events: none`, `max-width: 260px`, the one ambient drop shadow. Desktop only.

### Status strip
Between the header and the board: a `flex` column, 13px `ink-secondary`, `max-width: 74ch` on prose lines. The lead line pairs streaming progress (left, `ink`/500) with the fare legend (right — a swatch key: cheap→expensive ramp, the cheapest-cell swatch, the `nodata` hatch, the stops wedge; scoping caveat as a five-word `.legend-scope` with a title tooltip). Below it: `.growing` counts (11px `ink-muted`, tabular), advisory `.hint` lines (6px `advisory-amber` dot then normal-weight text), errors in `error-red`.

### Table view (`.tableview`, toggled by `body.show-table`)
An alternative to the **grid pane only** — the ranked list stays; the table takes the grid's place and shows *that one destination's* priced date pairs. Plain `<table>`, `border-collapse`, hairline row rules, `4px 10px` cells, 13px tabular. Zebra ~3.5% ink wash on even rows, hover ~9%. Numeric columns right-aligned. **Every heading sorts** (`aria-sort` + ↑/↓; same column flips). The sticky header sits flush at the pane's top on an opaque `surface-raised` ground with its own inset bottom rule. The toolbar toggle's label flips Table ⇄ Matrix. Mobile: a full-screen layer, 520px min-width, scrolls sideways.

## Do's and Don'ts

### Do:
- **Do** print the number on anything that also uses colour to encode a value — this ramp is art-directed, not lightness-monotonic, so the printed figure is the primary channel.
- **Do** keep `font-variant-numeric: tabular-nums` on every comparable figure, and keep numerals in Geist Mono via the one selector list in `styles.css`.
- **Do** separate surfaces with a 1px border (`hairline` / `axis` / `gridline`) and the canvas → page → surface-raised tonal steps.
- **Do** use hard offset rings/rules for focus, selection and "you are here"; give the fare cell a 2px `ink` outline on hover and focus.
- **Do** size an element to its content — the grid's 1px gaps and square corners are deliberate.
- **Do** let colour rank *within* the one grid on screen; compare across destinations by the list's fares and cheapest-first order.
- **Do** ship every warning and state with a word or icon, not colour alone; advisory in `advisory-amber`, errors in `error-red`, verified in `verified-green`.
- **Do** keep the warm-paper neutrals — they are the system's character, not an accident.
- **Do** support light and dark equally — every colour a token in all three roots.
- **Do** keep the results in the app shell: the panes scroll, the page does not.

### Don't:
- **Don't** put functional text below 11px, the fare matrix included. There is no sanctioned sub-11px exception any more.
- **Don't** run `ink-muted` on `gridline` — it clears AA on the paper surfaces, not on the mid-grey.
- **Don't** add a `box-shadow` to a card, pane, button, input or list row. Shadows belong to the tooltip, the two popovers, and the panel scrim — things that float over content.
- **Don't** use `marker-yellow` as a fill, a ramp step, a selection background, or a text-selection wash — the cheapest-cell marker only.
- **Don't** introduce a third typeface, and don't put Geist Mono on prose. Geist for chrome, Geist Mono for numerals.
- **Don't** put the app in a centred max-width column; it is full-bleed.
- **Don't** box a destination — a list row is a plain button separated by a 1px `gridline` rule; the grid-pane card has no border, fill, or radius. The city name and the grid bound the content for free.
- **Don't** let the grid pane scroll as a block, or let the page scroll once a board exists — the `.matrix-wrap` and `.dlist` own the only scrollbars (plus the matrix's horizontal one).
- **Don't** hide the matrix or list scrollbars or make them overlay-only; their visibility says there is more.
- **Don't** style an estimate to look as certain as a verified price, or a `nodata` cell to look expensive.
- **Don't** add gradients, hero imagery, urgency messaging, or decorative colour — this is an instrument, not a booking funnel.
- **Don't** animate beyond the sanctioned set (panel slide `0.16s`, chevron rotate, locate pulse, `searching-breathe`, per-destination `card-in` fade, smooth locate-scroll). The global `@media (prefers-reduced-motion: reduce)` block damps all of it; keep new motion inside that guard.
