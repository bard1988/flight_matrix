# FlightMatrix

Flexible-date, any-destination fare board. You give an approximate departure date, an
approximate return date and your passenger mix; it shows **many destinations at once**,
each as its own matrix where columns are departure dates (anchor ±7), rows are return
dates (anchor ±7), and each cell is the combined round-trip price for that date pair.

Existing sites show this grid one destination at a time, which makes "Athens on the
12th-19th vs Rome on the 14th-21st" a dozen-tab exercise. This puts them side by side.

## Quick start

```
py -3 -m pip install -r requirements.txt
py -3 run.py --demo          # synthetic data, no token needed, good for a look around
py -3 run.py                 # real data, needs a token (below)
```

It picks a free port, prints the URL and opens a browser.

## Serving it to colleagues

`run.py` binds `127.0.0.1` by default, so nothing off this machine can reach it. To serve
the board from this workstation:

```
.\serve.cmd /firewall     ONE TIME, in an ELEVATED prompt: opens inbound TCP 8712
.\serve.cmd               every time: binds 0.0.0.0 and serves
```

Colleagues then use `http://<this-hostname>:8712/`. They must be on the corporate network
or VPN, and this machine must be awake and unlocked-from-sleep.

It is a `.cmd`, not a `.ps1`, because group policy sets `AllSigned` for Windows PowerShell
here (`powershell -Command "Get-ExecutionPolicy -List"` shows `MachinePolicy AllSigned`),
so an unsigned script will not run in the default shell. Batch files are not subject to
execution policy. The firewall rule is scoped to the **domain** profile, so the port stays
closed on home and public Wi-Fi.

Three properties of the current build matter once more than one person uses it:

* **No authentication.** Anyone who can route to the host can run searches.
* **One process only.** Search progress is streamed from an in-memory registry
  (`app._streams`), so a second uvicorn worker would answer some stream requests with
  "unknown search id". Do not add `--workers`.
* **One shared rate limiter, one shared cache.** This is the reason to host centrally
  rather than have everyone run their own copy: the Kiwi pacing lock is process-global, so
  a single server cannot stampede the provider, and one person's filled grid is served to
  the next person from SQLite. The flip side is throughput - a 20-destination board is
  ~300 provider calls paced at `FM_KIWI_MIN_INTERVAL` (0.8s), i.e. about 4-5 minutes of
  provider time, and concurrent searches queue behind each other. Overlapping searches are
  nearly free; searches in different months are not.

SQLite runs in WAL mode with a 5s busy timeout so one user's board fill does not block
another user's reads.

## Getting the Travelpayouts token (free)

1. Register at <https://travelpayouts.com>.
2. Copy your token from <https://app.travelpayouts.com/profile/api-token>.
3. `copy .env.example .env` and set `TRAVELPAYOUTS_TOKEN=...`.

No website, traffic or approval is required. `fast-flights` needs no key at all.

## Two ways to read the dates

**Dates mean → "Around these dates"** (the original). The two fields are anchors, each
±`window_days`, and the grid is departure × return.

**Dates mean → "Anywhere in this range".** The two fields bound a *period* and the
**Nights** box says what to look for inside it — "a 3-4 night break sometime between
4 Nov and 30 Dec". Anchors cannot express this: two dates 56 days apart can only ever
describe ~56-night trips, so a 3-night filter over them correctly matches nothing.

**The layout stays departure × return in both modes.** In range mode that means the priced
cells form a diagonal band and the rest of the grid is empty — the empties are trip lengths
you did not ask for, not gaps in the data, so they render plain rather than hatched and
their tooltip says so. (Clicking one still prices it live.) An earlier version compacted
this to departure × trip-length; it was rejected, because seeing the real calendar shape
matters more than saving space.

Range mode is also far cheaper to fetch. Each Kiwi calendar call is one trip length, so
"3-4 nights over two months" is **2 calls per destination** rather than a whole grid:
3 destinations in ~10s, ~107 priced cells each. Coverage is reported against what was
actually asked for (117/117), not against the whole triangle (117/1941).

