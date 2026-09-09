---
name: FlightMatrix
description: A flexible-date, any-destination fare board - a ranked list of destinations beside the selected one's departure x return price grid
colors:
  ink: "#12171d"
  ink-secondary: "#48525c"
  ink-muted: "#5f6b7b"
  ink-on-fill: "#12171d"
  ink-flipped: "#fbfcfd"
  ink-on-warm: "#12171d"
  surface-raised: "#fbfcfd"
  surface-page: "#f1f4f6"
  surface-canvas: "#e8ecf0"
  gridline: "#d5dbe1"
  axis: "#b0b9c3"
  hairline: "rgba(18, 23, 29, 0.12)"
  hatch: "rgba(18, 23, 29, 0.05)"
  marker-yellow: "#f2b705"
  verified-green: "#097c09"
  error-red: "#c0261f"
  advisory-amber: "#fab219"
  fare-0: "#0f9246"
  fare-1: "#7ebb42"
  fare-2: "#fdcb08"
  fare-3: "#f68e1f"
  fare-4: "#ef4723"
  fare-5: "#bc1f26"
  fare-6: "#7f0a13"
  ink-dark: "#f2f5f8"
  ink-secondary-dark: "#b4bec9"
  ink-muted-dark: "#8b96a3"
  surface-raised-dark: "#161b21"
  surface-page-dark: "#0b0e12"
  gridline-dark: "#242b33"
  axis-dark: "#323b45"
  hairline-dark: "rgba(242, 245, 248, 0.12)"
  hatch-dark: "rgba(242, 245, 248, 0.06)"
  marker-yellow-dark: "#ffcf33"
  verified-green-dark: "#0ca30c"
  error-red-dark: "#ff8078"
typography:
  display:
    fontFamily: "Geist, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.15
  headline:
    fontFamily: "Geist, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.2
  title:
    fontFamily: "Geist, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Geist, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Geist, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.25
  cell:
    fontFamily: "Geist Mono, ui-monospace, 'SF Mono', 'Cascadia Mono', monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "18px"
    fontFeature: "tabular-nums"
  input-touch:
    fontFamily: "Geist, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.2
rounded:
  none: "0px"
  xs: "3px"
  sm: "4px"
  swatch: "5px"
  md: "6px"
  lg: "8px"
  full: "50%"
spacing:
  hair: "1px"
  xs: "3px"
  sm: "4px"
  md: "8px"
  lg: "12px"
  xl: "14px"
  xxl: "20px"
  section: "24px"
  page: "40px"
components:
  cell-fare:
    typography: "{typography.cell}"
    rounded: "{rounded.none}"
    width: "32px"
    height: "23px"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ink-flipped}"
    rounded: "{rounded.md}"
    padding: "8px 18px"
    typography: "{typography.body}"
  button-primary-touch:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ink-flipped}"
    rounded: "{rounded.md}"
    padding: "11px 18px"
    height: "44px"
    typography: "{typography.body}"
  button-quiet:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.md}"
    padding: "3px 9px"
    typography: "{typography.label}"
  list-row:
    backgroundColor: "{colors.surface-canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "8px 8px 9px"
  list-row-selected:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "8px 8px 9px"
  input-field:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "6px 8px"
    typography: "{typography.body}"
  input-field-touch:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "9px 10px"
    height: "44px"
    typography: "{typography.input-touch}"
---

# Design System: FlightMatrix

## Overview

**Creative North Star: "The Departures Board"**

FlightMatrix looks like the analog board in an airport concourse: tabular, glanceable, numbers first, and stripped of decoration. Its job is to get out of the way of a dense grid of prices so the eye can scan across departure and return dates and land on the cheap one. Every element is sized to the information it carries - a fare cell is 32x23px because that is what a four-figure price needs, not a pixel more - and the chrome around the grid is deliberately quiet: hairline borders, a cool grey ground, one workhorse typeface doing all the hierarchy by weight and size. The ground is cold on purpose. A departures board is a backlit instrument in a terminal, not paper on a desk, so the only warm thing on screen is the fare ramp itself.

The stance is **a quiet instrument, explicitly not a consumer travel site**. No hero images, no gradients, no urgency banners, no "1 seat left" theatre, no decorative colour. The one place colour is loud - the green to red fare heatmap - is load-bearing data, and even there the number is always printed on the cell so colour is never the only signal. The voice is candid about the product's limits (estimates are a ranking, not a quote; a hatched cell means "no cached data", not "expensive") and the design carries that honesty: states are labelled in words, warnings ship with text, nothing is styled to look more certain than it is.

