"""Configuration for Flight Matrix.

The Travelpayouts token is free: register at https://travelpayouts.com and copy the
token from https://app.travelpayouts.com/profile/api-token

Provide it either by creating a `.env` file next to this project root with

    TRAVELPAYOUTS_TOKEN=xxxxxxxx

or by setting the TRAVELPAYOUTS_TOKEN environment variable.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FRONTEND_DIR = ROOT / "frontend"
CACHE_DB = DATA_DIR / "cache.sqlite"


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

def _ca_bundle() -> str | bool:
    """Resolve a CA bundle for outbound HTTPS.

    This machine sits behind a TLS-inspecting corporate proxy, but not uniformly: some
    hosts are intercepted and re-signed by the corporate CA, others are reached directly
    and need the ordinary public roots. Neither bundle alone works for both, so merge
    certifi's public roots with the corporate CA into one file and use that.
    """
    override = os.environ.get("FM_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if override and Path(override).is_file():
        return override

    corporate = Path.home() / "certificates" / "amat-corporate-cas.pem"
    if not corporate.is_file():
        return True

    try:
        import certifi
    except ImportError:
        return str(corporate)

    public = Path(certifi.where())
    merged = DATA_DIR / "ca-merged.pem"
    newest = max(public.stat().st_mtime, corporate.stat().st_mtime)
    if not merged.is_file() or merged.stat().st_mtime < newest:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        merged.write_text(
            public.read_text(encoding="utf-8") + "\n" + corporate.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return str(merged)


CA_BUNDLE = _ca_bundle()

TRAVELPAYOUTS_TOKEN = os.environ.get("TRAVELPAYOUTS_TOKEN", "").strip()
TRAVELPAYOUTS_HOST = "https://api.travelpayouts.com"
TRAVELPAYOUTS_MARKER = os.environ.get("TRAVELPAYOUTS_MARKER", "").strip()

# Defaults, all overridable per search from the UI.
DEFAULT_ORIGIN = "TLV"
DEFAULT_CURRENCY = "ils"
DEFAULT_ADULTS = 2
DEFAULT_CHILDREN = 0
DEFAULT_MAX_DESTINATIONS = 20

# There is no flexibility "window" any more. The two date fields bound the travel period
# outright, so the axes come from that period plus the nights range (see
# SearchRequest.range_axes). WINDOW_DAYS / WINDOW_STEP / MAX_WINDOW_DAYS were the old
# anchor-plus-window model and are gone; the widen control now extends the period itself,
# capped client-side.

# Children are priced as `child_factor` of an adult ticket when scaling the cached
# single-ticket price into a family estimate. 1.0 is correct for the low cost carriers
# that dominate TLV and deliberately errs high rather than low.
CHILD_FACTOR = float(os.environ.get("FM_CHILD_FACTOR", "1.0"))

# Cached rows older than this are still shown but flagged stale in the UI.
STALE_AFTER_HOURS = int(os.environ.get("FM_STALE_AFTER_HOURS", "24"))

# Which Travelpayouts endpoint fills a destination grid. Measured: /v2/prices/latest
# strictly dominated every alternative (see providers/travelpayouts.py). Override with
# FM_GRID_STRATEGY=prices_for_dates to compare.
GRID_STRATEGY = os.environ.get("FM_GRID_STRATEGY", "latest")

# Bulk live fill. Measured: 4 concurrent Google Flights lookups returned 12/12 cells with
# no failures and no added latency (~1s each), so a 197-cell grid fills in about a minute.
# Raise cautiously; Google rate-limits aggressively and a block costs more than the speed.
FILL_WORKERS = int(os.environ.get("FM_FILL_WORKERS", "4"))

# Kiwi.com: which board provider to use, and how its grid fill is paced.
# Each Kiwi calendar call fills one constant-nights diagonal of the matrix.
BOARD_PROVIDER = os.environ.get("FM_BOARD_PROVIDER", "kiwi")  # kiwi | travelpayouts

# Paint the board from Travelpayouts FIRST, then upgrade it with Kiwi.
#
# Kiwi has the better data (real party totals, ~115 cells a grid) and the worse economics:
# a cold 20-destination board is 501 calls, and Kiwi blocks on volume, by IP, for minutes.
# Travelpayouts has the weaker data (single-ticket estimates, thinner coverage) and a
# documented, generous limit. Measured on the same 20-destination board:
#
#     Travelpayouts   42 calls    18s    916 cells at +30d, 495 at +90d
#     Kiwi           501 calls   234s   2300 cells
#
# Leading with the cheap source inverts the failure mode. It used to be Kiwi-then-degrade:
# spend the rate limit, hit a 403 part way through, and hand the REST of the board to
# estimates, so a block cost you a board. It is now estimate-then-improve: every card is
# populated within seconds, and Kiwi's calls are an upgrade that overlays real totals a
# grid at a time. A block now costs precision rather than the board, and because the
# upgrade is interruptible we stop bursting, which is what caused the block.
ESTIMATE_FIRST = os.environ.get("FM_ESTIMATE_FIRST", "1") != "0"
KIWI_WORKERS = int(os.environ.get("FM_KIWI_WORKERS", "4"))
# Seconds between Kiwi calls, as a STARTING point - the provider now adapts it (see
# KIWI_MAX_INTERVAL). It IP-blocks on volume and a block lasts a long time.
#
# Measured (data/bench_search.py, TLV, 30-day period, 5-9 nights):
#   0.8s  -> 1.21 calls/s achieved, i.e. the pacer, not Kiwi, was the binding constraint
#   0.0s / 8 workers -> 4.9x faster over 5 destinations with zero 403s, but over 20
#     destinations it sustained ~6.6 calls/s for ~230 calls and then took a 403 that
#     lasted over half an hour, during which the board served Travelpayouts estimates.
# So there is real headroom above 0.8s but the ceiling is volume-based and the penalty is
# severe. 0.4s is half the old interval with the adaptive backoff below as the guard.
KIWI_MIN_INTERVAL = float(os.environ.get("FM_KIWI_MIN_INTERVAL", "0.4"))
# The pacing interval is adaptive: every 403 doubles it (up to this ceiling) and a run of
# clean responses eases it back down towards KIWI_MIN_INTERVAL. A fixed interval has to be
# pessimistic enough for the worst case at all times; this one only pays for the block it
# actually meets.
KIWI_MAX_INTERVAL = float(os.environ.get("FM_KIWI_MAX_INTERVAL", "3.0"))
# Clean responses needed at the current interval before easing it back down a step.
KIWI_RECOVER_AFTER = int(os.environ.get("FM_KIWI_RECOVER_AFTER", "25"))

# Route ONLY Kiwi's calls through a proxy, to get off the datacenter IP Kiwi rate-limits
# hardest (Google and Travelpayouts stay direct). Format: http://user:pass@host:port.
# The budget guards a metered / free-trial proxy: once that many MB have gone through it
# the provider drops back to a direct connection - identical to running with no proxy,
# the existing 403 backoff just does the work again. Usage is cumulative and persisted to
# data/kiwi_proxy_usage.json; delete that file to reset (e.g. on a fresh trial).
KIWI_PROXY = os.environ.get("FM_KIWI_PROXY", "").strip() or None
KIWI_PROXY_BUDGET_MB = float(os.environ.get("FM_KIWI_PROXY_BUDGET_MB", "950"))

# A Kiwi 403 clears on its own, but with graceful per-destination fallback to the cached
# source (see board.build) a long stall is worse than an estimate. Wait a little, then
# hand the rest of the board to Travelpayouts and let the live cross-check fix the
# cheapest cells. Raise this if Kiwi is usable and you want to wait it out.
# Measured under a live block: at 40s the provider spent 8s + 16s of backoff and only
# handed over to Travelpayouts at t=26s, so the user watched three "rate-limiting" notices
# before seeing a board. The block does not clear inside that window anyway - it lasts
# minutes - so the budget was buying nothing but delay. At 12s the first 8s backoff is the
# only one that fits and the failover happens at ~9s.
KIWI_WAIT_BUDGET = float(os.environ.get("FM_KIWI_WAIT_BUDGET", "12"))
KIWI_BACKOFF_BASE = float(os.environ.get("FM_KIWI_BACKOFF_BASE", "8"))
KIWI_BACKOFF_MAX = float(os.environ.get("FM_KIWI_BACKOFF_MAX", "45"))
KIWI_MAX_ATTEMPTS = int(os.environ.get("FM_KIWI_MAX_ATTEMPTS", "8"))
# Once one call has spent the whole wait budget against a 403, treat Kiwi as blocked for
# this long and fail every other call instantly instead of re-proving it. The block is per
# egress IP and lasts minutes, so this latch is shared across provider instances and
# therefore across searches. Measured before it existed: a single 25-column grid fill spent
# 176s confirming what its first column already knew.
KIWI_BLOCK_COOLDOWN = float(os.environ.get("FM_KIWI_BLOCK_COOLDOWN", "180"))

# Reuse recently fetched cells instead of re-querying, which is what triggers the block.
# Re-querying is the main way the rate limit gets tripped, so reuse for as long as the
# board is willing to stand behind a cell. That bound already exists: STALE_AFTER_HOURS
# (24) is when the UI puts the staleness dot on a price. Reusing for 6h and then refetching
# something the interface would still have shown without comment was throwing calls away
# for no gain in freshness.
KIWI_CACHE_HOURS = float(os.environ.get("FM_KIWI_CACHE_HOURS", "24"))
# Only reuse a cached grid if it is nearly complete for the window being asked for.
# The FRACTION is the important one: a flat cell count let a half-filled grid (written by an
# older fetch strategy, or for a narrower window) satisfy a wider request forever.
# ~0.85 tolerates the diagonals that legitimately come back empty, such as 0-night trips.
CACHE_REUSE_MIN_CELLS = int(os.environ.get("FM_CACHE_REUSE_MIN_CELLS", "20"))
CACHE_REUSE_MIN_FRACTION = float(os.environ.get("FM_CACHE_REUSE_MIN_FRACTION", "0.85"))

# Re-price each card's cheapest cell with a real search. The price calendar is a
# precomputed index that goes stale per route (measured +135-166% on TLV-CTA), and the
# headline is the number the user acts on. One extra call per destination.
CHECK_HEADLINE = os.environ.get("FM_CHECK_HEADLINE", "1") != "0"
# Correcting the cheapest cell promotes the next-cheapest one, which on a route with a
# stale calendar is stale too - so re-check repeatedly until the cheapest cell on the
# card is one we priced ourselves. Bounded, because a wholly stale route would otherwise
# walk the entire grid.
#
# The loop is self-limiting on a healthy route: a correction within a few percent leaves
# the cell as the cheapest, the next pass sees it is already checked and stops, so one
# call is spent. The budget is only consumed where the calendar is actually wrong, and
# TLV-CTA (stale on some date pairs by 2.4x) needed 6-8.
CHECK_HEADLINE_MAX = int(os.environ.get("FM_CHECK_HEADLINE_MAX", "8"))
# Superseded by KIWI_NIGHTS_CEILING below; kept so an existing FM_KIWI_MAX_NIGHTS in a
# .env still lowers the ceiling rather than being silently ignored.
KIWI_MAX_NIGHTS = int(os.environ.get("FM_KIWI_MAX_NIGHTS", "0")) or 0
# Each trip length is one call. The window decides how many there are: a +-W window around
# an A-night trip spans max(0, A-2W)..A+2W, i.e. 22 lengths at +-7 but 50 at +-21. Fetch
# them all so the grid actually fills; the ceiling below only guards a runaway window.
# Set FM_KIWI_MAX_DIAGONALS to a positive number to cap it again (nearest-to-anchor kept).
# The grid is filled one RETURN date per call, so the call count is the number of return
# dates in the window: 15 at +-7, 43 at +-21. Only set this to guard a runaway window;
# when it bites, the returns nearest the one asked for are kept.
KIWI_MAX_COLUMNS = int(os.environ.get("FM_KIWI_MAX_COLUMNS", "0")) or 0
# Retired with the trip-length diagonals, which derived each cell's return date from a
# nights count and so mis-filed every overnight-outbound route. Kept only so an existing
# FM_KIWI_MAX_DIAGONALS in a .env does not fail to load.
KIWI_MAX_DIAGONALS = int(os.environ.get("FM_KIWI_MAX_DIAGONALS", "0")) or 0
KIWI_NIGHTS_CEILING = min(
    int(os.environ.get("FM_KIWI_NIGHTS_CEILING", "60")),
    KIWI_MAX_NIGHTS or 10_000,
)

# Bump when the Google Flights parsing changes in a way that alters prices. Verified rows
# stored under an older version are ignored and re-fetched rather than silently trusted.
#   1 -> fast-flights' own parser (read only payload[3]; understated many cells)
#   2 -> parse every itinerary block, including payload[2] "best flights"
# Bump when a change alters how a BOARD cell's price or dates are derived. Cells stored
# under an older version are ignored rather than served, because they are wrong, not
# merely old.
#   1 -> return date inferred as departure + nightsCount (mis-filed overnight outbounds)
#   2 -> return date pinned in the query, so each cell is the pair that was asked for
FILL_VERSION = 2

PARSER_VERSION = 2

# Discovery over-fetches candidates because cached coverage is thin: many destinations
# come back with an empty grid, so ask for more than we need and stop once enough fill.
CANDIDATE_MULTIPLIER = float(os.environ.get("FM_CANDIDATE_MULTIPLIER", "3.0"))

# Discovery seeding (idea.md #15A): when a region filter is set and the board provider's
# own "where can I go" under-delivers inside it, probe up to this many curated airports
# from that region (OurAirports, best hubs first) with one cheap Travelpayouts call each,
# and fold in the ones that actually fly from the origin. 0 disables seeding.
SEED_SHORTLIST = int(os.environ.get("FM_SEED_SHORTLIST", "150"))

# Emit every destination as a headline-only PREVIEW card the moment discovery returns,
# then upgrade each one in place as its grid fills.
#
# Discovery already returns a real party total per city in a single call, and the UI is
# master-detail: exactly one grid is on screen at a time (frontend/app.js, isExpanded).
# Filling all 20 grids before the board is usable meant ~500 calls and ~7 minutes to show
# something the user could act on, of which ~95% of the fetched cells were off screen.
# Previews make the ranked list usable after one call; the grids still arrive, just behind
# the answer instead of in front of it.
PREVIEW_FIRST = os.environ.get("FM_PREVIEW_FIRST", "1") != "0"

# How many destination grids to fill concurrently. The provider's pacer is global, so this
# does not raise the request rate - it keeps the rate budget saturated across destinations
# instead of draining the pool at the tail of each one and idling through the sequential
# headline re-check.
BOARD_PREFETCH = int(os.environ.get("FM_BOARD_PREFETCH", "3"))

# Completed boards are kept in `searches` so a link to one still resolves. They are large
# (measured: up to 1.8 MB of JSON each) and were never pruned - 69 MB of a 77 MB cache
# database. Keep the most recent N and drop the rest.
SEARCH_HISTORY_KEEP = int(os.environ.get("FM_SEARCH_HISTORY_KEEP", "50"))

# Rate limits, requests per minute, per the Travelpayouts docs.
RATE_LIMITS = {
    "prices_for_dates": 600,
    "latest": 300,
    "week_matrix": 60,
    "city_directions": 600,
}
