# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

<!-- Mobile web is a real target (denser matrices, passenger controls in the bar on small
screens); it does not make the platform native. -->

## Users

Today: the author and a handful of colleagues, reached over a corporate network / VPN or a
small internet deployment behind shared basic auth — explicitly not a public launch yet.

Intended: any traveller planning a trip with **loose dates and no fixed destination** —
someone who knows roughly when they can go and how many people are coming, and wants to
know where is cheap and which date pair is cheapest. The public flexible-date fare board is
the stated direction; current distribution is a stepping stone.

Situation being served: comparing several candidate destinations across a range of
departure and return dates at once — "Athens on the 12th–19th vs Rome on the 14th–21st" —
which on existing sites is a dozen-browser-tab exercise because each shows one destination's
date grid at a time.

## Product Purpose

Render **many destinations simultaneously**, each as its own matrix where columns are
departure dates, rows are return dates, and each cell is the combined round-trip price for
that date pair and the given passenger mix. The user scans across destinations and date
pairs together and finds the cheap combination without opening many tabs.

Success: the user identifies the cheapest viable destination + date-pair for their trip,
and understands which numbers are estimates to rank by and which are verified prices to
trust.

## Positioning

Two things a neighbouring product does not do:

1. **Many destinations' flexible-date grids on screen at once.** Google Flights, Kiwi,
   Skyscanner and Momondo all show one destination's date grid at a time; the comparison
   across destinations is left to the user and their tabs.
2. **An explicit two-layer accuracy model, surfaced in the UI.** A fast, wide estimated
   board (Kiwi umbrella GraphQL with real party totals; Travelpayouts as fallback fill) is
   treated as *ranking only*; per-cell Google Flights checks are treated as *truth* and
   fold back in, re-sorting the board. Every card and cell says which layer it is showing
   (`EST` / `KIWI` / `LIVE`, hatched = no data rather than expensive, solid border =
   verified).

## Operating Context

- **Single process, by design.** Search progress streams from an in-memory registry and
  the provider rate limiter is process-global. Never run multiple workers / replicas /
  instances. One shared SQLite cache (WAL mode) serves everyone; one person's filled grid
  is reused for the next.
- **Free / keyless data sources under rate limits.** `fast-flights` (Google Flights) needs
  no key; Travelpayouts needs a free token; Kiwi's endpoint is open. Kiwi 403-throttles
  bursts by IP, worse from a datacenter IP, and that pacing lock is the throughput ceiling
  (a 20-destination board ≈ 300 paced provider calls ≈ 4–5 minutes).
- **Booking-horizon ceiling.** Coverage is search-driven and collapses with distance:
  roughly useful inside ~2 months, close to useless past ~4. The board warns when a window
  is far enough out to be sparse.
- **Deployment.** Local `run.py` (binds 127.0.0.1); `serve.cmd` for LAN; an Oracle
  "Always Free" micro VM + Caddy (single shared username/password) for the small internet
  deployment. DNS currently points at **flightmatrix**.
- **This machine's corporate proxy** re-signs some hosts with an internal CA; a merged CA
  bundle is resolved at runtime. It correctly no-ops off the corporate network.

## Capabilities and Constraints

Capabilities (all present in the current build):

- Search by an approximate departure date, an approximate return date and a passenger mix
  (adults + children).
- **Two date interpretations:** "around these dates" (each field an anchor ±window, full
  departure × return grid) and "anywhere in this range" (the fields bound a period, a
  Nights box sets trip length, priced cells form a diagonal band). Layout stays
  departure × return in both.
- Per-matrix **rank** colour scale (each card runs cheapest→dearest over its own cells;
  colour does not compare across cards). Cheapest cell per card ringed; board-wide cheapest
  marked more strongly.
- Grids are independent scroll viewports with pinned date headers; window starts at ±7
  days and **widens on demand** (per-card button, or a deliberate past-the-edge scroll
  gesture) because widening costs live API calls.
- Click any cell to price it live and fetch both legs (times, flight numbers, carriers,
  stops, duration), in parallel with a Google cross-check; works at any horizon.
- Filters: destination / country (pre-search restricts the search itself; post-search
  narrows the view); depart-between / return-between time windows (**search parameters** —
  they reprice); day-of-week + min/max nights (instant view recompute — colour, per-card
  cheapest and board order all recompute over matching cells); nonstop only.