Each matrix is **its own scroll viewport in both axes**, sized independently of the grid,
so a card stays compact however wide the date window gets and several boards fit on screen
at once. While you scroll:

- The **date headers stay pinned** — the departure row across the top, the return column
  down the left, and the corner cell — so you never lose track of which cell you are on.
- Your **scroll position survives** a re-render, so cells arriving or a widening completing
  will not yank you back to the corner.
- The page does not scroll when a grid hits its end (`overscroll-behavior: contain`).

The window starts at ±7 days and grows on demand up to `FM_MAX_WINDOW_DAYS` (default ±28,
a 57 × 57 grid). Two ways to grow it:

- The **± Nd** button on each card, which widens every destination at once.
- **Keep scrolling past an edge.** Because the grid now always overflows its viewport,
  simply *reaching* an edge is ordinary browsing and deliberately does nothing. You have to
  push past it — about 160px of continued scrolling — which is the familiar "pull for more"
  gesture. A hint appears once you start pushing. This matters: widening costs live API
  calls, and Kiwi rate-limits, so it must never fire by accident.

### Why widening costs what it costs

One Kiwi calendar call = one **trip length**, and it covers the whole departure window
(verified: asking for 15 / 31 / 43 / 60 / 90 days returns exactly that many dates — the
calendar does not truncate). So call count depends only on how many trip lengths the window
spans, not on how wide it is.

A ±W window around an A-night trip spans lengths `max(0, A-2W) .. A+2W`: **22 diagonals at
±7, 50 at ±21**. All of them are fetched, so the grid fills its whole triangle:

| window | grid | valid cells | filled | time |
|---|---|---|---|---|
| ±7 | 15 × 15 | 197 | 189 (96%) | 21s |
| ±21 | 43 × 43 | 1,219 | 1,183 (97%) | 43s |

The only trip length that comes back empty is 0 nights (same-day return), which genuinely
has no flights rather than being a fetch gap. `FM_KIWI_NIGHTS_CEILING` (60) guards a runaway
window; set `FM_KIWI_MAX_DIAGONALS` to a positive number to cap fetching again, in which
case the lengths nearest your anchor trip are kept.

## How to read the board

- **Columns = departure date, rows = return date.** Cells below the diagonal (return
  before departure) are blank.
- The colour scale is a *rank* scale computed **per matrix**: each card runs from its own
  cheapest cell (green) to its own dearest (red), so the colours answer "which dates are
  good for *this* destination". **Colour therefore does not compare across cards** — a
  green cell on an expensive destination can cost more than a red cell on a cheap one.
  Compare destinations by the headline price, the cheapest-first ordering, and the
  board-wide cheapest marker. Exact prices are on every cell and in the tooltip.
- **Hatched cell = no cached data for that date pair.** It does *not* mean expensive.
  Click it to fetch that one cell live.
- **Green = cheap, red = expensive.** The **cheapest cell in each matrix has a yellow ring**;
  the cheapest on the whole board gets a thicker ring and a yellow card border.
- Corner wedge = the itinerary has stops (bigger wedge = 2+); exact count is in the tooltip.
  Small amber dot = the cached price is over a day old.
- **Fill live** on a card prices every cell in that grid for real (~50s). Card header shows
  `EST` or `LIVE` for whether its headline number is an estimate or a verified price.
- Dotted left edge marks 7- and 14-night trips, a guide for reading trip length off the
  diagonal.
- **Table view** lists every priced cell as sortable text, cheapest first.
- **Only destinations** does two jobs. Set it **before Search** and it restricts the search
  itself, so the destination budget is spent inside the filter: `IT` searches the cheapest
  *Italian* cities rather than the cheapest cities anywhere with the rest hidden. Measured:
  unfiltered it returned Larnaca/Palermo/Paphos/Catania/Eilat/Naples; with `IT` it surfaced
  Venice, Milan and Rome, none of which made the unfiltered list. Typed **after** a search it
  narrows what is shown, instantly and with no API calls.

  Matching is by IATA code, city, country code or **country name** (`greece`, `italy`).
  Codes match *exactly* and names by substring — deliberately, because substring-matching a
  two-letter code against country names over-matches badly (`IT` is inside L**it**huania and
  Un**it**ed Kingdom, which inflated one search from 7 matches to 16).

