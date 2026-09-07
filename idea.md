# Ideas / backlog

Things worth doing, not yet scheduled.

---

## Feature backlog

| # | Feature | Size | Status |
|---|---|---|---|
| 1 | **Filter by airline** — bundled airline-name DB, refreshed periodically (and/or from what searches return) | M | todo |
| 9 | **Filter by region** — collapsible continent → subregion → country tree | M–L | **backend done** (2026-09-07); tree UI todo |
| 11 | **Kids' ages** — per-child age (infant/child buckets), not just a count; changes the price. Must propagate to providers + `party_key` cache key + child-factor scaling | M–L | todo |
| 6 | **Cabin class** selector (economy / premium / business) — thread through provider → API → UI | M | todo |
| 4 | **One search model: period + trip length** — drop the "Dates mean" dropdown | M | **phase 1 done** (2026-09-07: dropdown gone, range default); anchors code removal + widen-as-extend = phase 2 |
| 7 | **Mobile: more compact** | M | todo |
| 7.1 | — passengers shown in the bar, not behind Options | S | todo |
| 7.2 | — denser matrices on small screens | S | todo |
| 7.3 | — cell-detail panel: the ✕ close is mispositioned (far right); reconsider full-screen panel on mobile | S | todo |
| 10 | **Show the airport's city** wherever only the IATA code appears | S | **backend done** (2026-09-07: `describe()` resolves airport→city via `city_code`); panel-leg display todo |
| 8 | **Design pass** — use the `design` skill / a proper design system | L | in progress |

### Notes on specific items

### #4 — One search model (spec, decided)