- Currency is a **display** setting — converts every shown number via a free keyless FX
  source, no re-search; per-matrix ranking is unaffected.
- Table view (every priced cell, sortable, cheapest first). Stop button during a search.
  Booking deep links carry passenger counts and the nonstop flag, not just dates.
- Auto cross-check toggle (on by default) re-prices cheapest cells in the background.

Constraints future work must respect:

- **No authentication** in the app itself; anyone who can route to the host can search.
- Estimated board prices are **measurably optimistic** (checked live: cheapest-cell
  estimates ran ~+30–60% mean vs verified, individual cells −10% to +200%), so the board is
  a ranking instrument, not a price quote. Do not present estimates as firm prices.
- A missing cell is **hatched and excluded from the colour scale** — it means "no cached
  data", never "expensive".
- Cells below the diagonal (return before departure) are blank.

Terminology: *board* (the whole set of destination cards), *matrix* / *card* (one
destination's grid), *cell* (one departure × return date pair), *headline price* (a card's
cheapest known price), *fill* (price a whole grid live), *cross-check* / *verify* (re-price
on Google Flights), *anchors mode* vs *range mode*, *EST* / `KIWI` / *LIVE*.

## Brand Commitments

- **Name is undecided.** "SkyMatrix" is used throughout `README.md` and the code; the live
  DNS says **flightmatrix**; the repo is `flight_matrix`. Future work must not assume one
  until the user picks.
- **Voice** (established in the README, treated as the working voice, not formally locked):
  plain, precise, measurement-led, and candid about the product's limits — it states error
  bars and horizon ceilings rather than implying false precision.
- No logo, wordmark, illustration, or colour identity has been committed. The existing
  green→red fare ramp is a data-encoding decision (below), not a brand palette.

## Evidence on Hand

- `README.md` — extensive, with **measured** benchmark tables: source coverage vs
  booking horizon, an estimate-vs-verified error study, per-mode fetch costs, and colour
  ramp ΔE measurements under simulated colour vision deficiency. Reproducible via scripts
  in `data/` (`coverage.py`, `coverage_horizon.py`, `estimate_error.py`,
  `check_diverging_cvd.py`, `emit_ramp_css.py`, …).
- `idea.md` — feature backlog and provider research conclusions (adding more aggregators
  adds no new price data).
- `DEPLOY.md` — the Oracle VM deployment procedure and its baked-in constraints.
- `graphify-out/` — a prebuilt knowledge graph of the repo's documentation.
- **No** customers, testimonials, press, usage numbers, or partnerships exist. Future work
  must not fabricate them or imply a user base.

## Product Principles

1. **Ranking, not truth.** The board estimates and orders; the click verifies. Every
   surface must make clear which the user is looking at, and never let an estimate read as
   a quote.
2. **Show the real calendar shape.** Keep the departure × return structure even when the
   data is sparse; empty and hatched cells are information (trip lengths not asked for; no
   cached data), not clutter to compact away.
3. **Honest about limits.** Surface coverage and horizon warnings, error context, and
   source labels rather than presenting a clean number that isn't earned.
4. **Design within one shared process.** No feature may assume horizontal scale, per-user
   state on the server, background workers, or unthrottled provider access.
5. **Colour is a secondary channel.** Every value must be legible without it — price text
   on every cell, a full table view, and a fare ramp that survives loss of hue.

## Accessibility & Inclusion

- Target **WCAG 2.1 AA** for the interface overall.
- The fare ramp must stay **distinguishable under red–green colour vision deficiency**. The
  current diverging ramp uses deliberately asymmetric arm lightness (dark green arm, light
  red arm) so cheap vs dear reads by lightness alone; verified with the Machado–Oliveira–
  Fernandes model at severity 1.0 via `data/check_diverging_cvd.py`. Regenerate with
  `data/emit_ramp_css.py` and re-run the CVD check after any ramp change.
- **Colour is never the sole carrier of price meaning:** every cell carries a visible price
  label (minimum measured label contrast 4.8:1) and the table view lists every value.
- Yellow is reserved for the cheapest-cell markers and must never appear as a ramp fill, so
  the marker cannot be read as a price level.