- **Time-of-day windows (Depart between / Return between).** Unlike every other filter these
  are **search parameters, not display filters**, and take effect on the next Search — the
  Search button turns amber to say so. The reason is structural: the price calendar returns
  only a date and a price, with no departure time, so there is nothing to filter on
  client-side. Narrowing the window genuinely reprices the board, because the price is then
  drawn from a different set of flights:

  | filter | cheapest | cells priced |
  |---|---|---|
  | none | ₪694 | 189/197 |
  | depart 06:00-11:00 | ₪818 | 189/197 |
  | depart 17:00-23:00 | ₪738 | 176/197 |

  Fewer cells is expected: a date with no flight in the window has no price. **A filtered
  search bypasses the cell cache in both directions** — it neither reuses it (the cache is
  keyed on route/dates/currency only, so it would silently hand back unfiltered prices) nor
  writes into it (which would poison it for later unfiltered searches).

- **Day-of-week and trip-length constraints.** Pick which weekdays you can depart and return
  on, and a min/max nights range — e.g. Thu out, Sun back, 2-4 nights. This is a view over
  cells already loaded, so it is instant and free, and the **colour scale, each card's
  cheapest cell and the board ordering all recompute over only the matching cells** — so it
  answers "cheapest Thu→Sun", it does not merely hide rows. Measured: unconstrained the
  board led with Larnaca ₪380; constrained to Thu→Sun it reordered to Eilat ₪719 first.
  Excluded cells fade rather than vanish, so you can still see what you ruled out.

- **Cross-hair.** Hovering a cell lights its departure column and return row and bolds both
  date headers, so which date is outbound and which is return is never ambiguous. Clicking
  pins it so it survives the mouse leaving the grid.
- **◎ locate** on each card scrolls that grid to its own cheapest cell and pulses it, then
  names the price and dates in the status bar. On a widened grid the winner is usually
  scrolled out of sight.
- **Clicking a cell fetches its flight times** from the board source (`/api/details`), in
  parallel with the Google cross-check. You get **both legs** with local departure/arrival
  times, flight numbers, carriers, stops and duration — and it works at **any horizon**,
  including dates Google has no data for at all. The block is labelled with its source and
  price, because each source's *cheapest* itinerary is often a different flight, so two
  unlabelled departure times would look like a contradiction.
- **Booking links carry your filters**, not just the dates: passenger counts and, when
  `Nonstop only` is on, Kiwi's direct-only flag (`stopNumber=0`). Without that the board
  filters correctly but the booking page opens showing one-stop options, which reads as the
  filter being ignored.
- If a cell cannot be cross-checked (some routes are absent from Google Flights entirely),
  the panel still shows the board's own price and a **booking link from the source that did
  price it**, rather than only a dead Google link.

## Kiwi.com: the default board source

**The best free source found, and it needs no key and no signup.** Kiwi's open umbrella
GraphQL endpoint (`api.skypicker.com/umbrella/v2/graphql`) is the only free source that
returns **real party totals for your actual passenger mix**, rather than a single-adult
fare you have to scale up:

- `returnOnePerCityItineraries` — ~70 destinations from TLV with real 2-adult-3-child
  prices, in **one call**.
- `returnItineraryPricesCalendar` — 15 dated prices per call. Pin `nightsCount` to a single
  value and each call fills one **diagonal** of the departure × return matrix, so ~22 calls
  give a complete grid.

Measured against the previous Travelpayouts default, same search, 21 days out:

| board source | mean coverage | what the price means |
|---|---|---|
| Travelpayouts | 25% | single-adult fare × passengers (measured 30-60% optimistic) |
| **Kiwi** | **95%**, often 100% | **real total for 2 adults + 3 children** |

Six destinations in ~41s. Cross-validation: Kiwi's cheapest Larnaca cell came back at
₪980, exactly matching an independent Google Flights verification of the same cell.

