# Ideas / backlog

Things worth doing, not yet scheduled.

---

## Feature backlog

| # | Feature | Size | Status |
|---|---|---|---|
| 1 | **Filter by airline** — bundled airline-name DB, refreshed periodically (and/or from what searches return) | M | todo |
| 9 | **Filter by region** — collapsible continent → subregion → country tree | M–L | **done** (2026-09-08: tree UI in the Advanced panel) |
| 9.1 | **Airport / city leaves in the region tree** — a fourth level under each country: pick a specific airport or city, not just the whole country. | M | **mostly covered** (2026-09-10, 320b316) — the destination combobox typeahead (`search_places` → `/api/places`) already resolves a city/airport by name or IATA, and `destination_codes` is wired through the board (filters candidates, seeds discovery for a picked airport the board missed, forces it into the grid). Residual, both niche: (a) *browsing* to an airport by expanding the tree rather than searching; (b) non-hub airports — the typeahead caps at scheduled large/medium hubs. Revisit only if either need turns out to be real. |
| 11 | **Kids' ages** — per-child age (infant/child buckets), not just a count; changes the price. Must propagate to providers + `party_key` cache key + child-factor scaling | M–L | todo |
| 6 | **Cabin class** selector (economy / premium / business) — thread through provider → API → UI | M | todo |
| 4 | **One search model: period + trip length** — drop the "Dates mean" dropdown | M | **done** (2026-09-07/08: dropdown gone, range default; anchors plumbing removed + widen reworked for the period model by the redesign pass) |
| 7 | **Mobile: more compact** | M | mostly addressed by the 2026-09-09/10 responsive audit + mobile-sheet rework + consumer reskin (84fc501, 7c0fe2e, 5cf0328, 0585774). No standing sub-items left. |
| 7.1 | — passengers shown in the bar, not behind Options | S | **done** (`field-pax` is a first-class field in the primary control bar; 50%-width on mobile. The post-search folded summary omits the pax count by design — 7c0fe2e.) |
| 7.2 | — denser matrices on small screens | S | **dropped** (2026-09-10) — the reskin deliberately went the other way ("enlarged pastel matrix", 0585774). Revisit only as a concrete "the big cells cost too much scrolling on a phone" complaint. |
| 7.3 | — cell-detail panel: the ✕ close is mispositioned (far right); reconsider full-screen panel on mobile | S | **done** (2026-09-10) — the ✕ sits correctly now (confirmed on device); panel is z-70 above the grid layers (7c0fe2e) with the current design system. Optional nicety left: no tap-outside / swipe-down to dismiss on mobile (scrim is off) — not a bug. |
| 10 | **Show the airport's city** wherever only the IATA code appears | S | **done** (2026-09-10: `/api/details` legs carry `from_city`/`to_city` via `_name_leg_airports`; the panel shows the city with the IATA code as a dimmed suffix, legs wrap on a narrow sheet. Tooltip + table already showed the city) |
| 8 | **Design pass** — use the `design` skill / a proper design system | L | in progress |
| 15 | **Discovery coverage — the whole world, not just short-haul** — Kiwi's `returnOnePerCityItineraries` for TLV returns ~160 nearby cities and nothing long-haul (no sub-Saharan Africa, thin on Asia / S. America), so "To: Africa" yields only Marrakesh. Plan of record in **Lever 3**. **15.0 + 15A + 15.1 shipped** (2026-09-10) — the coverage gap that opened this item is closed. **15C** (Google price-graph board) is the only remaining sub-item and is **deferred** (see Lever 3). | L | **done for coverage** (15.0 + 15A + 15.1); 15C deferred |
| 15.0 | **OurAirports data** — replace the Travelpayouts airport dump with OurAirports (`type`, `scheduled_service`, lat/long, country). Prerequisite for 15A, 15C and #9.1. `data/build_airports.py`, same pattern as `build_countries.py`. | S–M | **done** (2026-09-10, 7fe50c9: `data/build_airports.py` merges OurAirports + Travelpayouts metro codes → `data/airports.v3.json`; `backend/airports.py` reads v3) |
| 15A | **Seed discovery from the curated list** — when a region/destination filter is set and the live board returns few/none inside it, run our own discovery: OurAirports region universe → shortlist by `type`/scheduled_service → **cheap per-airport price probe** to find what actually flies from the origin → fill the survivors cheapest-first via the existing `fill_matrix`. Stepping stone to 15C. | M | **done** (2026-09-10: `_seed_candidates` in `board.py`, probes with Google Flights (71ffb16) not the TP cache, honours the nights range (6b65257), a failed probe skips that airport (ef15eba); emits `region_seeding` / `region_seeded`) |
| 15C | **Google price-graph board provider** (was "Lever 1") — promote `google_flights.py` to a first-class board provider with `discover()` + `fill_matrix()` via the keyless price-graph RPC. Google isn't IP-blocking the VM and returns real party totals (2026-09-07 spike). **Blocked:** the batched call needs the `SNlM0e` XSRF token Google withholds from anonymous clients; point-query fallback measured ~15–20 min/20 dests. Needs a spike before committing. Endgame, not near-term. | L | spike — **deferred 2026-09-10** (coverage gap closed by 15.0/15A/15.1; revisit on latency complaints or a wider launch — see Lever 3) |
| 15.1 | — Egypt (Sharm, Hurghada, Cairo) is classified `Asia / Middle East` in `data/build_countries.py`, so the **Africa** filter excludes the one well-connected part of Africa from TLV. Decide: move Egypt to `Africa / Northern Africa`, or surface it under both. | S | todo |

