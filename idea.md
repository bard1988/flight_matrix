# Ideas / backlog

Things worth doing, not yet scheduled.

---

## Feature backlog

| # | Feature | Size | Status |
|---|---|---|---|
| 1 | **Filter by airline** — bundled airline-name DB, refreshed periodically (and/or from what searches return) | M | todo |
| 6 | **Cabin class** selector (economy / premium / business) — thread through provider → API → UI | M | todo |
| 4 | Make **"any trip inside this period" (range mode) the default**; nights box controls trip length; drop anchors mode | L | todo — destructive, decide first |
| 7 | **Mobile: more compact** | M | todo |
| 7.1 | — passengers shown in the bar, not behind Options | S | todo |
| 7.2 | — denser matrices on small screens | S | todo |
| 8 | **Design pass** — use the `design` skill / a proper design system | L | todo |

### Notes on specific items

- **#4 drop anchors mode.** `date_mode` (`anchors|range`) is threaded through `models.py`,
  `board.py`, `app.py` and the frontend. Removing a mode is a real refactor and changes
  the default UX — confirm before starting.
- **#1 airline DB.** `data/airlines_seen.py` already collects airline names. Filtering can
  be client-side on already-fetched cells (each cell carries `airline`); the search-time
  filter (spend the destination budget inside the filter) is the harder half.

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