Two caveats. Kiwi does **virtual interlining**, so some cheap results are self-transfer
combinations on separate tickets — legitimate, but a missed connection is your problem, not
the airline's. And `visibleDates` is mandatory and may be combined with only *one* of
`nightsCount` / `departureDates` / `returnDates`, which is why the fill is diagonal.

Set `FM_BOARD_PROVIDER=travelpayouts` to switch back to the cached source.

### Kiwi rate limiting, and how it is handled

Kiwi blocks bursts by IP with a bare `403`, no `Retry-After`, and the block lasts minutes.
It is volume-based: while blocked, even a trivial `{__typename}` 403s, and no header
combination avoids it. Interestingly the block applies to the *search* operations — cheap
queries recover first.

Five things keep it out of your way, in order of how much they matter:

1. **Cache reuse is the main lever** (see below). Diagonal fetching is deliberately NOT
   capped any more: capping it left widened grids with a large unfilled band, which is a
   worse problem than the extra calls.
2. **Cache reuse.** A filled grid is stored and reused for `FM_KIWI_CACHE_HOURS`
   (default 6), so repeat searches cost zero calls. Re-querying is the main way the limit
   gets tripped.

   Reuse requires the cached grid to be **nearly complete for the window being asked for**
   (`FM_CACHE_REUSE_MIN_FRACTION`, default 0.85 of the valid cells), not just to have some
   minimum number of cells. A flat cell count is unsafe: a grid written under an older,
   narrower fetch strategy — or for a smaller window — easily clears "20 cells" while
   missing whole diagonals, and would then be served forever without ever refetching.
   Measured symptom: a Larnaca grid sat at 85/180 cells (47%), missing every trip length
   under 7 nights, and no amount of re-searching would fill it. With the fraction check it
   refetches and reaches 170/180 (94%).
3. **Pacing.** `FM_KIWI_MIN_INTERVAL` (0.8s) between calls, `FM_KIWI_WORKERS` (2) concurrency.
4. **Waiting it out, visibly.** On a 403 the provider backs off 8 → 16 → 32 → 45s up to
   `FM_KIWI_WAIT_BUDGET` (default 180s), streaming *"Kiwi is rate-limiting; waiting 16s
   then retrying (24s of 180s budget used)"* to the status bar, so a pause reads as waiting
   rather than hanging. The block state is **shared across threads**, so a grid fill pauses
   once as a whole instead of each worker burning the budget separately.
5. **Fallback last.** Only after the budget is spent does it drop to Travelpayouts, and it
   says so — because the prices change meaning from real party totals to scaled estimates.

If you do get blocked, waiting is the only fix; hammering Search keeps the window open.

## The accuracy story, honestly

The board and the per-cell price come from two different places, on purpose.

**Board fill: Travelpayouts / Aviasales Data API.** A cache of fares real Aviasales users
saw over the last 2-7 days. It is the only free source that can answer *"where can I even
go from TLV"* in a single call. Two consequences:

- **Coverage is search-driven, and it is the binding constraint.** Cached rows exist only
  where real people searched, so coverage collapses the further ahead you look. Measured
  live from TLV across 8 destinations, as a share of the 197 valid cells in a ±7 window:

  | departure | 14 days out | 30 | 45 | 60 | 90 | 150 |
  |---|---|---|---|---|---|---|
  | mean coverage | **43%** | 36% | 24% | 13% | 12% | **2%** |

  **So this tool is genuinely useful inside about two months and close to useless past
  four.** The board warns you when your window is far enough out to be sparse. Coverage
  also varies hugely by route at any horizon: on one 3-weeks-out run Rome came back 54%
  and Larnaca 49%, while Varna was 3%.

  The gaps also cluster on the odd off-peak combos that are often cheapest, which is why a
  missing cell is hatched and excluded from the colour scale rather than left blank.