### Notes on specific items

### Search bar: back to explicit dates (2026-09-10)

The "When" preset dropdown ("Anytime (next 3 months)" / a month name) that fronted the
two date fields is gone. **"Travel from" and "Travel until" are now the actual date
inputs, in the primary bar** — the preset only ever wrote to those fields, and picking a
real window is clearer than translating a month label. "Trip length" (nights preset)
stays in the bar; Options keeps the raw Nights min/max. Files: `frontend/index.html`,
`app.js` (dropped `buildWhenOptions`/`applyWhen`, `setDefaultDates` fills only what a
shared URL left blank), `styles.css`.

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
  - **Google price-graph board (#15C)** — spiked 2026-09-07: Google prices real party
    totals ✓, but the batched calendar call needs the `SNlM0e` XSRF token Google
    withholds from anonymous clients → fragile reverse-engineering. Point-query-only
    board is ~15-20 min for 20 destinations. Parked; see Lever 3 / #15C.
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
| Wizz Air | yes | works: version scraped+cached, per-person fare scaled, fresh client per call | **wired in** (`providers/wizz.py`) — the aggregators thin for small routes far out (TLV→Iași 7mo empty everywhere, Wizz selling it); map feeds discovery, `timetable` fills the gap |
| Ryanair | no (from IL) | keyless `farfnd` + `searchWidget/routes`, no cookies | **wired in** (`providers/ryanair.py`) — zero IL routes, but "From" is any airport now; from a Ryanair base it's most of the board |
| El Al / Arkia / Israir | yes | none usable (WAF / Cloudflare / CMS-only) | dead |
| Pegasus / Air Arabia / AJet / easyJet / flydubai | yes | not yet probed past guessed endpoints (`data/probe_lccs.py`); several look bot-walled | candidates — each needs browser recon |
| Transavia | via AMS/ORY | had an open API, now partner-login gated | no longer self-serve |
| Pegasus / AJet / Aegean / flydubai / Air Arabia | yes | each needs individual reverse-engineering, mostly per-person | not worth 5 brittle integrations |

The README's own line settles it: *"The aggregator has the carriers; what we were
missing was itineraries, and that was our parser, not the source."*

So the levers below are about **capability and reliability of the sources we have**, not
breadth — Lever 3 (discovery coverage) is the plan of record.

---

## Lever 3 — discovery coverage: the whole world, not just short-haul (PLAN OF RECORD)

**The shortcoming (verified 2026-09-09, live).** A TLV → "Africa" search returns
**Marrakesh only**. It is a *discovery* failure, not a data or filtering failure:

- Kiwi and Travelpayouts can both price a TLV→Nairobi grid perfectly well **if you name
  the route** — `fill_matrix` is route-by-route and works. What fails is the "where can I
  go from TLV?" question.
- Kiwi's `returnOnePerCityItineraries` for TLV returns ~160 destinations, effectively all
  Europe / Caucasus / Gulf. The only African city in it is `RAK`. Nairobi, Zanzibar,
  Addis, Johannesburg, Cape Town — 1–2-stop long-haul — are simply absent, so
  `board.build`'s region filter has nothing to keep (`matched: 0` → `done` "Nothing
  reachable from here is in the regions you picked").
- Travelpayouts discovery (`prices_for_dates`, no `destination`) is a cache of what
  Aviasales users recently searched — broader than Kiwi but skewed the same Euro-heavy
  way, and not live.
- Adding a third aggregator buys nothing (see the provider-research conclusion above:
  Kiwi / TP / Google / Skyscanner / Kayak all resell the same GDS+NDC+LCC pool). The
  missing piece is **a better list of candidate destinations to hand to discovery.**

**Egypt sub-issue (#15.1).** Egypt *does* come back from Kiwi (`CAI`, `HRG`, `SSH`) but
is tagged `Asia / Middle East` in `data/build_countries.py`, so the **Africa** checkbox
never includes it. Cheap independent fix; decide move-vs-dual-list.

### Steps, in order

> **Status (2026-09-10): 15.0 and 15A are shipped.** `airports.v3.json` is built from
> OurAirports (`data/build_airports.py`); `board._seed_candidates` runs the universe →
> shortlist → Google-Flights probe → fill funnel whenever a region/destination filter is
> set and the live board comes back short. Left to do: **15.1** (Egypt) and **15C** (spike).
> The step descriptions below are kept as the design record.

**15.0 — OurAirports data (prerequisite).** `S–M`
Replace `data/airports.v2.json` (Travelpayouts dump: 10.5k airports, no hub signal) with
[OurAirports](https://ourairports.com/data/) — same worldwide coverage **plus** a `type`
field (`large_airport` / `medium_airport` / `small_airport`), a `scheduled_service`
flag, lat/long, and ISO country. The list was never the gap; the *ranking* was — Kenya
alone has ~39 airports and discovery can only price ~20. `type` + `scheduled_service`
give us that ranking. New `data/build_airports.py`, same pattern as `build_countries.py`;
`backend/airports.py` reads the new shape. Also unblocks #9.1 (airport tree leaves).

**15A — seed discovery from the curated list.** `M`  *(ship first for immediate relief)*
In `board.build`, when `request.country_codes` (or a typed `destination_filter`) is set
**and** the live city board returns few/none inside the selection, run our own discovery
over a funnel instead of trusting the provider's "where can I go" call:

1. **Universe** — OurAirports, filtered to the selected countries/region (~9k worldwide
   with scheduled service → hundreds per continent, ~5–30 per country).
2. **Shortlist** — rank by `type` (large → medium) + `scheduled_service`, cap at ~100
   (or take all, for a single small country).
3. **Probe** — one cheap call per shortlisted airport: Travelpayouts `prices_for_dates`
   **with** an explicit `destination` (the discovery call already used with it omitted),
   or the Kiwi equivalent. Keeps only airports that come back with a real
   origin→airport price this month; that price is the seed for ranking. ~600 calls/min,
   so ~100 airports ≈ 10–12s, a single country ≈ 2–4s. This is the step that answers
   "which of these is actually reachable from TLV" — OurAirports says what *exists*, the
   probe says what *flies*.
4. **Fill** — merge the survivors into `candidates`, re-rank cheapest-first, then the
   **existing** budget cap + `fill_matrix` loop + preview-first streaming.

Gated on a filter being set: "To: Everywhere" keeps the current ~160-city board (the
cheapest-anywhere genuinely *is* nearby, so probing 9k airports every search is waste).
No new provider — works today on Kiwi/TP. This is 15C's discovery step done offline, so
building it cleanly (a "discover a candidate list, then fill it" path) is a stepping
stone, not throwaway.

**15C — Google price-graph board provider.** `L`  *(the real arc — needs a spike first)*
Promote `backend/providers/google_flights.py` from per-cell verifier to a first-class
board provider that can `discover()` and `fill_matrix()`, selected with
`FM_BOARD_PROVIDER=google`. Would replace **Kiwi** as the primary board source;
**Travelpayouts stays exactly where it is** — the estimate-first / fallback source
(`_base_provider`, `_fallback_provider`).

- **The plan:** Google has a keyless **price-graph RPC** — cheapest round-trip per
  departure date over a range, for a trip-length band, in one call (the same "diagonal"
  shape `kiwi.py` already fills). Port the message from `krisukox/google-flights-api`
  (Go, `GetPriceGraph()`); `fast-flights` builds the point-query protobuf and
  `_parse_all_itineraries` parses results, but does not expose the graph message.
- **In its favour:** free, keyless, no new service; data from the source we already trust
  for verification; Google is **not** IP-blocking the Oracle VM (Kiwi is — that is why
  Kiwi boards take ~5 min today). The 2026-09-07 spike confirmed Google returns **real
  party totals**, not per-person.
- **The blocker the spike hit:** the *batched* price-graph / calendar call needs the
  `SNlM0e` XSRF token that Google withholds from anonymous clients. Without it you fall
  back to point queries — one call per date pair — which measured **~15–20 min for 20
  destinations**, i.e. slower than Kiwi, and the spike was parked there. So 15C is not
  "port a Go function"; it needs a spike to either (a) obtain / mint `SNlM0e` reliably
  from a warm session, or (b) find another batched endpoint, or (c) decide point-query
  throughput is acceptable with heavy caching + estimate-first painting.
- **Risk:** Google could throttle later — mitigations: `fast-flights` v3 BrightData /
  SearchApi hooks, or a residential proxy.
- **Discovery for 15C:** the price-graph is route-keyed, so it still needs a candidate
  list — 15A's OurAirports seeding feeds it directly.

**Because of that blocker: 15.0 + 15A are the committed near-term work** (they fix the
reported bug on the providers we already have). 15C stays the intended endgame but is
gated on its own spike.

**Deferred — reviewed 2026-09-10.** 15.0 + 15A + 15.1 are shipped and the coverage gap
that opened #15 is closed. What 15C would still buy is a *faster, real-totals* primary
board — an upgrade to plumbing that already works, not a missing capability. Against that:
the spike is a coin-flip (a plausible outcome is "the token-mint GET is CAPTCHA'd from the
Oracle datacenter IP → dead without a residential proxy"), and a win puts a
reverse-engineered Google surface on the critical path with the same break-on-Google's-
schedule fragility as the HTML parser. With ~no traffic and no latency complaints, the
small certain UX wins (#1, #6, #11 …) are the better use of time.

Revisit when either (a) board latency becomes a real complaint from real users, or
(b) a wider launch is being prepped and the "real totals, not optimistic estimates"
accuracy story needs to be tight. Cheap hedge available first: timebox **just the
token-mint-from-the-VM** to ~2h — whether the datacenter IP gets CAPTCHA'd is the whole
ballgame and permanently informs the call.

**Parked:** Google Travel Explore / SerpApi as a discovery source. Revisit only if 15A's
curated seeding proves too coarse in practice.

**Acceptance (15.0 + 15A + 15.1):** TLV → "Africa", 3-month window, ~1 week → returns
Sharm / Hurghada (needs 15.1) plus at least a few of Nairobi / Zanzibar / Cape Town /
Johannesburg (needs 15A), each with a filled grid.

**Expectations caveat:** even with perfect discovery, TLV → sub-Saharan Africa is
genuinely 1–2 stops and expensive — those grids will be sparse and pricey. That is real,
not a bug. The goal is that the destinations *appear* when asked for, not that they are
cheap.

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
3. **Accept it** and lean on 15C (Google board) as the primary, Kiwi as the
   real-totals cross-check on cheapest cells only.

**Note:** the merged-CA hack (`config._ca_bundle()`) is corp-proxy-specific and already
correctly no-ops on the VM; a proxy integration should not resurrect it.

---

## Smaller / maybe

- ~~Migrate Travelpayouts Data API to the Nov-2025 version — the old one stops working
  **2026-06-15**.~~ **Investigated 2026-09-10: nothing to do.** The 2026-06-15 shutdown is
  the Travelpayouts *Flights Search API* (the real-time `flight_search` +
  `flight_search_results` polling flow). FlightMatrix does not use it — `providers/
  travelpayouts.py` only hits the **Data API** (`/v2/prices/latest`,
  `/aviasales/v3/prices_for_dates`, `/v1/prices/calendar`), which is current with no
  deprecation notice, and booking links are plain `aviasales.com/search/...` web URLs.
  The original note conflated the two products.
- ~~`fast-flights` pinned `>=2.2` but the code targets the 3.x API.~~ **Done 2026-09-10:**
  `requirements.txt` now pins `fast-flights>=3,<4`; the live verifier was retested against
  3.1.0 (TLV→ATH returned a real total + segments + Google link).
- SerpApi Google Travel Explore (free 250/mo) as a discovery source — **parked** under
  Lever 3; revisit only if #15A's curated seeding proves too coarse.

---

## Done features

### Verified-price freshness + verify self-healing (2026-09-10)

Three linked fixes after a cell showed ₪22,848 as a "live total" when Google Flights
actually had ₪12,977 — a verification frozen since who-knows-when.

- **Verifications go stale.** `FM_VERIFY_FRESH_MINUTES` (default 60). The background
  cross-check re-checks any cell whose verification is older than that (was: *skip a
  verified cell forever*); the board grid marks it stale (`Cell.found_at` now set from the
  verification time, `to_json` uses the shorter bound for verified cells); a manual cell
  click **never** trusts the cache — it always re-verifies live.
- **A failed re-check never clobbers a good price.** `cache.put_verified` drops a
  null-total write when a real price is already stored, so the aged number survives as the
  fallback. `/api/verify` serves that stored verification — clearly labelled "last verified
  N ago / may be out of date" — only when the live check fails.
- **The verify request self-heals.** `postJSON` wraps the fetch with a 15s timeout and two
  silent retries; on final failure the panel keeps the board price + booking link and says
  "the live check didn't respond, tap again" instead of the old "check your connection"
  dead end. `/api/details` uses the same helper.
- **Trip duration** was the first segment only ("4h" for a 20h TLV→HAN); now first
  departure → last arrival, layovers included (`_elapsed_minutes`).

Files: `config.py`, `cache.py`, `filler.py`, `board.py`, `models.py`, `app.py`,
`providers/google_flights.py`, `frontend/app.js`.

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
