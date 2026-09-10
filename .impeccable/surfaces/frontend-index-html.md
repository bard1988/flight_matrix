---
version: 1
slug: "frontend-index-html"
primary_target: "frontend/index.html"
related_targets: ["frontend/app.js","frontend/styles.css"]
---

# Surface brief — FlightMatrix app shell (results board)

Scope: the whole web app surface — control bar, ranked destination list, the selected
destination's departure × return fare matrix, cell detail panel, table view, first-run.
Visitor mode: **Operate** (the visitor is completing a task: find the cheapest viable
destination + date pair).

Audience / job: a traveller with loose dates and no fixed destination, scanning several
candidate destinations across a date range at once. Action: open a destination, read its
grid, land on the cheap cell, click through to book.

Constraints that do not move (PRODUCT.md): every priced cell prints its price; fare ramp
stays CVD-safe (OKLCH lightness strictly monotonic cheap→dear, re-validated by
`data/emit_fare_ramp.py`); WCAG 2.1 AA; single shared process (no per-user server state);
estimates never styled as quotes; hatched = "no data", not "expensive"; `--cheapest`
yellow reserved for the cheapest-cell marker only.

Unresolved: whether to swap Geist for a rounded humanist face (Onest) — offered to the
user after first render.

## Direction contract

THESIS: The board is a **fare calendar you read at arm's length**, not a dense instrument
panel — few large cells, price first, one supporting fact, soft colour. It refuses the
airport-solari treatment (32×23 monospace cells, cold grey ground, hairline everything)
that the previous world committed to.

OWN-WORLD: Warm off-white ground (`#f6f4f0`), white raised cards with a soft low shadow
(`0 1px 3px / 0 8px 24px rgba(30,25,20,.06)`), 12–16px radii on cards and 8–10px on
cells. One blue accent (`#2f6be0`) for the active state and the primary CTA; a soft-tint
fare ramp (light saturated green → cream → peach → terracotta) whose OKLCH lightness still
descends monotonically. Geist across the board; prices in Geist with `tabular-nums`,
large and semibold. Pill-shaped filter toggles. Nothing is boxed in hairlines; separation
is shadow + tonal step + generous whitespace.

STORY: The visitor sees a friendly grid of prices, greenest = cheapest for this
destination, each cell also telling them the trip length. They scan, pick a cell, and a
detail card gives them the flight and a clear "View deal" button.

FIRST VIEWPORT: Control bar (rounded search field group + pill filters) across the top on
a white raised strip. Below, the two-pane board: left, a ~300px ranked list of rounded
destination rows (city + country, big fare, cheapest date pair), cheapest first, the
selected one on a tinted blue-wash surface; right, the selected destination's fare matrix
filling the pane — ~5 departure columns × ~5 return rows visible at rest, each cell a
rounded tinted tile ~104×72px showing the price (18px semibold) over the trip length
("5 nights", 11px muted), the rest of the widened grid reachable by scroll with the date
axes pinned. Primary action = clicking a cell → detail panel with a blue "View deal".

FORM: A fare-calendar reskin of the existing master-detail shell — pinned by the user's
reference mockup, not dealt by the roll. No seed key (brief-pinned direction; concept
tournament skipped per new-work §3 collision rule).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish
review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