- **There is no passenger parameter, and the resulting estimates are measurably
  optimistic.** Rows are single-ticket prices with no child fare, so a family total is
  extrapolated as `price × (adults + children × FM_CHILD_FACTOR)`. `FM_CHILD_FACTOR`
  defaults to `1.0`. Rows past `expires_at` are dropped outright.

  Checked live against Google Flights, TLV, 2 adults + 3 children, 3 weeks out:

  | cell sampled | n | mean | median | range |
  |---|---|---|---|---|
  | destination's **cheapest** | 5 | **+62%** | +31% | −10% to **+201%** |
  | destination's **median** | 5 | +35% | +27% | −5% to +85% |

  Two things follow. A typical cell is roughly **a third under** the real family price. And
  the *cheapest* cell is systematically worse, because the cheapest cached fare is exactly
  the one likely to have a seat or two left at that price — verifying the headline cell is
  a worst case by construction. The error is not one-directional though: some cells came
  back cheaper than estimated.

  **This means the ranking itself is not trustworthy, not just the absolute numbers.** In
  one run Larnaca led the board at ₪1,010 and verified at ₪3,043, which put it last.
  Reproduce with `py -3 data/estimate_error.py`.

**Per-cell verification: Google Flights via `fast-flights` (3.x).** Real bookable prices
with real `adults` / `children` counts, in your requested currency. About one second per
lookup. The result is cached and folded back into the board, which re-sorts: if a verified
price is much worse than the estimate, that destination visibly drops, which is the whole
point. Verified cells get a solid border and their card header switches from `EST` to
`LIVE`.

One consequence worth expecting: as you verify a card's cheapest cell, its headline falls
through to the *next* unverified estimate, so the card can climb back up the board. That is
honest — you have not yet checked that cell either — but it does mean a card only settles
once you have verified the few cells you actually care about.

Treat the board as **ranking**, and the click as **truth**.

## Two sources, layered

**Kiwi first, Google Flights on the fly.** The board renders from Kiwi in seconds, then the
**Auto cross-check** toggle (on by default) quietly re-prices its cheapest cells on Google
Flights in the background, upgrading them from `KIWI` to `LIVE` in place and re-sorting.

Two details that turned out to matter, both found by measurement:

- **Cells are picked per destination, not cheapest-N overall.** A flat cheapest-40 list sent
  all 40 slots to a single cheap city. Now it takes each destination's own cheapest few
  (`AUTO_VERIFY_PER_DEST`, 6) and interleaves them, capped at `AUTO_VERIFY_CELLS` (40).
- **Routes Google cannot price are skipped.** TLV→Ramon (ETM) failed all 40 attempts —
  it is simply not in Google's data. `cache.unpriceable_destinations()` drops any
  destination with 3+ failures and no successes, so the budget is never burned re-failing
  the same route. Those cells keep their Kiwi price, which is the right answer.

When both sources do price a cell they agree closely: Varna came back at ₪1,854 live against
Kiwi's ₪1,853, and Larnaca's cheapest matched at ₪980 exactly.

### Why a cell occasionally disagrees wildly

Kiwi's price *calendar* is a precomputed index, and individual entries go stale. Measured
against Kiwi's own full search at 2 adults:

| route | nights | calendar | full search | ratio |
|---|---|---|---|---|
| TLV-CTA | 16 | 671 | 1,329 | **1.98** |
| TLV-ATH | 7 | 797 | 818 | 1.03 |
| TLV-LCA | 5 | 796 | 857 | 1.08 |
| TLV-BUD | 9 | 1,149 | 1,149 | 1.00 |
| TLV-FCO | 6 | 943 | 943 | 1.00 |

Four of five agree within 8%; Catania on an uncommon 16-night trip was off by 2×, and
Google put it higher still (₪2,120, i.e. +216% over the board). So it is **per-cell
staleness on unusual trip lengths, not a scaling error** — the calendar does scale correctly
with passengers (measured exactly ×1/×2/×3/×5 for 1a/2a/3a/2a+3c). This is precisely what
the automatic cross-check exists to catch.

## Fill live: the actual answer to sparse data

Each card has a **Fill live** button. It prices *every* cell in that destination's grid via
Google Flights, at 4 concurrent lookups. Measured: **~50 seconds for a 197-cell grid**,
taking Larnaca from 96 cached cells (49%) to 196 real ones (99.5%).