**The composition is master-detail, in a full-viewport app shell.** Once a search returns, the results take over the whole screen and the page itself stops scrolling. On the left, a fixed-width **ranked list** - one tight row per destination, cheapest first, each row carrying the essence of that destination's grid. On the right, the **one selected destination's full departure x return grid**, filling its pane. The two panes scroll independently: running down the list never moves the grid. On a phone the list is the whole screen and the grid slides in over it as a fixed layer.

Because the board now previews every destination from a single discovery call and fills the grids behind it, the detail pane has two states beyond the settled one. **Selected, priced, but not yet gridded** is a real card with a real heading and a real way back, never a bare sentence. **Filling** is the grid painting a calendar column at a time as each provider call lands, so the matrix is visibly being built rather than appearing whole after a wait. The card's headline fare and date pair update live as cheaper cells arrive; its position in the ranked list does not, because a row that climbs while you are reading it is worse than a number that settles.

Motion is minimal - a panel slide, a locate pulse, a slow "searching" breathe, a card fade-in as each destination streams. Surfaces are flat.

**Key Characteristics:**
- Numbers-first: tabular figures everywhere comparison happens; the grid is the hero.
- Master-detail: a ranked list you scan, one grid you study. Independent scroll regions in a viewport-filling shell.
- Two families (Geist for chrome, Geist Mono for every numeral), one cool-neutral palette, hairline separation.
- Flat by default: depth is a 1px border or a tonal step, not a shadow.
- Colour is a second channel, never the only one; yellow is reserved for the "cheapest" marker.
- Honest states: labelled in words, never over-styled for false confidence.
- Light and dark are equal citizens (system-following, with a manual override).
- Every layer that covers the screen carries its own way out.

## Colors

A cool near-monochrome - grey glass, blue-black ink, cold greys - with colour admitted only where it carries meaning: the fare heatmap, the reserved "cheapest" yellow, and three small status hues. The neutrals were warm paper (a `#f4f3ef` cream under a `#0b0b0b` tinted near-black) until the board's own vernacular won the argument: those two values are the exact pair generated interfaces default to, and neither belongs on an instrument. Every colour is a CSS custom property defined in all three roots (`:root`, `@media (prefers-color-scheme: dark)`, `:root[data-theme='dark']`).

### Primary
- **Marker Yellow** (`#f2b705` light / `#ffcf33` dark): the cheapest-cell marker, and nothing else.

### Neutral
- **Ink** (`#12171d` / `#f2f5f8`): primary text, focus rings, selection rules.
- **Ink Secondary** (`#48525c` / `#b4bec9`): supporting text, list-row detail, the waiting note.
- **Ink Muted** (`#5f6b7b` / `#8b96a3`): labels, captions, disclosure carets.
- **Surface Raised** (`#fbfcfd` / `#161b21`): inputs, popovers, the selected list row.
- **Surface Page** (`#f1f4f6` / `#0b0e12`): the control bar ground.
- **Surface Canvas** (`#e8ecf0` / `#0b0e12`): the app canvas behind the panes.
- **Gridline** (`#d5dbe1` / `#242b33`): hairline separation between rows and cells.
- **Axis** (`#b0b9c3` / `#323b45`): the grid's own date axes and input borders.
- **Hairline** (`rgba(18,23,29,.12)` / `rgba(242,245,248,.12)`): generic borders.
- **Hatch** (`rgba(18,23,29,.05)` / `rgba(242,245,248,.06)`): the no-data cell fill.

### Status
- **Verified Green** (`#097c09` / `#0ca30c`): a price confirmed by a real search.
- **Error Red** (`#c0261f` / `#ff8078`): failures, unbookable pairs.
- **Advisory Amber** (`#fab219`): staleness and rate-limit notices.

### The Fare Ramp
Seven art-directed steps, cheap to expensive, each with its own paired ink token (`--qi0` through `--qi6`) so contrast holds on every step:

`#0f9246` -> `#7ebb42` -> `#fdcb08` -> `#f68e1f` -> `#ef4723` -> `#bc1f26` -> `#7f0a13`

Ink flips to `#fcfcfb` on the last two steps only; the first five carry `#0b0b0b`. These two ramp inks are deliberately NOT the neutral tokens: they are measured against the seven fills, not against the page, so retuning the ground does not touch them. Worst pair is 4.89.