**Rationale.** The two things people can always state about a trip are *roughly how
long* ("a week off", "a long weekend") and *roughly when* ("mid-November"). That is
exactly range mode's two inputs. Anchors asks for two specific dates instead, which
forces the user to translate "a week around mid-Nov" into "depart the 14th, return the
21st" — an extra step that also throws away the nights figure, which was the real
constraint. Range can express every anchors case (narrow the period, set a nights
band); anchors cannot express range ("two dates 56 days apart can only describe
~56-night trips"). So: **one model, nights-first.**

**The good news:** the range engine is already fully built and shipping —
`SearchRequest.range_axes()`, `nights_span()`, `date_axes()`, and the range branch of
`KiwiProvider.fill_matrix` / Travelpayouts / demo. #4 is mostly deletion + relabeling.

**Backend (`models.py`, `board.py`, `app.py`):**
- `date_mode` defaults to `"range"` (keep the field for one release for request
  back-compat, then remove). `is_range` / the `anchors` branches in `date_axes`,
  `fill_matrix`, `_prune_to_nights`, `_coverage_note` go away.
- `nights_span()` when min/max aren't given: today defaults to `2..4`. Change to derive
  from the two date fields — `n = (travel_until - travel_from)` clamped, band `n±2` — or
  just require the nights field in the UI so it's always sent.
- `depart_window`/`return_window` / `window(anchor, days)` become dead code; the
  `window_days` "± N days" widen-on-scroll becomes "extend the period" (already how
  range widening works).

**Frontend (`index.html`, `app.js`):**
- Delete the `#datemode` `<select>` and `syncDateMode()`.
- Relabel the two date fields: **"Travel from"** / **"Travel until"** (a period), always.
- Make **Nights** (`nmin`/`nmax`) a first-class visible field, not tucked in the
  advanced area — it's now the primary constraint. Default e.g. `5`–`9`.
- `searchSignature()`: nights always counts (drop the "only in range mode" branch).
- Default values: travel from ≈ today+30, travel until ≈ today+75, nights 5–9.
- The "impossible constraint" warning (anchors + short-nights) is no longer possible —
  remove it.

**Sequencing:** backend is safe now (design-independent). Frontend overlaps the
`/impeccable` design pass (it owns the control bar) — do it right after, or hand the
date-field change to that pass.
- **#1 airline DB.** `data/airlines_seen.py` already collects airline names. Filtering can
  be client-side on already-fetched cells (each cell carries `airline`); the search-time
  filter (spend the destination budget inside the filter) is the harder half.

- **#13 Kiwi rate limit — mostly handled by #14 (below).** Root cause is the Oracle
  datacenter IP; Kiwi 403-blocks it far more than a residential one. The free answer is
  #14 (fast graceful failover to Travelpayouts + live cross-check). Two dormant tools
  remain if we ever want real Kiwi coverage back:
  - **Google price-graph board (Lever 1)** — spiked 2026-09-07: Google prices real party
    totals ✓, but the batched calendar call needs the `SNlM0e` XSRF token Google
    withholds from anonymous clients → fragile reverse-engineering. Point-query-only
    board is ~15-20 min for 20 destinations. Parked.
  - **`FM_KIWI_PROXY` + `FM_KIWI_PROXY_BUDGET_MB`** (built, dormant) — routes only
    Kiwi's calls through a proxy, counts wire bytes to `data/kiwi_proxy_usage.json`,
    drops to direct when the budget is spent or the proxy fails (HTTP 407 etc.).
    `/api/health.kiwi_proxy` shows usage. No free residential proxy that beats Fastly
    exists without a home connection; a $5 one-time IPRoyal top-up is the cheap option
    if #14 isn't good enough.
- **#11 kids' ages.** `children` is a bare count today. Providers price by age bucket
  (infant on lap / infant in seat / child). Needs: per-child ages in the UI →
  `SearchRequest` → each provider (Kiwi `infants`, Google `infants_in_seat` /
  `infants_on_lap`, Travelpayouts) → `party_key` (it's part of the cache key, so a
  wrong key serves a wrong-priced grid) → the `FM_CHILD_FACTOR` estimate scaling.
- **#10 airport city.** The card head already shows the city; the gap is everywhere
  else a raw IATA code surfaces — the flight-details panel legs, the tooltip, the table
  view, and codes that resolve to an airport (not a city) in `airports.describe()`.

### #9 — Filter by region

**Backend done (2026-09-07):** `data/build_countries.py` → `data/countries.json`
(250 countries: name + continent + subregion, from mledoze/countries + travel
overrides). `airports.py` `country_name()` now worldwide, plus `region_of()` and
`taxonomy()`. `GET /api/regions` serves the tree. `SearchBody.country_codes` →
`board.build` filters candidates at discovery (composes with `destination_filter`,
no cache impact), emits a `region_filtered` event. **Still todo: the tree UI**
(collapsible continent → subregion → country, tri-state checkboxes, post-search
counts, its own field in the control bar) — coordinate with the design pass.

Original spec below.

---

**Its own field**, separate from the `Only destinations` text box. The two complement:
- **Region tree** = structured geography, primarily a *search-time restriction* — the
  destination budget is spent inside the checked continents/regions/countries (e.g.
  "only Italy" → search finds the cheapest Italian cities, not the cheapest anywhere
  then hidden). Also acts as a post-search view filter (un/check to hide/show).
- **`Only destinations` box** = unchanged, free-text narrowing of what's already shown
  (city, code, country substring).

**Data — use the full ISO country list, not the hand-typed 75.** `backend/airports.py`
`COUNTRY_NAMES` is a ~75-entry manual patch (*"the Mediterranean/Europe region this
tool is aimed at"*); the airport feed itself carries only ISO 3166-1 alpha-2 codes with
no names. Ship a complete bundled `alpha-2 → {name, continent, subregion}` table
(~249 rows, ~15 KB, ISO 3166 + UN M49 with travel-taxonomy overrides), have
`country_name()` and the tree derive from it, and drop the partial dict. Codes stay the
internal key; every label shows the full name ("Italy", not "IT").

**Taxonomy (travel-oriented, not strict UN M49):**
- Europe: Western · Northern/Scandinavia · Southern · Eastern & Balkans
- Middle East (Western Asia + Turkey; Cyprus and Egypt are judgment calls)
- Africa: North Africa · Sub-Saharan
- Asia: Caucasus & Central Asia · South & Southeast Asia · East Asia
- Americas: North America · Latin America & Caribbean
- Oceania

**UI:** collapsible "Regions ▾" disclosure in the field (collapsed by default; on
mobile full-width when open). Tree = continent → subregion → country, tri-state
checkboxes (checking a parent toggles children), a count per node. Post-search only
nodes with ≥1 result are shown (~10 countries, not 249); pre-search shows
continents + subregions only.

**Wiring:** add `regions: [...]` (or `country_codes: [...]`) to the search body →
`board.build` → filter candidates by `region_of(country)`. Frontend view-filter reuses
the same map. Phase 1 could ship view-only; phase 2 adds the search-time restriction.

---

## Provider research conclusion (2026-09)

Adding more flight *providers* does not add price data. Kiwi, Travelpayouts/Aviasales
and Google Flights are all **aggregators** over the same pool (GDS + airline NDC + LCC
connectivity). Skyscanner, Kayak, Momondo, FlightAPI.io, ScrapeBadger, SerpApi, Duffel,
etc. repackage that same pool — another API surface, not new routes or lower fares.

The only genuinely additive data is **direct carrier feeds** for airlines the aggregators
miss or misprice. For TLV every candidate is already blocked:

| Carrier | TLV? | API | Verdict |
|---|---|---|---|
| Wizz Air | yes | works, but **per-person fares only**, moving version string, `InvalidProtocol` on repeat | reintroduces the ×N family error; Google fill already returns Wizz as cheapest-cell winner |
| El Al / Arkia / Israir | yes | none usable (WAF / Cloudflare / CMS-only) | dead |
| Ryanair | no | keyless (`ryanair-py`) | zero Israeli airports |
| Transavia | via AMS/ORY | had an open API, now partner-login gated | no longer self-serve |
| Pegasus / AJet / Aegean / flydubai / Air Arabia | yes | each needs individual reverse-engineering, mostly per-person | not worth 5 brittle integrations |

The README's own line settles it: *"The aggregator has the carriers; what we were
missing was itineraries, and that was our parser, not the source."*

So the two levers below are about **capability and reliability of the sources we have**,
not breadth.

---

## Lever 1 — Google Flights as a full board source (price graph)

**What:** today Google Flights is only a per-cell verifier (`backend/providers/google_flights.py`,
used by Fill live and Auto cross-check). Promote it to a first-class board provider
(`FM_BOARD_PROVIDER=google`) that can `discover()` and `fill_matrix()`.

**How:** Google Flights has a keyless **price-graph RPC** — cheapest round-trip per
departure date over a range, for a trip-length band, in one call. Same protobuf
mechanism `fast-flights` already uses for point queries; it just doesn't expose this
message. `krisukox/google-flights-api` (Go) implements it as `GetPriceGraph()` and shows
the protobuf shape. `backend/providers/google_flights.py` already builds and parses
Google Flights protobufs (`_parse_all_itineraries`, `PARSER_VERSION`), so this is an
extension, not a new dependency.

**Why it's the good lever:**
- free, keyless, no new service
- data from the source we already trust for verification
- Google is **not** blocking the Oracle datacenter IP (the live deploy test filled 5
  boards clean) — unlike Kiwi
- gives a Kiwi-style grid fill that isn't rate-limited to death

**Caveats:**
- price graph is departure-date-centric → a full departure×return matrix means one call
  per trip length, i.e. the same "diagonal" approach `backend/providers/kiwi.py` already
  takes
- verify it honours the passenger count (real total, not per-person) — `GetOffers` does;
  confirm the graph message does too
- still Google → a block is possible later. Mitigations: the BrightData / SearchApi hooks
  `fast-flights` v3 added, or a residential proxy.

**Rough shape:**
- new `GoogleFlightsBoardProvider` in `backend/providers/`
- port the price-graph protobuf build from the Go lib into `google_flights.py`
- wire into `board.make_board_provider()` on `FM_BOARD_PROVIDER=google`
- `discover()` can reuse the existing Travelpayouts discovery, or Google Travel Explore
  (SerpApi free tier: 250/mo) if we want it fully off Travelpayouts

---

## Lever 2 — fix Kiwi's datacenter-IP throttling

**What:** Kiwi 403-blocks bursts by IP and the block lasts minutes. From the Oracle VM
this bites harder than from a residential/office IP. Current mitigations
(`backend/providers/kiwi.py`: shared backoff, pacing, cache reuse, diagonal fetch,
Travelpayouts fallback) manage it but cap throughput; the live test took ~5 min for a
5-destination board on the micro.

**Options, cheapest first:**
1. **Run behind a Cloudflare Tunnel from a non-datacenter connection** (home / office
   box) instead of / in addition to the Oracle VM. Residential IP, no open ports.
   `DEPLOY.md` already sketches this as the fallback.
2. **Residential / mobile proxy for outbound Kiwi calls only** — a `FM_KIWI_PROXY` env
   that `KiwiProvider`'s httpx client honours. Cheap residential proxy pools exist; only
   the Kiwi calls need it, not Google or Travelpayouts.
3. **Accept it** and lean on lever 1 (Google board) as the primary, Kiwi as the
   real-totals cross-check on cheapest cells only.

**Note:** the merged-CA hack (`config._ca_bundle()`) is corp-proxy-specific and already
correctly no-ops on the VM; a proxy integration should not resurrect it.

---

## Smaller / maybe

- Migrate Travelpayouts Data API to the Nov-2025 version — the old one stops working
  **2026-06-15**.
- `fast-flights` is pinned `>=2.2` in `requirements.txt` but the code targets the 3.x
  API. Pin it properly (`>=3,<4`) and retest Fill live.
- SerpApi Google Travel Explore (free 250/mo) as a discovery source, to get discovery
  fully off Travelpayouts.

---

## Done features

### #14 — Fast graceful Kiwi -> Travelpayouts failover (2026-09-07)

The board already fell back to Travelpayouts if Kiwi's *discovery* call failed, but a
rate-limited per-destination fill just errored, and Kiwi waited out the 403 for up to
180 s per fill. Now: `FM_KIWI_WAIT_BUDGET` default 180 -> 40, and when a Kiwi
`fill_matrix` throws `ProviderError` mid-board (`board.build`), the rest of the
destinations switch to Travelpayouts and the failed one retries there. Destinations
already filled from Kiwi keep real party totals; the rest are estimates whose cheapest
cells the live Google cross-check still corrects. The `done` event carries `failovers`
plus a note ("N have real totals, M use cached estimates"). Files: `backend/config.py`,
`backend/board.py`. The free answer to #13 — Kiwi when the IP behaves, snappy estimate
fallback when it doesn't, no 5-minute stalls.

### #5 — Green → orange → red colour ramp (2026-09-07)

Replaced the neutral-midpoint diverging ramp with a plain traffic-light scale
(q0 green → q3 orange → q6 red). Green/orange/red is the classic red-green
colour-blind failure, so the ramp's **WCAG luminance is strictly monotonic**
cheap→dear — it still reads as light→dark with hue removed — and every cell still
prints its price. Per-step ink recomputed for contrast. Light + both dark blocks in
`frontend/styles.css`; derivation + CVD check in `data/make_ramp_traffic.py`
(supersedes `make_ramp_diverging.py` / `emit_ramp_css.py`). Middle mirrored pair
(q2 vs q4) is deutan ΔE ~6-7 — weak on hue alone, covered by luminance + labels.

### #2 — Currency without re-search (2026-09-07)

The board is priced in `meta.currency`; the currency dropdown is now a **display**
setting. Changing it converts every shown number (`fmtMoney`, `fmtCompact` route
through `convert()`) using FX rates from a free keyless source
(`open.er-api.com`, localStorage-cached 12h, static `FX_FALLBACK` if offline) and
re-renders — no new search. `'currency'` removed from `SEARCH_INPUTS` so it no longer
marks the board stale. Per-matrix colour ranking is unaffected (invariant under a
linear scale). Verify/fill/details calls still use the fetch currency. Files:
`frontend/app.js`.

### #3 — Stop button (2026-09-07)

`Stop` button appears next to `Search` while a search runs. Clicking it closes the
event stream immediately (whatever destinations rendered stay on screen) and POSTs
`/api/search/{id}/cancel`; the backend polls `should_stop` before discovery and
between destinations, then emits a `done` event with `stopped: true`. Files:
`backend/board.py` (`build(..., should_stop=)`), `backend/app.py`
(`/api/search/{id}/cancel`, `_cancelled`), `frontend/{index.html,app.js}`.