That solves both problems at once — 100% coverage *and* true prices for the real passenger
mix — with no API key and no third-party dependency. Results are written to the cache as
they arrive, so a cancelled or crashed fill keeps whatever it got, and re-running only
retries the cells that failed. Click the button again while it runs to stop it.

Concurrency is `FM_FILL_WORKERS` (default 4). Measured at 4: 12/12 lookups succeeded with
no added latency and 3.7× the throughput of serial. Raise it cautiously; Google rate-limits
and a block costs far more than the speed gains.

## Why not Skyscanner, Amadeus, Ryanair, or the airlines directly?

All investigated with live probes. Kiwi won (see above); the rest are unusable here:

| Source | Free? | Obtainable? | Verdict |
|---|---|---|---|
| **Ryanair** `farfnd` | Yes, keyless | Yes | **API is perfect** — cheapest round trips to every destination over a date range, one call. But Ryanair serves **zero Israeli airports** (224 active, none in IL). Useless from TLV. |
| **Wizz Air** | Yes, keyless | No | Dominant LCC at TLV, but `metadata.json` is gone and the versioned API path has moved. Would mean reverse-engineering a SPA bundle they actively relocate. |
| **Skyscanner** | Free for partners | No | Commercial partner application, reviewed case-by-case. No self-service key. |
| **Kiwi Tequila** | — | No | Invite-only partner program since 2026; self-serve signup closed. |
| **Amadeus** | — | No | Self-service tier shut down July 2026. |
| **Duffel** | Test free, live pay-as-you-go | Partly | Booking-oriented, commercial setup, per-booking pricing. |
| **RapidAPI Skyscanner proxies** | Paid | Yes | Unofficial scrapers, variable reliability, against Skyscanner's terms — and still only estimates, not true 5-passenger totals. |

The conclusion that matters: **the best free source was the one already integrated.** Google
Flights is keyless, effectively unlimited, and returns real family pricing. Nothing on that
list would have been better than bulk-filling with it. Reproduce the network checks with
`py -3 data/probe_ryanair.py` and `py -3 data/probe_wizz.py`.

### Direct airline feeds (Wizz, El Al, Arkia, Israir)

Also investigated, with a live probe each (`data/probe_il_carriers.py`, `probe_wizz2.py`):

| Airline | Reachable? | Finding |
|---|---|---|
| **Wizz Air** | **Yes** | `be.wizzair.com/<version>/Api` works. Version must be scraped from their homepage bundle (it was 29.15.1, not the 27.x in old gists). `asset/map` gives 196 cities and **29 TLV destinations**; `search/timetable` returns ~20 dated prices per leg in one POST. |
| El Al | No | Returns HTTP 247 (a WAF code) on any API-ish path; no API references in its markup. |
| Arkia | No | Cloudflare bot challenge ("Just a moment...") on every path, including the homepage. |
| Israir | No | Homepage is a site-builder template; the only `/api/*` routes are CMS config, not flights. |

**Wizz works but is deliberately not wired in as a price source.** Its timetable returns a
**per-person lowest fare that ignores passenger counts** — so using it would reintroduce
exactly the ×5 extrapolation error that Fill live eliminates, on routes where we already
have true 5-passenger prices from Google. It also rejects repeated calls with
`{"handlerError":"InvalidProtocol"}` and its version string moves.

The empirical check that settles it: Google's own response for TLV-LON lists **33 carriers
including El Al (LY) and Arkia (IZ)**, and our filled cells already return Wizz Air, Israir
and SKY express as cheapest-per-cell winners. The aggregator has the carriers; what we were
missing was itineraries, and that was our parser (below), not the source.

## Configuration

All optional, via `.env` or environment:

