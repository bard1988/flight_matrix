# Graph Report - flight_matrix  (2026-09-06)

## Corpus Check
- Corpus is ~5,592 words - fits in a single context window. You may not need a graph.

## Summary
- 79 nodes · 107 edges · 10 communities (9 shown, 1 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 19 edges (avg confidence: 0.83)
- Token cost: 82,000 input · 6,000 output

## Community Hubs (Navigation)
- Grid Colour Scale & Frontend Cells
- Kiwi Board & Rejected Sources
- Travelpayouts Board Fill & Discovery
- Google Flights Verification & Caching
- Date Modes & Fare Board Model
- Kiwi Rate-Limit Mitigations
- Backend App & Concurrency Constraints
- Config & Install Workarounds
- Deployment & Entry Points
- Demo Mode

## God Nodes (most connected - your core abstractions)
1. `Kiwi.com board source` - 9 edges
2. `Travelpayouts / Aviasales Data API board fill` - 7 edges
3. `Destination discovery` - 7 edges
4. `backend/cache.py` - 7 edges
5. `Kiwi rate limiting (403 blocking)` - 6 edges
6. `Per-cell Google Flights verification` - 6 edges
7. `Auto cross-check toggle` - 6 edges
8. `Fill live` - 6 edges
9. `Diverging price colour ramp` - 6 edges
10. `Family-total extrapolation (FM_CHILD_FACTOR)` - 5 edges

## Surprising Connections (you probably didn't know these)
- `SQLite WAL mode` --references--> `backend/cache.py`  [INFERRED]
  README.md → README.md  _Bridges community 6 → community 3_
- `Independent per-matrix scroll viewport` --implements--> `frontend/ (index.html, app.js, styles.css)`  [INFERRED]
  README.md → README.md  _Bridges community 5 → community 0_
- `Kiwi.com board source` --semantically_similar_to--> `Travelpayouts / Aviasales Data API board fill`  [INFERRED] [semantically similar]
  README.md → README.md  _Bridges community 1 → community 2_
- `returnOnePerCityItineraries` --conceptually_related_to--> `Destination discovery`  [INFERRED]
  README.md → README.md  _Bridges community 4 → community 2_
- `Filled-grid cache reuse` --references--> `backend/cache.py`  [INFERRED]
  README.md → README.md  _Bridges community 5 → community 3_

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Kiwi rate-limit mitigation stack** — readme_kiwi_rate_limiting, readme_cache_reuse, readme_kiwi_pacing, readme_kiwi_backoff, readme_travelpayouts_fallback, readme_diagonal_fetching [EXTRACTED 0.90]
- **Board-as-ranking, click-as-truth accuracy flow** — readme_kiwi_board_source, readme_child_factor_extrapolation, readme_price_calendar_staleness, readme_auto_cross_check, readme_google_flights_verification, readme_fill_live [EXTRACTED 0.85]
- **Per-matrix diverging colour system** — readme_per_matrix_rank_scale, readme_diverging_colour_ramp, readme_yellow_reserved, readme_ramp_ink_colours, readme_cvd_check [EXTRACTED 0.85]

## Communities (10 total, 1 thin omitted)

### Community 0 - "Grid Colour Scale & Frontend Cells"
Cohesion: 0.14
Nodes (14): Cross-hair cell hover, CVD check (Machado-Oliveira-Fernandes), data/make_ramp.py, Diverging price colour ramp, Day-of-week and trip-length constraints, frontend/ (index.html, app.js, styles.css), Hatched cell (no cached data), Locate button (per card) (+6 more)

### Community 1 - "Kiwi Board & Rejected Sources"
Cohesion: 0.20
Nodes (11): Rejected flight-source survey, Filter-carrying booking links, Family-total extrapolation (FM_CHILD_FACTOR), data/estimate_error.py, Israeli carrier feed probes (El Al, Arkia, Israir), Kiwi.com board source, Kiwi price-calendar per-cell staleness, Ryanair farfnd probe (data/probe_ryanair.py) (+3 more)

### Community 2 - "Travelpayouts Board Fill & Discovery"
Cohesion: 0.22
Nodes (11): Aviasales deeplink construction, backend/airports.py, backend/board.py, data/probe_api.py, Destination discovery, Travelpayouts grid strategy (endpoint choice), 'Only destinations' filter, /aviasales/v3/prices_for_dates (+3 more)

### Community 3 - "Google Flights Verification & Caching"
Cohesion: 0.31
Nodes (10): Auto cross-check toggle, backend/cache.py, fast-flights library, Fill live, Per-cell Google Flights verification, _parse_all_itineraries, parser_version / PARSER_VERSION invalidation, Per-destination cell picking for verification (+2 more)

### Community 4 - "Date Modes & Fare Board Model"
Cohesion: 0.31
Nodes (9): 'Around these dates' mode, backend/models.py, Departure x return grid layout, Kiwi umbrella GraphQL endpoint, Multi-destination fare board, 'Anywhere in this range' mode, returnItineraryPricesCalendar, returnOnePerCityItineraries (+1 more)

### Community 5 - "Kiwi Rate-Limit Mitigations"
Cohesion: 0.32
Nodes (8): Filled-grid cache reuse, Diagonal grid fetching, Shared rate-limit backoff (wait it out visibly), Kiwi rate limiting (403 blocking), Independent per-matrix scroll viewport, Travelpayouts fallback (last resort), Widening cost model (one call per trip length), On-demand window widening

### Community 6 - "Backend App & Concurrency Constraints"
Cohesion: 0.33
Nodes (6): backend/app.py, Cell-click flight times (/api/details), Kiwi call pacing, Shared rate limiter and cache, Single-process constraint, SQLite WAL mode

### Community 7 - "Config & Install Workarounds"
Cohesion: 0.40
Nodes (5): backend/config.py, Merged CA bundle (config._ca_bundle), fast-flights install workaround, data/get_wheel.py, Travelpayouts token

### Community 8 - "Deployment & Entry Points"
Cohesion: 0.67
Nodes (3): No authentication, run.py, serve.cmd

## Knowledge Gaps
- **14 isolated node(s):** `run.py`, `Table view`, `Cross-hair cell hover`, `Locate button (per card)`, `CVD check (Machado-Oliveira-Fernandes)` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 20 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Kiwi.com board source` connect `Kiwi Board & Rejected Sources` to `Travelpayouts Board Fill & Discovery`, `Google Flights Verification & Caching`, `Date Modes & Fare Board Model`, `Kiwi Rate-Limit Mitigations`?**
  _High betweenness centrality (0.251) - this node is a cross-community bridge._
- **Why does `Travelpayouts / Aviasales Data API board fill` connect `Travelpayouts Board Fill & Discovery` to `Grid Colour Scale & Frontend Cells`, `Kiwi Board & Rejected Sources`, `Kiwi Rate-Limit Mitigations`, `Config & Install Workarounds`?**
  _High betweenness centrality (0.231) - this node is a cross-community bridge._
- **Why does `Search-driven coverage collapse` connect `Grid Colour Scale & Frontend Cells` to `Travelpayouts Board Fill & Discovery`, `Google Flights Verification & Caching`?**
  _High betweenness centrality (0.182) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Destination discovery` (e.g. with `Per-destination cell picking for verification` and `returnOnePerCityItineraries`) actually correct?**
  _`Destination discovery` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `backend/cache.py` (e.g. with `Filled-grid cache reuse` and `parser_version / PARSER_VERSION invalidation`) actually correct?**
  _`backend/cache.py` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `run.py`, `Table view`, `Cross-hair cell hover` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Grid Colour Scale & Frontend Cells` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._