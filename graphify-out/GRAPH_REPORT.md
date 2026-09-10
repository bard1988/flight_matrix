# Graph Report - flight_matrix  (2026-09-09)

## Corpus Check
- 134 files · ~85,615 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 807 nodes · 1537 edges · 53 communities (36 shown, 15 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 125 edges (avg confidence: 0.89)
- Token cost: 190,928 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50

## God Nodes (most connected - your core abstractions)
1. `SearchRequest` - 57 edges
2. `renderCard()` - 26 edges
3. `Cell` - 24 edges
4. `render()` - 24 edges
5. `KiwiProvider` - 23 edges
6. `TravelpayoutsProvider` - 22 edges
7. `ProviderError` - 20 edges
8. `DestinationMatrix` - 19 edges
9. `build()` - 15 edges
10. `verifyCell()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `run()` --uses--> `SearchRequest`  [INFERRED]
  data/probe_hours_board.py → backend/models.py
- `run()` --uses--> `SearchRequest`  [INFERRED]
  data/probe_search_filter.py → backend/models.py
- `Lever 1: Google Flights Price-Graph Board Provider` --semantically_similar_to--> `Kiwi.com Umbrella GraphQL Board Source`  [INFERRED] [semantically similar]
  idea.md → README.md
- `Cloudflare Tunnel Residential Fallback` --semantically_similar_to--> `Lever 2 / FM_KIWI_PROXY (residential proxy for Kiwi)`  [INFERRED] [semantically similar]
  DEPLOY.md → idea.md
- `flightmatrix systemd Service` --semantically_similar_to--> `compose.yaml flightmatrix service`  [INFERRED] [semantically similar]
  DEPLOY.md → compose.yaml

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Colour-vision-deficiency-safe fare ramp system** — design_fare_heatmap, design_colour_is_second_rule, design_oklch_monotonic_lightness, design_reserved_yellow_rule, data_emit_fare_ramp [EXTRACTED 0.85]
- **Kiwi datacenter-IP rate-limit mitigation stack** — readme_kiwi_rate_limiting, readme_cache_reuse, readme_diagonal_fill, idea_kiwi_travelpayouts_failover, deploy_datacenter_ip_risk, idea_kiwi_proxy [EXTRACTED 0.85]
- **Two-layer estimate-then-verify pricing flow** — product_two_layer_accuracy_model, readme_kiwi_board_source, readme_travelpayouts_board_fill, readme_google_flights_verification, readme_auto_cross_check [EXTRACTED 0.85]
- **Light / dark / mono variant system** — brand_flightmatrix_mark_flightmatrix_mark, brand_flightmatrix_mark_dark_flightmatrix_mark_dark, brand_flightmatrix_mark_mono_flightmatrix_mark_mono [INFERRED 0.75]
- **FlightMatrix horizontal lockup family** — brand_flightmatrix_lockup_flightmatrix_lockup, brand_flightmatrix_lockup_dark_flightmatrix_lockup_dark, brand_flightmatrix_lockup_ui_flightmatrix_lockup_ui [INFERRED 0.85]
- **All renderings of the FlightMatrix mark** — brand_flightmatrix_mark_flightmatrix_mark, brand_flightmatrix_mark_dark_flightmatrix_mark_dark, brand_flightmatrix_mark_mono_flightmatrix_mark_mono, brand_flightmatrix_icon_16_flightmatrix_icon_16, brand_flightmatrix_icon_32_flightmatrix_icon_32, frontend_favicon_favicon [INFERRED 0.85]

## Communities (53 total, 15 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (50): airport(), AutoVerifyBody, cancel_fill(), cancel_search(), cell_details(), ExtendBody, FillBody, health() (+42 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (23): parse_ts(), Travelpayouts timestamps come back in a few shapes; be forgiving., Kiwi board first, then Google Flights upgrading the cheapest cells…, Click the board's cheapest cell and confirm the live verification lands in the…, Check no card clips its grid at a range of viewport widths., Day-of-week / trip-length constraints must change the ANSWER, not just hide…, Hovering a cell must light its departure column and return row; clicking pins…, Exercise bulk live fill end to end through the UI. (+15 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (31): NoItinerariesError, ProviderError, Raised for anything the caller should surface rather than retry blindly., A full search for one exact date pair came back empty. Distinct from the other…, _add_proxy_bytes(), _clock(), _day_end(), _day_start() (+23 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (39): How distinguishable are the two arms of the green<->red ramp under colour…, report(), build(), check(), contrast(), delta_e(), _hex_rgb(), ink_for() (+31 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (38): fill(), pending_cells(), Any, date, Yield one event per cell as it lands, then a summary. Results are written to…, Every valid (departure, return) pair not already verified for this passenger…, Live-price an explicit list of (destination, depart, return) cells. Used to…, verify_cells() (+30 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (18): _ca_bundle(), Configuration for Flight Matrix. The Travelpayouts token is free: register at…, Resolve a CA bundle for outbound HTTPS. This machine sits behind a TLS-…, Is the Kiwi 403 coming from Kiwi, or from the corporate proxy? `x-symc-…, How many departure dates does ONE Kiwi calendar call actually return? If the…, What does Kiwi's price-calendar entry actually carry? The board infers each…, Can we reach El Al / Arkia / Israir / Wizz directly, keylessly? Time-boxed…, Does Kiwi's price calendar actually scale with passenger count? FlightMatrix… (+10 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (37): compose.yaml caddy service, compose.yaml flightmatrix service, One App Container Only Rule, Caddy Shared-Password Gate, Cloudflare Tunnel Residential Fallback, Datacenter-IP Block Risk (Kiwi/Google), Demo Mode (FM_DEMO), DuckDNS Updater (systemd timer) (+29 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (33): _apply_verified(), build(), build_board(), _check_headline(), _coverage_note(), date_axes(), _describe(), destination_matches() (+25 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (29): connect(), create_search(), finish_search(), get_all_verified(), get_matrix(), get_search(), get_verified(), _migrate() (+21 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (28): addDays(), animatedDests, applyTrip(), applyWhen(), destAxes, DOW, DOW_FULL, ensureVisible() (+20 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (12): Core data types for the fare board., Synthetic provider for developing and eyeballing the board without a token.…, Travelpayouts / Aviasales Data API. This is a cache of fares real Aviasales…, Build a real board against the live API and print it as text. py -3…, Is the board serving a stale, partially-filled grid from cache instead of…, Verify the board still works when the live provider is rate-limited., Build a board far ahead and check the advisory note is now correct., Audit a filled grid: does each cell's price survive a real search for that… (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.15
Nodes (23): bake(), gap_mask(), head(), icon(), inject(), line_end(), load(), main() (+15 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (24): Repo Knowledge Graph (graphify-out), The 11px Floor Rule, "The Departures Board" North Star, Fare Matrix (signature component), The Flat-By-Default Rule, FlightMatrix Design System, The Tabular Numbers Rule, Triangular Wedge (stops indicator) (+16 more)

### Community 13 - "Community 13"
Cohesion: 0.18
Nodes (21): cellAria(), convert(), fetchTimes(), finishCard(), fmtCompact(), fmtMoney(), fmtStops(), headlineChip() (+13 more)

### Community 14 - "Community 14"
Cohesion: 0.11
Nodes (10): Bulk-fill a destination's whole grid with live Google Flights prices. Why this…, # NOTE: the progress denominator is `total_cells`, never `total`. `total` on a, Provider protocol. Two very different kinds of source sit behind this…, How wrong are the cached estimates, and is the error worse for the cheapest…, Does the existing Google Flights source surface El Al / Arkia / Israir / Wizz?…, Do Catania's board cells correspond to itineraries that actually exist?…, Does the LIVE source (Kiwi) actually thin out far ahead, the way the cache did?…, Find a connecting itinerary so the numbered-leg rendering is actually exercised. (+2 more)

### Community 15 - "Community 15"
Cohesion: 0.23
Nodes (8): MissingTokenError, Any, date, Normalise a row from any of the price endpoints into a Cell., Every calendar month the windows touch, as YYYY-MM-01., Destinations reachable from the origin, ranked by cheapest fare in the month.…, The grid filler. One call per calendar month the window touches., TravelpayoutsProvider

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (10): Kiwi.com via its open umbrella GraphQL endpoint. The best free source found,…, slug_for(), _slugs(), Is the CTA gap staleness, or a per-person vs party-total units mismatch? If the…, Open a generated Kiwi booking link and confirm it actually prefills a search.…, Fetch real flight times for one cell from Kiwi, including far-out dates., How long does a Kiwi search block actually last? Poll a real search until it…, Why does the calendar price a date pair that a full search cannot fill? Checks… (+2 more)

### Community 17 - "Community 17"
Cohesion: 0.17
Nodes (18): applyCell(), bandCells(), buildDowPicker(), cellAllowed(), cellValue(), constraintsActive(), describeConstraints(), fillOpenDestination() (+10 more)

### Community 18 - "Community 18"
Cohesion: 0.33
Nodes (16): FlightMatrix icon 16px, FlightMatrix icon 32px, FlightMatrix lockup (dark variant), FlightMatrix horizontal lockup, FlightMatrix wordmark (Flight ink + Matrix green), Tagline: Search Compare Fly, FlightMatrix compact UI lockup, FlightMatrix brand color palette (+8 more)

### Community 19 - "Community 19"
Cohesion: 0.27
Nodes (12): contrast(), _dE(), ink_for(), _lab(), _lin(), luminance(), Derive the green -> orange -> red price ramp now used by the board. Supersedes…, report() (+4 more)

### Community 20 - "Community 20"
Cohesion: 0.21
Nodes (14): afterRegionChange(), buildRegionTree(), closeDestPop(), destTagList(), filterRegionTree(), onRegionChange(), openDestPop(), refreshRegionCounts() (+6 more)

### Community 21 - "Community 21"
Cohesion: 0.24
Nodes (12): _build_index(), country_name(), _country_table(), describe(), _download(), load(), Any, IATA code to city/country lookup. Travelpayouts publishes these as plain JSON… (+4 more)

### Community 22 - "Community 22"
Cohesion: 0.27
Nodes (13): axesFor(), canWiden(), clearCross(), departureStrip(), highlightCross(), isWeekend(), periodOf(), pinCross() (+5 more)

### Community 23 - "Community 23"
Cohesion: 0.21
Nodes (5): Cell, One (departure date, return date) pair for one destination., The stored link with the CURRENT passenger mix applied. Passenger counts must…, What this cell costs the whole party, however the source expressed it., Keep the cheapest price seen for a given date pair.

### Community 24 - "Community 24"
Cohesion: 0.20
Nodes (6): parse_date(), Any, date, Trip lengths to search, shortest first. The two date fields bound a period, not…, Departure and return axes implied by a range plus a trip length., (populated, valid) cell counts. `valid` excludes return-before-departure pairs.…

### Community 25 - "Community 25"
Cohesion: 0.25
Nodes (4): Identifies the passenger mix a party TOTAL was priced for. Kiwi prices the real…, Cached prices are for one ticket with no child fare. Extrapolate a family total., True when the prices are narrowed at source rather than being the plain…, SearchRequest

### Community 26 - "Community 26"
Cohesion: 0.24
Nodes (7): DestinationMatrix, A full 15 x 15 grid for one destination. Missing pairs are simply absent., Cheapest cell by what the board actually shows. Ranking on raw unit price is…, DiscoveryProvider, date, Candidate destinations from the origin, as (IATA, cheapest in-window price)., Every (departure, return) pair we can find inside the window.

### Community 27 - "Community 27"
Cohesion: 0.20
Nodes (8): [dest, depart, ret], fnSrc, html, renderTimes, src, start, state, text

### Community 28 - "Community 28"
Cohesion: 0.22
Nodes (10): boardToUrl(), consume(), markSearchStale(), readNights(), searchSignature(), startSearch(), stopAutoVerify(), stopOpenFill() (+2 more)

### Community 29 - "Community 29"
Cohesion: 0.31
Nodes (3): DemoProvider, date, Aviasales deeplink: ORIGIN DDMM DEST DDMM PAX, e.g. /search/TLV0812ATH22121.

### Community 30 - "Community 30"
Cohesion: 0.47
Nodes (5): free_port(), main(), Start FlightMatrix on a free local port and open it in the browser. py -3…, The URL to hand to someone else, which is never the wildcard address., reachable_url()

### Community 31 - "Community 31"
Cohesion: 0.40
Nodes (4): Any, A live, bookable total for the real passenger mix., VerifyProvider, Protocol

### Community 33 - "Community 33"
Cohesion: 0.50
Nodes (4): main(), pick(), Download a public PyPI wheel directly, bypassing pip's pinned corporate mirror.…, Prefer a pure-python wheel, else a CPython 3.10 win_amd64 one.

### Community 34 - "Community 34"
Cohesion: 0.60
Nodes (4): describe(), gql(), Introspect Kiwi itinerary result types so we can select the right fields., unwrap()

### Community 35 - "Community 35"
Cohesion: 0.60
Nodes (4): gql(), Get the input shapes for Kiwi's calendar / one-per-city queries., show_type(), unwrap()

### Community 40 - "Community 40"
Cohesion: 0.67
Nodes (3): Can we filter by departure / return TIME, and where does time data even exist?…, show_input(), unwrap()

## Knowledge Gaps
- **41 isolated node(s):** `src`, `start`, `fnSrc`, `state`, `renderTimes` (+36 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 303 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SearchRequest` connect `Community 25` to `Community 0`, `Community 2`, `Community 4`, `Community 7`, `Community 10`, `Community 15`, `Community 23`, `Community 24`, `Community 26`, `Community 29`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `KiwiProvider` connect `Community 2` to `Community 7`, `Community 16`, `Community 23`, `Community 24`, `Community 25`, `Community 26`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Why does `Cell` connect `Community 23` to `Community 1`, `Community 2`, `Community 7`, `Community 8`, `Community 10`, `Community 15`, `Community 24`, `Community 26`, `Community 29`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `SearchRequest` (e.g. with `ExtendBody` and `FillBody`) actually correct?**
  _`SearchRequest` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Cell` (e.g. with `_apply_verified()` and `put_cells()`) actually correct?**
  _`Cell` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `render()` (e.g. with `cellAllowed()` and `matchesFilter()`) actually correct?**
  _`render()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `src`, `start`, `fnSrc` to the rest of the system?**
  _41 weakly-connected nodes found - possible documentation gaps or missing edges._