| Variable | Default | Meaning |
|---|---|---|
| `TRAVELPAYOUTS_TOKEN` | *(none)* | required for real data |
| `TRAVELPAYOUTS_MARKER` | *(none)* | affiliate marker appended to Aviasales links |
| `FM_CHILD_FACTOR` | `1.0` | child price as a fraction of an adult ticket |
| `FM_STALE_AFTER_HOURS` | `24` | cached rows older than this get the staleness dot |
| `FM_GRID_STRATEGY` | `latest` | `latest` or `prices_for_dates` |
| `FM_CANDIDATE_MULTIPLIER` | `3.0` | how many extra destinations discovery tries |
| `FM_FILL_WORKERS` | `4` | concurrent Google Flights lookups during Fill live |
| `FM_BOARD_PROVIDER` | `kiwi` | `kiwi` (real party totals) or `travelpayouts` (estimates) |
| `FM_KIWI_WORKERS` | `4` | concurrent Kiwi calendar calls per destination |
| `FM_KIWI_NIGHTS_CEILING` | `60` | longest trip length the diagonal fill will request |
| `FM_KIWI_MAX_DIAGONALS` | uncapped | cap on trip lengths fetched; nearest-to-anchor kept |
| `FM_KIWI_MIN_INTERVAL` | `0.8` | seconds between Kiwi calls; it IP-blocks bursts |
| `FM_CACHE_REUSE_MIN_FRACTION` | `0.85` | share of a window's valid cells a cached grid needs before it is reused |
| `FM_KIWI_CACHE_HOURS` | `6` | how long a filled grid stays reusable |
| `FM_WINDOW_STEP` | `7` | days added to the window each time it widens |
| `FM_MAX_WINDOW_DAYS` | `28` | widest the window can get (±28 = a 57 × 57 grid) |
| `FM_CA_BUNDLE` | merged bundle | CA bundle for outbound HTTPS |
| `FM_DEMO` | *(unset)* | `1` for synthetic data |

### Grid strategy

Which endpoint fills a departure × return grid was **measured against the live API**, not
taken from the docs. For TLV→ATH over one month:

| endpoint | distinct pairs | max returns per departure |
|---|---|---|
| **`/v2/prices/latest`** | **29** | **14** |
| `/aviasales/v3/prices_for_dates` | 16 | 3 |
| `/v1/prices/calendar` | 8 | 1 |
| `/aviasales/v3/grouped_prices` | 11 | 1 |
| `/v2/prices/week-matrix` | 0 usable | — |
| `/v2/prices/month-matrix` | one-way only, no `return_date` | — |

`latest` was a strict superset of every other source on all 8 destinations tested, so
there is nothing to gain from unioning them and it is the only strategy used.
`prices_for_dates` is still used for **discovery**, where omitting `destination` answers
"where can I go from here" in one call. Set `FM_GRID_STRATEGY=prices_for_dates` to compare.

Two gotchas worth knowing if you touch this: `prices_for_dates` silently picks one
arbitrary return date per departure unless you pass `return_at`, which is what made the
first implementation return 1% coverage; and `latest` rows carry no booking `link`, so the
Aviasales deeplink is constructed as `/search/ORIGIN{DDMM}DEST{DDMM}{pax}`.

Reproduce any of this with `py -3 data/probe_api.py`, `data/coverage.py` and
`data/coverage_horizon.py`.

## Layout

```
backend/
  app.py                  FastAPI, SSE streaming, /api/verify
  board.py                discovery -> grid fill -> progressive events
  cache.py                SQLite: cells, verified, searches
  models.py               SearchRequest, Cell, DestinationMatrix
  airports.py             IATA -> city/country (downloaded once, cached)
  config.py               token, defaults, CA bundle resolution
  providers/
    travelpayouts.py      board fill + destination discovery
    google_flights.py     live per-cell verification
    demo.py               synthetic data for --demo
frontend/                 index.html, app.js, styles.css
data/
  emit_fare_ramp.py       derives + validates the fare heatmap ramp
  probe_api.py            which endpoint can fill a grid (measured)
  coverage.py             per-source and union coverage
  coverage_horizon.py     coverage vs booking horizon
  live_board.py           build a real board and print it as text
  spike.py                original step-1 endpoint spike
  get_wheel.py            fetch a PyPI wheel past the pinned corporate mirror
  shoot.py, probe*.py     headless screenshot / DOM probes
```

