"""Kiwi.com via its open umbrella GraphQL endpoint.

The best free source found, and the only one that gives **real party totals** for an
arbitrary passenger mix without an API key:

* `returnOnePerCityItineraries` answers "where can I go from TLV" with ~70 destinations,
  real 2-adults-3-children prices, in ONE call.
* `returnItineraryPricesCalendar` returns one dated price per departure in the requested
  span. Pinning `returnDates` to a single day makes each call fill one **column** of the
  departure x return matrix, so a +-7 grid costs 15 calls.

Unlike Travelpayouts these are party totals, not single-adult fares needing extrapolation,
and unlike Google Flights the whole board comes back in seconds rather than per cell.
Kiwi also does virtual interlining, so it surfaces self-transfer combinations no single
airline or aggregator lists.

No key, no signup. `visibleDates` is mandatory and may be combined with exactly one of
`nightsCount` / `departureDates` / `returnDates`, which is why the grid is filled a line at
a time. `returnDates` is the one to pin: `nightsCount` counts nights from ARRIVAL, so it
cannot be turned back into a return date without knowing whether the outbound flies
overnight, and guessing put unbookable prices on the board.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any

import httpx

import config
from models import Cell, DestinationMatrix, SearchRequest, parse_date
from providers.base import NoItinerariesError, ProviderError

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
KIWI_WEB = "https://www.kiwi.com"

# IATA -> kiwi.com city slug, learned during discovery and persisted, because the extend
# and re-fill paths do not re-run discovery but still need a working booking link.
_SLUG_FILE = config.DATA_DIR / "kiwi_slugs.json"
_slug_lock = threading.Lock()
_slug_cache: dict[str, str] | None = None


# --- proxy bandwidth guard ---------------------------------------------------------
# A metered proxy (typically a free-trial residential pool) carries Kiwi's calls until
# its byte budget is spent, then the provider falls back to a direct connection - the
# same behaviour as no proxy at all. Usage is cumulative and persisted, so a restart
# mid-trial does not reset the count.
_PROXY_USAGE_FILE = config.DATA_DIR / "kiwi_proxy_usage.json"
_proxy_lock = threading.Lock()


def _proxy_bytes_used() -> int:
    try:
        return int(json.loads(_PROXY_USAGE_FILE.read_text(encoding="utf-8")).get("bytes", 0))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return 0


def _proxy_budget_bytes() -> int:
    return int(config.KIWI_PROXY_BUDGET_MB * 1024 * 1024)


def _add_proxy_bytes(n: int) -> int:
    """Add to the running total, persist it, and return the new total."""
    with _proxy_lock:
        total = _proxy_bytes_used() + max(0, int(n))
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _PROXY_USAGE_FILE.write_text(json.dumps({"bytes": total}), encoding="utf-8")
        except OSError:
            pass
        return total


def proxy_status() -> dict[str, Any]:
    """For /api/health: whether a Kiwi proxy is configured and how much budget is left."""
    if not config.KIWI_PROXY:
        return {"configured": False}
    used = _proxy_bytes_used()
    return {
        "configured": True,
        "active": used < _proxy_budget_bytes(),
        "used_mb": round(used / 1024 / 1024, 1),
        "budget_mb": round(config.KIWI_PROXY_BUDGET_MB, 1),
    }


def _slugs() -> dict[str, str]:
    global _slug_cache
    with _slug_lock:
        if _slug_cache is None:
            try:
                _slug_cache = json.loads(_SLUG_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _slug_cache = {}
        return dict(_slug_cache)


def slug_for(code: str) -> str | None:
    return _slugs().get((code or "").upper())


def remember_slugs(found: dict[str, str]) -> None:
    """Persist newly seen IATA -> slug pairs."""
    global _slug_cache
    if not found:
        return
    with _slug_lock:
        if _slug_cache is None:
            try:
                _slug_cache = json.loads(_SLUG_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _slug_cache = {}
        changed = {k: v for k, v in found.items() if v and _slug_cache.get(k) != v}
        if not changed:
            return
        _slug_cache.update(changed)
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _SLUG_FILE.write_text(json.dumps(_slug_cache, indent=0, sort_keys=True),
                                  encoding="utf-8")
        except OSError:
            pass

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.kiwi.com",
    "Referer": "https://www.kiwi.com/",
}

_ONE_PER_CITY = """
query OnePerCity($search: SearchReturnInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnOnePerCityItineraries(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on OnePerCityItineraries {
      itineraries {
        price { amount }
        departureDate
        source { station { code city { slug } } }
        destination { station { code city { name slug country { code } } } }
      }
    }
  }
}
"""

_CALENDAR = """
query Cal($search: SearchReturnPricesCalendarInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnItineraryPricesCalendar(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on ItineraryPricesCalendar {
      calendar { date ratedPrice { price { amount } } }
    }
  }
}
"""


_DETAILS = """
query Details($search: SearchReturnInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnItineraries(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on Itineraries {
      itineraries {
        price { amount }
        ... on ItineraryReturn {
          duration
          outbound { duration sectorSegments { segment {
            code duration carrier { name code }
            source { localTime station { code name } }
            destination { localTime station { code name } } } } }
          inbound { duration sectorSegments { segment {
            code duration carrier { name code }
            source { localTime station { code name } }
            destination { localTime station { code name } } } } }
        }
      }
    }
  }
}
"""


def _clock(iso: str | None) -> str | None:
    """'2026-10-03T08:00:00' -> 'Sat 03 Oct 08:00'."""
    if not iso:
        return None
    try:
        from datetime import datetime
        stamp = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.strftime("%a %d %b %H:%M")


def _sector(node: dict[str, Any] | None) -> dict[str, Any] | None:
    """Flatten a Kiwi sector into legs with local times."""
    if not node:
        return None
    legs = []
    for wrapper in node.get("sectorSegments") or []:
        seg = (wrapper or {}).get("segment") or {}
        src, dst = seg.get("source") or {}, seg.get("destination") or {}
        legs.append({
            "from": ((src.get("station") or {}).get("code")),
            "to": ((dst.get("station") or {}).get("code")),
            "departs": _clock(src.get("localTime")),
            "arrives": _clock(dst.get("localTime")),
            "carrier": ((seg.get("carrier") or {}).get("name")),
            "code": seg.get("code"),
        })
    if not legs:
        return None
    duration = node.get("duration")
    return {
        "departs": legs[0]["departs"],
        "arrives": legs[-1]["arrives"],
        "stops": max(0, len(legs) - 1),
        "duration": f"{duration // 3600}h {(duration % 3600) // 60:02d}m" if duration else None,
        "carriers": ", ".join(dict.fromkeys(l["carrier"] for l in legs if l["carrier"])) or None,
        "legs": legs,
    }


def _day_start(value: date) -> str:
    return f"{value.isoformat()}T00:00:00"


def _day_end(value: date) -> str:
    return f"{value.isoformat()}T23:59:59"


class KiwiProvider:
    name = "kiwi"

    def __init__(self, timeout: float = 60.0, on_status: Any = None) -> None:
        self._timeout = timeout
        self._lock = threading.Lock()
        self.on_status = on_status
        # Called with (destination, [Cell, ...]) as each calendar column lands, so the grid
        # can paint while it fills instead of appearing whole. Set by board.build; the
        # other providers do not have it and simply never stream. Same idea as on_status.
        self.on_cells: Any = None
        # Use the proxy only if one is configured AND its budget is not already spent.
        self._proxy: str | None = (
            config.KIWI_PROXY
            if config.KIWI_PROXY and _proxy_bytes_used() < _proxy_budget_bytes()
            else None
        )
        self._client = self._new_client()
        self._next_allowed = 0.0
        self._blocked_until = 0.0
        # Adaptive pacing: start at the configured interval, widen on a 403, ease back
        # after a run of clean responses. `_clean` counts the current run.
        self._interval = max(0.0, config.KIWI_MIN_INTERVAL)
        self._clean = 0
        self.strategy = "kiwi-calendar"
        # Set when the most recent fill_matrix hit a rate limit / transport error on one
        # or more columns. board.build reads it to fail the rest of the board over to the
        # cached source instead of grinding through every remaining destination.
        self.rate_limited = False
        if self._proxy:
            self._note(
                f"Kiwi calls routed through the proxy "
                f"({_proxy_bytes_used() // (1024 * 1024)} of "
                f"{int(config.KIWI_PROXY_BUDGET_MB)} MB used)."
            )
        elif config.KIWI_PROXY:
            self._note("Kiwi proxy budget already spent - using a direct connection.")

    def _new_client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, verify=config.CA_BUNDLE,
                            headers=_HEADERS, follow_redirects=True, proxy=self._proxy)

    def _drop_proxy(self, why: str) -> None:
        """Swap to a direct connection - the byte budget is spent, or the proxy failed."""
        with self._lock:
            if not self._proxy:
                return
            self._proxy = None
            old, self._client = self._client, self._new_client()
        try:
            old.close()
        except Exception:
            pass
        self._note(f"Kiwi proxy {why} - direct connection now; rate-limit waits may return.")

    # ------------------------------------------------------------------ transport

    def _pace(self) -> None:
        """Space requests out, and hold everyone back while a block is in force.

        The wait is shared across threads: when one call gets a 403 the whole provider
        pauses, so a grid fill does not spend its retry budget many times over in parallel.

        The interval is adaptive (see `_slower` / `_faster`). A fixed interval has to be
        pessimistic enough for the worst case on every call; this one starts optimistic and
        pays for a block only once it actually meets one.
        """
        while True:
            with self._lock:
                now = time.monotonic()
                blocked_for = self._blocked_until - now
                if blocked_for <= 0:
                    wait = max(0.0, self._next_allowed - now)
                    self._next_allowed = max(now, self._next_allowed) + self._interval
                    break
            time.sleep(min(blocked_for, 2.0))
        if wait:
            time.sleep(wait)

    def _slower(self) -> None:
        """A 403 arrived: double the interval, up to the ceiling, and reset the run."""
        with self._lock:
            self._clean = 0
            widened = min(self._interval * 2, config.KIWI_MAX_INTERVAL)
            if widened <= self._interval:
                return
            self._interval = widened
        self._note(f"Kiwi pushed back - pacing Kiwi calls {widened:.2f}s apart from here.")

    def _faster(self) -> None:
        """A clean response. After a run of them, ease the interval back down a step.

        Without this the first 403 of a long board would permanently halve the rate for
        every search after it, which is how a single bad minute becomes a slow afternoon.
        """
        with self._lock:
            self._clean += 1
            if self._clean < config.KIWI_RECOVER_AFTER:
                return
            self._clean = 0
            eased = max(self._interval / 2, config.KIWI_MIN_INTERVAL)
            if eased >= self._interval:
                return
            self._interval = eased
        self._note(f"Kiwi steady - easing pacing back to {eased:.2f}s between calls.")

    def _note(self, message: str) -> None:
        if self.on_status:
            try:
                self.on_status(message)
            except Exception:
                pass

    def _gql(self, query: str, variables: dict[str, Any], operation: str) -> dict[str, Any]:
        """Run a query, waiting out a rate limit rather than failing the board.

        Kiwi blocks bursts with a bare 403 and no Retry-After, and the block clears on its
        own. Waiting is nearly always better than falling back to scaled estimates, so
        spend the configured budget before giving up.
        """
        body = json.dumps({"query": query, "variables": variables, "operationName": operation})
        last: Exception | None = None
        spent = 0.0

        for attempt in range(config.KIWI_MAX_ATTEMPTS):
            self._pace()
            try:
                response = self._client.post(ENDPOINT, content=body)
            except httpx.HTTPError as exc:
                # A flaky proxy: abandon it and retry this attempt directly rather than
                # spending the wait budget on a transport we can just drop.
                if self._proxy and isinstance(
                    exc, (httpx.ProxyError, httpx.ConnectError, httpx.ConnectTimeout)
                ):
                    self._drop_proxy(f"connection failed ({type(exc).__name__})")
                    continue
                last = exc
                time.sleep(1.5)
                continue

            if self._proxy:
                # Count what went over the proxy (request body + wire response + headers
                # overhead) and step down to direct once the budget is spent. num_bytes_
                # downloaded is the compressed wire size; over-counting here is safe.
                spent = _add_proxy_bytes(
                    len(body)
                    + (getattr(response, "num_bytes_downloaded", 0) or len(response.content))
                    + 2048
                )
                if spent >= _proxy_budget_bytes():
                    self._drop_proxy("byte budget spent")
                elif response.status_code == 407:  # Proxy Authentication Required
                    self._drop_proxy("rejected our credentials (trial expired?)")
                    continue

            if response.status_code in (403, 429):
                self._slower()
                backoff = min(config.KIWI_BACKOFF_BASE * (2 ** attempt), config.KIWI_BACKOFF_MAX)
                if spent + backoff > config.KIWI_WAIT_BUDGET:
                    last = ProviderError(
                        f"Kiwi kept rate-limiting for {int(spent)}s (HTTP "
                        f"{response.status_code}). Giving up on the live source for now."
                    )
                    break
                spent += backoff
                with self._lock:
                    self._blocked_until = max(self._blocked_until, time.monotonic() + backoff)
                self._note(
                    f"Kiwi is rate-limiting; waiting {int(backoff)}s then retrying "
                    f"({int(spent)}s of {int(config.KIWI_WAIT_BUDGET)}s budget used)."
                )
                last = ProviderError("Kiwi rate limited")
                continue

            if response.status_code != 200:
                last = ProviderError(f"Kiwi {operation}: HTTP {response.status_code}")
                continue

            if spent:
                self._note("Kiwi responded again, continuing.")
            self._faster()
            payload = response.json()
            if payload.get("errors"):
                messages = "; ".join(e.get("message", "")[:160] for e in payload["errors"][:2])
                raise ProviderError(f"Kiwi {operation}: {messages}")
            return payload.get("data") or {}
        raise ProviderError(f"Kiwi {operation} failed: {last}")

    def _options(self, request: SearchRequest) -> dict[str, Any]:
        return {
            "currency": request.currency.lower(),
            "locale": "en",
            "partner": "skypicker",
            "market": "il",
        }

    def _filter(self, request: SearchRequest) -> dict[str, Any]:
        """Search-side filters: stops, and time-of-day windows.

        Time has to be applied here rather than in the UI, because the price calendar
        returns only a date and a price - there is no departure time to filter on later.
        A narrower window genuinely reprices the board: measured on TLV-ATH, a 06:00-11:00
        outbound moved 12 of 14 dates and emptied one.
        """
        flt: dict[str, Any] = {}
        if request.nonstop_only:
            flt["maxStopsCount"] = 0
        out = request.depart_hours_range()
        back = request.return_hours_range()
        if out:
            flt["outbound"] = {"departureHours": out}
        if back:
            flt["inbound"] = {"departureHours": back}
        return flt

    def _passengers(self, request: SearchRequest) -> dict[str, Any]:
        return {"adults": request.adults, "children": request.children, "infants": 0}

    @staticmethod
    def _source_ids(origin: str) -> dict[str, Any]:
        return {"ids": [f"Station:airport:{origin.upper()}"]}

    # ------------------------------------------------------------------ discovery

    def discover(
        self,
        request: SearchRequest,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> list[tuple[str, float]]:
        """~70 destinations with real party prices, in a single call."""
        variables = {
            "search": {
                "itinerary": {
                    "source": self._source_ids(request.origin),
                    "outboundDepartureDate": {
                        "start": _day_start(depart_dates[0]), "end": _day_end(depart_dates[-1]),
                    },
                    "inboundDepartureDate": {
                        "start": _day_start(return_dates[0]), "end": _day_end(return_dates[-1]),
                    },
                },
                "passengers": self._passengers(request),
                "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
            },
            "filter": self._filter(request),
            "options": self._options(request),
        }
        data = self._gql(_ONE_PER_CITY, variables, "OnePerCity")
        node = data.get("returnOnePerCityItineraries") or {}
        if node.get("error"):
            raise ProviderError(f"Kiwi discovery: {node['error']}")

        found: dict[str, float] = {}
        slugs: dict[str, str] = {}
        self.cities: dict[str, dict[str, str]] = getattr(self, "cities", {})
        for item in node.get("itineraries") or []:
            # Kiwi's booking URLs are keyed by city slug, so harvest them while we are here.
            src_station = (item.get("source") or {}).get("station") or {}
            src_slug = ((src_station.get("city") or {}).get("slug")) or ""
            if src_station.get("code") and src_slug:
                slugs[src_station["code"].upper()] = src_slug
            try:
                price = float(item["price"]["amount"])
            except (KeyError, TypeError, ValueError):
                continue
            station = (item.get("destination") or {}).get("station") or {}
            code = (station.get("code") or "").upper()
            if not code or code == request.origin.upper():
                continue
            if request.max_price is not None and price > request.max_price:
                continue
            city = station.get("city") or {}
            self.cities[code] = {
                "city": city.get("name") or code,
                "country": ((city.get("country") or {}).get("code") or ""),
            }
            if city.get("slug"):
                slugs[code] = city["slug"]
            if code not in found or price < found[code]:
                found[code] = price

        remember_slugs(slugs)
        return sorted(found.items(), key=lambda kv: kv[1])

    # ------------------------------------------------------------------ grid fill

    def _return_column(
        self,
        request: SearchRequest,
        destination: str,
        depart_dates: list[date],
        ret: date,
    ) -> list[Cell]:
        """One call = one COLUMN of the matrix: every departure date for one fixed return.

        The return date is pinned rather than inferred from a trip length. `nightsCount`
        counts nights spent AT THE DESTINATION, measured from ARRIVAL, so an overnight
        outbound shifts the return a day later than departure + nights: Wizz TLV-CTA leaves
        22:55 and lands 01:15, so a 12-night request comes back as a trip returning 13 days
        after departure. Filing those under departure + nights put a real price on a date
        pair that cannot be booked - the board quoted 853 for a Catania trip that actually
        costs 2,289, and cells whose true itinerary fell outside the grid showed a price
        for a trip with no flights at all. Athens hid the bug because its daytime flights
        arrive the same day and never shift.

        Pinning the return removes the inference: every cell is the pair we asked for.
        Measured on TLV-CTA, all 8 departures came back within ~1% of a full search for
        that exact pair.
        """
        # A departure after the return is not a trip, and Kiwi is asked for one contiguous
        # span, so clamp the window rather than paying for dates that cannot produce a cell.
        first, last = depart_dates[0], min(depart_dates[-1], ret)
        if last < first:
            return []
        variables = {
            "search": {
                "source": self._source_ids(request.origin),
                "destination": {"ids": [f"Station:airport:{destination.upper()}"]},
                "visibleDates": {"start": _day_start(first), "end": _day_end(last)},
                "returnDates": {"start": _day_start(ret), "end": _day_end(ret)},
                "passengers": self._passengers(request),
                "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
            },
            "filter": self._filter(request),
            "options": self._options(request),
        }
        data = self._gql(_CALENDAR, variables, "Cal")
        node = data.get("returnItineraryPricesCalendar") or {}
        if node.get("error"):
            return []

        cells: list[Cell] = []
        for item in node.get("calendar") or []:
            try:
                depart = date.fromisoformat(str(item["date"])[:10])
                price = float(item["ratedPrice"]["price"]["amount"])
            except (KeyError, TypeError, ValueError):
                continue
            if depart > ret:
                continue
            cells.append(
                Cell(
                    depart_date=depart.isoformat(),
                    return_date=ret.isoformat(),
                    price=price,
                    currency=request.currency,
                    source="kiwi",
                    is_total=True,          # already a party total, do not scale by pax
                    link=self._deeplink(request, destination, depart, ret),
                )
            )
        return cells

    def _deeplink(self, request: SearchRequest, destination: str, depart: date, ret: date) -> str:
        """A kiwi.com search URL that actually prefills.

        Kiwi's search path takes CITY SLUGS ("tel-aviv-israel/venice-italy"), not IATA
        codes: a URL built from codes loads with both From and To empty and "Nothing here
        yet ...". Slugs come from the API during discovery and are cached to disk, because
        the extend and re-fill paths do not re-run discovery.
        """
        src, dst = slug_for(request.origin), slug_for(destination)
        if not src or not dst:
            # Rather than hand out a link that silently loads an empty search.
            return "https://www.kiwi.com/en/"
        # Deliberately NO passenger query here: this URL is cached under a key that has no
        # passenger counts in it, so baking them in would serve a 2-adult link to a
        # 2-adult-3-children search. Cell.booking_link() appends the live counts.
        return (f"{KIWI_WEB}/en/search/results/{src}/{dst}/"
                f"{depart.isoformat()}/{ret.isoformat()}")

    def itinerary_details(
        self,
        request: SearchRequest,
        destination: str,
        depart: str,
        ret: str,
    ) -> dict[str, Any]:
        """Actual flight times for one date pair, from the same source as the board price.

        The price calendar carries no times, so this is a separate full search for that one
        cell. It works at any horizon, unlike the Google cross-check, which has no data
        beyond about a year out.
        """
        variables = {
            "search": {
                "itinerary": {
                    "source": self._source_ids(request.origin),
                    "destination": {"ids": [f"Station:airport:{destination.upper()}"]},
                    "outboundDepartureDate": {"start": f"{depart}T00:00:00",
                                              "end": f"{depart}T23:59:59"},
                    "inboundDepartureDate": {"start": f"{ret}T00:00:00",
                                             "end": f"{ret}T23:59:59"},
                },
                "passengers": self._passengers(request),
                "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
            },
            "filter": self._filter(request),
            "options": self._options(request),
        }
        data = self._gql(_DETAILS, variables, "Details")
        node = data.get("returnItineraries") or {}
        if node.get("error"):
            raise ProviderError(f"Kiwi details: {node['error']}")

        best: dict[str, Any] | None = None
        for item in node.get("itineraries") or []:
            try:
                price = float((item.get("price") or {})["amount"])
            except (KeyError, TypeError, ValueError):
                continue
            if best is None or price < best["price"]:
                best = {
                    "price": price,
                    "outbound": _sector(item.get("outbound")),
                    "inbound": _sector(item.get("inbound")),
                }
        if best is None:
            raise NoItinerariesError(
                "Kiwi returned no itineraries for that exact date pair.")
        return best

    def fill_matrix(
        self,
        request: SearchRequest,
        destination: str,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> DestinationMatrix:
        # One call per RETURN date, each covering the whole departure window (the calendar
        # returns exactly the span asked for - verified up to 90 days). A +-7 window is 15
        # calls, fewer than the 22 the trip-length diagonals used to need, and every cell is
        # the date pair actually requested instead of one derived from a nights count that
        # counts from arrival. See _return_column.
        columns = [r for r in return_dates if r >= depart_dates[0]]

        # Only a narrow band of trip lengths is wanted, so for each return date ask only
        # about the departures that can produce one. (This used to branch on
        # request.is_range, with an else-arm that spanned everything up to
        # KIWI_NIGHTS_CEILING for the retired anchors mode. There is only one mode now.)
        spans: dict[date, list[date]] = {}
        nights = request.nights_span()
        lo_n, hi_n = nights[0], nights[-1]
        for r in columns:
            window = [d for d in depart_dates if lo_n <= (r - d).days <= hi_n]
            if window:
                spans[r] = window
        columns = [r for r in columns if r in spans]

        # Only guards a runaway window; keeps the returns nearest the one actually asked for.
        if config.KIWI_MAX_COLUMNS and len(columns) > config.KIWI_MAX_COLUMNS:
            anchor = parse_date(request.return_date)
            columns = sorted(
                sorted(columns, key=lambda r: abs((r - anchor).days))[:config.KIWI_MAX_COLUMNS]
            )

        matrix = DestinationMatrix(origin=request.origin.upper(), destination=destination.upper())
        lo_d, hi_d = depart_dates[0].isoformat(), depart_dates[-1].isoformat()
        self.rate_limited = False

        def run(ret: date) -> list[Cell]:
            try:
                return self._return_column(request, destination, spans[ret], ret)
            except ProviderError:
                # A column failed - almost always the 403 rate limit (or a transport
                # blip). Flag it so the board can fail over rather than serve a grid
                # that is sparse only because Kiwi throttled us.
                self.rate_limited = True
                return []

        # as_completed, not map: map yields in submission order, so a column that finished
        # early would still wait behind a slow one before it could be streamed. Nothing
        # downstream cares about column order, and the point here is to emit each one the
        # moment it lands.
        with ThreadPoolExecutor(max_workers=config.KIWI_WORKERS) as pool:
            futures = [pool.submit(run, ret) for ret in columns]
            for future in as_completed(futures):
                fresh = []
                for cell in future.result():
                    if lo_d <= cell.depart_date <= hi_d:
                        matrix.add(cell)
                        fresh.append(cell)
                if fresh and self.on_cells:
                    # A listener must never be able to kill a grid fill.
                    try:
                        self.on_cells(destination, fresh)
                    except Exception:
                        pass

        info = getattr(self, "cities", {}).get(destination.upper())
        if info:
            matrix.city, matrix.country = info["city"], info["country"]
        return matrix

    def close(self) -> None:
        self._client.close()