**Ink on warm** (`#12171d`, theme independent) is the text colour for anything sitting on `marker-yellow` or `advisory-amber`. Those fills are the same in both themes, so their ink cannot follow `--text-primary` or it inverts to white on yellow in dark mode.

### Named Rules

**The Colour-Is-Second Rule.** Every priced cell prints its price; the table view lists every value; the fare ramp is never the only carrier of meaning. This ramp trades lightness-monotonicity for exact reference colours, so the printed number is not optional - it is the primary channel and the colour is the accent.

**The Reserved Yellow Rule.** `marker-yellow` marks the cheapest cell only - a ring on the grid's own cheapest cell, a thicker ring-plus-ink-edge on the board-wide cheapest cell. It appears **nowhere** as a fill: not a ramp step, not a selection background, not a text-selection wash. The ranked list needs no yellow of its own - it is sorted cheapest-first, so the board's cheapest destination is always row 1.

**The Per-Matrix Scale Rule.** Heatmap colour ranks date pairs *within the destination on screen*, never across destinations. A green cell on an expensive city can cost more than a red cell on a cheap one. Cross-destination comparison is by the list's fares and its cheapest-first order only - never imply otherwise in copy or legend.

**The Key Follows The Grid Rule.** The colour key is shown only while a grid is actually rendered in the detail pane. Previews mean the pane can be gridless; a ramp legend with nothing on screen using it explains nothing.

## Typography

**Chrome Font:** Geist (with `system-ui`, `-apple-system`, `Segoe UI`, `sans-serif`)
**Numeral Font:** Geist Mono (with `ui-monospace`, `SF Mono`, `Cascadia Mono`, `Segoe UI Mono`, `monospace`)

**Character:** One neutral grotesque doing all the hierarchy by weight and size, paired with its own monospace for every figure. The pairing is unshowy on purpose: the type is a delivery mechanism for numbers, and the numbers are the design.

### Hierarchy

Five prose steps at a ratio of about 1.27, plus two functional exceptions. The ramp used to carry fourteen sizes with five of them inside a 2px band (12 / 12.5 / 13 / 13.5 / 14); steps that close cannot be read as hierarchy, so they were accretion, not a scale.

- **Display** (600, 28px): the verified total in the cell panel; the first-run headline on desktop.
- **Headline** (600, 22px): the first-run headline at <=720px and in the short-viewport branch.
- **Title** (600, 18px): the card headline fare, panel section headings, the primary action on touch.
- **Body** (400, 14px): the document default. UI text, table cells, list-row city, the waiting note.
- **Label** (400, 11px): field labels, tags, hints, legend text, list-row detail, disclosure carets. The floor.

Two exceptions, both functional rather than typographic:

- **Cell** (Geist Mono, 12px / 18px, tabular): the fare matrix, sized to `--cell-w` / `--cell-h` rather than to the scale. 13px on mobile in a 38px cell.
- **Input on touch** (16px): every field at <=720px. This is an iOS workaround, not a type decision: anything under 16px makes Safari zoom the viewport on focus.

### Named Rules

**The 11px Floor Rule.** Functional text is never below 11px, and there is no exception. The two 10px disclosure carets that used to sit under the floor were raised onto it; a caret is not a good enough reason to have a fourteenth size.

**The Sentence Case Rule.** Labels are sentence case with no tracking. Uppercase plus letter-spacing on an 11px label is the single most recognisable piece of generated-interface chrome, and it is harder to read than lower case at that size. The search bar was de-capsed for this reason; the Options group headings, the provenance chip and the flight-times heading followed.
**The Tabular Numbers Rule.** Any number a user might compare, sort, or watch update carries `font-variant-numeric: tabular-nums`: the matrix, every list-row price and range, the panel, and the table view.

**The Two Families Rule.** Geist for chrome, Geist Mono for numerals. No third typeface, and no monospace on prose.

## Layout

**The shell.** `<main>` fills the viewport and the page does not scroll once a board exists; the panes own the only scrollbars.

**The board** is a two-pane split (`.board-split`, CSS Grid `minmax(240px, 300px) / minmax(0, 1fr)`, `flex: 1; min-height: 0`). The list scrolls in its own region; the grid scrolls in `.matrix-wrap` on both axes with the axes pinned.

**Spacing rhythm.** Not tokenised as a scale; the observed vocabulary is 1px (cell gap and hairlines), 3-4px (tight internal), 8px (default gutter), 12-14px (group), 20-24px (section), 40px (layer bottom padding).