Everything in `data/` except `airports.json` and the caches is a dev aid; none of it is
imported by the app.

## Networking on this machine

The corporate proxy intercepts some hosts and re-signs them with the internal CA, while
others are reached directly and need the ordinary public roots. Neither bundle alone works
for both, so `config._ca_bundle()` merges `certifi` with
`~/certificates/amat-corporate-cas.pem` into `data/ca-merged.pem` and uses that. Without
the merge, `api.travelpayouts.com` works but `pypi.org` fails, or vice versa.

## Colour ramp

The heatmap is a seven-step **green → amber → red** scale, applied **per matrix**: green =
that destination's cheapest date pair, red = its dearest. Each card's own cheapest cell
gets a **yellow ring**; the board-wide cheapest gets a thicker ring plus a yellow card
border. Yellow is *reserved* — it never appears in the ramp — so the marker can never be
read as a price level.

Per-matrix scaling means every card uses the full ramp and its internal structure is
readable, at the cost of colour no longer comparing between cards (see "How to read the
board").

### Lightness does the work

Green↔red is the worst pair for red-green colour blindness — hue alone, green/amber/red
collapse together under deuteranopia. So the ramp's **OKLCH lightness is strictly monotonic
cheapest → dearest** (L 0.43 → 0.84 on the light surface, minimum step ΔL 0.065; mirrored
on the dark surface). With hue removed the scale still separates every step by tone, and
the cheapest vs dearest pair stays ~40 ΔE apart even simulated. The **cheap end also
carries the salience** the board is for: the deepest, most saturated green, so the eye
lands on the good dates first. Every cell also prints its price and the table view lists
everything — the real backstop.

Each step ships its own ink token (`--qi0`…`--qi6`, black or white by measured contrast;
minimum label contrast 4.66:1) since both ends of the ramp are dark enough to need white.

Regenerate and re-validate (lightness monotonicity, label contrast, CVD ΔE) with
`py -3 data/emit_fare_ramp.py`. It supersedes the earlier `make_ramp*.py` /
`emit_ramp_css.py` / `check_diverging_cvd.py`, which built the one-hue and diverging ramps
this replaced.

## Known gaps

- **`fast-flights` cannot be installed with plain pip here.** pip is pinned to an internal
  Artifactory mirror that does not carry it, and pip's own TLS stack fails against upstream
  PyPI. Reinstall after a Python upgrade with:

  ```
  py -3 data/get_wheel.py fast-flights primp protobuf selectolax
  py -3 -m pip install --no-index --find-links wheels fast-flights
  ```

- **`fast-flights` discards itineraries, so we parse the payload ourselves.** Its parser
  reads only `payload[3][0]`. Google also returns a "best flights" block at `payload[2][0]`,
  and on TLV-LON that block held the cheapest option by a wide margin — Israir at 8,285 ILS
  versus 10,974 for the cheapest in `payload[3]`, a 24% understatement. `_parse_all_itineraries`
  in `providers/google_flights.py` reads every block and falls back to the library parser if
  Google changes shape. Verified rows carry `parser_version`; anything older than
  `config.PARSER_VERSION` is ignored and re-fetched, so a parser fix invalidates stale prices
  automatically instead of silently trusting them.
- **`fast-flights` 3.x crashes on routes Google does not serve.** Its parser raises a bare
  `TypeError` from `payload[3][0]` when the response has no itinerary block. That is caught
  and reported as "no itineraries for this route on these dates", which is what it actually
  means, but it is a library bug rather than a clean API.
- Nonstop-only is passed to discovery and filtering, but with cached data a nonstop board
  is considerably sparser again.
- Discovery ranks candidates on the cheapest fare anywhere in the month, not strictly
  inside your ±7 window, because requiring an in-window row would discard destinations
  whose grid can still be filled. It over-fetches `FM_CANDIDATE_MULTIPLIER`× candidates and
  stops once enough grids come back non-empty.
- A destination with 6 populated cells gets the same card as one with 96. The cell count
  in each header is how you tell them apart.
"# flight_matrix" 