**Breakpoints.** Four, and they are not all width:

- **`max-width: 720px`** - the control bar restacks to full-width fields, loses its stickiness, and fields go to 16px.
- **`max-width: 860px`** - master-detail collapses. The list becomes the whole screen; the detail pane becomes a fixed full-bleed layer at `z-index: 60` with the list hidden behind it; the table view does the same. `.detail-back` and `.table-back` appear here and only here.
- **`max-height: 480px`** - the control bar stops being sticky, for landscape phones.
- **`pointer: coarse`** - independent of width. Touch comfort sizing: the theme toggle, the bar's buttons, the traveller steppers, the board-tools controls and every field take a 44px minimum. A landscape phone is 740px wide and still a finger, which is why this keys off the pointer and not the viewport.

### Named Rules

**The Panes Scroll, The Page Does Not Rule.** Once a board exists, `.dlist` and `.matrix-wrap` own the only scrollbars. Never let the grid pane scroll as a block, and never hide the matrix or list scrollbars or make them overlay-only - their visibility says there is more.

**The Escape Hatch Rule.** Any layer that covers the screen carries its own control to dismiss it, inside the layer. At <=860px both the detail pane and the table view are fixed and full-bleed, and each one covers the toolbar control that opened it - so `.detail-back` ("< All") and `.table-back` ("< Board") live inside the layers themselves. A full-screen layer whose only exit is browser-back is a defect.

**The Full-Bleed Rule.** The app is never in a centred max-width column.

## Elevation & Depth

The system is **flat**. Depth is carried by a 1px border (`gridline` / `axis` / `hairline`) and a three-step tonal ladder (`canvas` -> `page` -> `surface-raised`). Shadows exist only for things that genuinely float over content.

### Shadow Vocabulary
- **Tooltip / popover** (`0 6px 20px rgba(0,0,0,.18)`, `0 8px 28px rgba(0,0,0,.18)`): the two popovers and the hover tooltip.
- **Panel scrim** (`0 0 0 100vmax rgba(0,0,0,.22)`): the full-viewport dim behind the cell panel.
- **Cheapest here** (`inset 0 0 0 1px currentColor, inset 0 0 0 3px var(--cheapest)`): the grid's own cheapest cell.
- **Cheapest on the board** (`inset 0 0 0 1px currentColor, inset 0 0 0 4px var(--cheapest), inset 0 0 0 5px currentColor`).
- **Locate flash** (`--flash-from` -> `--flash-to`): the pulse that lands you on a cell.
- **Structural insets** (`inset 0 -1px 0 0 var(--gridline)`, `inset 2px 0 0 0 var(--text-primary)`): sticky-header rule and the selected row's leading edge. These are rules drawn as shadows, not elevation.
- **Row wash** (`inset 0 0 0 999px rgba(127,127,127,.16)`): the table's hover tint.

### Named Rules

**The Flat-By-Default Rule.** Surfaces are flat at rest. Reaching for a `box-shadow` on a card, pane, button, input or list row is wrong - use a 1px border or a tonal step. The tooltip, the two popovers, and the panel scrim are the only sanctioned floating shadows.

**The Ring, Not Glow Rule.** Focus and selection are crisp offset rings and rules (1-5px, often a 1px surface-coloured gap), never a blurred halo. Fare-cell hover and keyboard focus are a 2px ink `outline` at `outline-offset: 1px`.

## Shapes

Square where the data lives, gently rounded where the chrome does.

- **`0px`** - the fare cell. Deliberate: 1px gaps and square corners make the grid read as one surface.
- **`3px`** - the smallest chips and swatches.
- **`4px`** - inputs and fields.
- **`5px`** - the legend swatch strip.
- **`6px`** - buttons, popovers, the quiet toolbar controls.
- **`8px`** - the largest panels and cards.
- **`50%`** - circular status dots only.

**The Square Grid Rule.** The matrix never gets a corner radius. Rounding a fare cell breaks the continuous-surface read the 1px gap is there to create.

## Components

**Ranked list row (`.lrow`).** A plain full-width `<button>`, 8px/9px padding, separated by a 1px `gridline` rule. Two-column grid: city plus country on the left, fare plus ceiling right-aligned, the cheapest date pair underneath in `ink-secondary`. Selected state is `surface-raised` plus a 2px inset ink rule on the leading edge. No border, no radius, no shadow - the name and the rule bound it for free.

**Preview list row.** The same row before its grid arrives. Carries `preview_price` from discovery in the fare slot and the words *"from - finding dates..."* where the date pair goes. It shows no range and no dates, because discovery returns a departure date and a party total but no return date, and a guessed pair is how unbookable prices reached the board once before. Preview prices go through the same per-person division as a filled row, or the list would rank two different quantities against each other.

**Waiting detail card (`.card.is-waiting`).** The detail pane for a selected destination whose grid has not landed. Uses the same `.card` and `.card-head` as a filled card, carries the city name, the price found so far, and the same `.detail-back` control. `role="status"` so a screen reader hears the grid arrive. No skeleton grid: the axes are unknown until the fill returns, and a placeholder of the wrong shape is a worse lie than a sentence.

**Fare cell (`td`).** 32x23px, 12px Geist Mono, tabular, square, 1px gap. Hover and focus are a 2px ink outline. A `nodata` cell is `hatch`, never styled to read as expensive. Cells are exempt from target-size minimums - they are sized by `--cell-w`/`--cell-h` and are the instrument itself.

**Back controls (`.detail-back`, `.table-back`).** `display: none` above 860px; `inline-flex` below it. Same visual treatment as a quiet button. Labels are "< All" and "< Board".

**Board tools.** A quiet strip above the board: count, region filter, currency, per-person toggle, table toggle. Every control clears 24px, and 44px under `pointer: coarse`.

**Inputs.** `surface-raised` on a 1px `axis` border, 4px radius, 6px/8px padding. At <=720px they go full-width at 16px; under `pointer: coarse` they take a 44px minimum height.

### Named Rules

**The Target Floor Rule.** Every interactive control clears **24x24px** (WCAG 2.5.8, AA) on every pointer, and **44x44px** under `pointer: coarse`. The fare matrix is the one documented exception.

**The Honest State Rule.** An estimate is never styled to look as certain as a verified price. Every warning and state ships with a word or an icon, not colour alone.

## Do's and Don'ts

### Do
- **Do** print the number on anything that also uses colour to encode a value - this ramp is art-directed, not lightness-monotonic, so the printed figure is the primary channel.
- **Do** keep `font-variant-numeric: tabular-nums` on every comparable figure, and keep numerals in Geist Mono.
- **Do** separate surfaces with a 1px border and the canvas -> page -> surface-raised tonal steps.
- **Do** use hard offset rings and rules for focus, selection and "you are here".
- **Do** size an element to its content - the grid's 1px gaps and square corners are deliberate.
- **Do** let colour rank *within* the one grid on screen; compare across destinations by the list's order.
- **Do** ship every warning and state with a word or icon, not colour alone.
- **Do** give any full-screen layer its own dismiss control, inside the layer.
- **Do** keep the neutrals cold. The warmth on screen belongs to the fare ramp and nothing else.
- **Do** support light and dark equally - every colour a token in all three roots.
- **Do** keep the results in the app shell: the panes scroll, the page does not.

### Don't
- **Don't** put functional text below 11px. The only 10px values are the two disclosure carets.
- **Don't** run `ink-muted` on `gridline` - it clears AA on the paper surfaces, not on the mid-grey.
- **Don't** add a `box-shadow` to a card, pane, button, input or list row.
- **Don't** use `marker-yellow` as a fill, a ramp step, a selection background, or a text-selection wash.
- **Don't** introduce a third typeface, and don't put Geist Mono on prose.
- **Don't** put the app in a centred max-width column; it is full-bleed.
- **Don't** box a destination - a list row is a plain button separated by a 1px rule.
- **Don't** let the grid pane scroll as a block, or let the page scroll once a board exists.
- **Don't** hide the matrix or list scrollbars or make them overlay-only.
- **Don't** style an estimate to look as certain as a verified price, or a `nodata` cell to look expensive.
- **Don't** show a price without the dates behind it unless you say so in words, as the preview row does.
- **Don't** shrink a control below 24px on any pointer, or below 44px on a coarse one.
- **Don't** add gradients, hero imagery, urgency messaging, or decorative colour - this is an instrument, not a booking funnel.
- **Don't** animate beyond the sanctioned set (panel slide `0.16s`, chevron rotate, locate pulse, `searching-breathe`, per-destination `card-in` fade, smooth locate-scroll), and keep new motion inside the `prefers-reduced-motion` guard.
