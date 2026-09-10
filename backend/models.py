"""Core data types for the fare board."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional


ISO = "%Y-%m-%d"


def parse_date(value: str) -> date:
    return datetime.strptime(value[:10], ISO).date()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    """Travelpayouts timestamps come back in a few shapes; be forgiving."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, text[:19]):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


@dataclass
class SearchRequest:
    origin: str
    depart_date: str
    return_date: str
    adults: int = 2
    children: int = 0
    currency: str = "ils"
    max_destinations: int = 20
    nonstop_only: bool = False
    max_price: float | None = None

    # Restrict which destinations are searched at all: matches IATA code, city or country.
    # Applied during discovery, so the destination budget is spent inside the filter rather
    # than on the cheapest destinations anywhere and then hidden.
    destination_filter: str = ""

    # Restrict to these ISO alpha-2 country codes (from the region tree). Like
    # destination_filter, applied at discovery so the budget is spent inside the selection.
    # Empty = no restriction.
    country_codes: list[str] = field(default_factory=list)

    # Explicit IATA destinations the user picked from the typeahead (a city or airport).
    # Composed with country_codes as a union at discovery; any that discovery does not
    # surface are probed live and folded in, so a picked airport always makes the board.
    destination_codes: list[str] = field(default_factory=list)

    # The two date fields bound a PERIOD ("travel from" .. "travel until"); the trip is
    # nights_min..nights_max long, somewhere inside it. There is no longer a date_mode:
    # the old "anchors" mode (a +-window around each of two anchor dates) was retired when
    # the UI stopped producing it, and its last remnants went with it.
    nights_min: int | None = None
    nights_max: int | None = None

    # Time-of-day windows, as local hours 0-23 inclusive. These are SEARCH parameters, not
    # display filters: the price calendar returns only a date and a price, so there is no
    # time to filter on client-side. Narrowing the window changes which flights the price
    # is drawn from (measured: a 06:00-11:00 outbound moved 12 of 14 dates and emptied one).
    depart_hours: tuple[int, int] | None = None
    return_hours: tuple[int, int] | None = None

    @staticmethod
    def _hours(value: tuple[int, int] | None) -> dict[str, int] | None:
        if not value:
            return None
        lo, hi = int(value[0]), int(value[1])
        lo, hi = max(0, min(lo, 23)), max(0, min(hi, 23))
        if (lo, hi) == (0, 23):
            return None                     # the whole day is not a filter
        return {"start": min(lo, hi), "end": max(lo, hi)}

    def depart_hours_range(self) -> dict[str, int] | None:
        return self._hours(self.depart_hours)

    def return_hours_range(self) -> dict[str, int] | None:
        return self._hours(self.return_hours)

    @property
    def has_search_filters(self) -> bool:
        """True when the prices are narrowed at source rather than being the plain cheapest.

        The cell cache is keyed only by route, dates and currency, so a filtered result is
        NOT interchangeable with an unfiltered one. Rather than widen the key, filtered
        searches bypass the cache in both directions: they neither reuse it (which silently
        returned unfiltered prices) nor write into it (which would poison it).
        """
        return bool(
            self.nonstop_only
            or self.depart_hours_range()
            or self.return_hours_range()
        )


    def nights_span(self) -> list[int]:
        """Trip lengths to search, shortest first. The two date fields bound a period, not
        a trip, so a missing nights range falls back to a sensible band rather than being
        derived from the dates."""
        lo = self.nights_min if self.nights_min is not None else 5
        hi = self.nights_max if self.nights_max is not None else max(lo + 4, 9)
        lo, hi = max(0, min(lo, hi)), max(0, max(lo, hi))
        return list(range(lo, hi + 1))

    def range_axes(self) -> tuple[list[date], list[date]]:
        """Departure and return axes implied by a range plus a trip length."""
        start, end = parse_date(self.depart_date), parse_date(self.return_date)
        if end < start:
            start, end = end, start
        span = self.nights_span()
        lo, hi = span[0], span[-1]
        last_departure = max(start, end - timedelta(days=lo))
        departs = [start + timedelta(days=i) for i in range((last_departure - start).days + 1)]
        first_return, last_return = start + timedelta(days=lo), end
        if last_return < first_return:
            last_return = first_return
        returns = [first_return + timedelta(days=i)
                   for i in range((last_return - first_return).days + 1)]
        return departs, returns

    @property
    def passengers(self) -> int:
        return self.adults + self.children

    @property
    def party_key(self) -> str:
        """Identifies the passenger mix a party TOTAL was priced for.

        Kiwi prices the real mix, so its cells are only valid for that mix. Cached under
        a route-and-dates key alone, a 2-adult board would be handed straight to a
        2-adult-3-children search and quote roughly two fifths of the true price."""
        return f"{self.adults}a{self.children}c"


    def scale(self, single_ticket_price: float, child_factor: float) -> float:
        """Cached prices are for one ticket with no child fare. Extrapolate a family total."""
        return single_ticket_price * (self.adults + self.children * child_factor)


@dataclass
class Cell:
    """One (departure date, return date) pair for one destination."""

    depart_date: str
    return_date: str
    price: float                      # single ticket, as returned by the provider
    currency: str
    airline: str | None = None
    transfers: int | None = None      # outbound stops
    return_transfers: int | None = None
    found_at: str | None = None
    expires_at: str | None = None
    link: str | None = None

    # Where the number came from, and whether it already covers the whole party.
    # Travelpayouts gives a single-adult fare that must be scaled; Kiwi gives a real
    # party total for the requested passenger mix and must NOT be scaled.
    source: str = "travelpayouts"
    is_total: bool = False

    # Filled in by the verify path.
    verified: bool = False
    # Re-priced against a real search rather than the precomputed calendar.
    checked: bool = False
    verified_total: float | None = None
    verified_at: str | None = None

    def booking_link(self, request: "SearchRequest") -> str | None:
        """The stored link with the CURRENT passenger mix applied.

        Passenger counts must not be baked into the cached link: the cell cache is keyed by
        route, dates and currency only, so a link saved during a 2-adult search would be
        handed out unchanged to a 2-adult-3-children search and silently drop the children.
        Strip whatever query is on the stored URL and rebuild it from the live request.
        """
        if not self.link or "kiwi.com" not in self.link:
            return self.link
        base = self.link.split("?", 1)[0]
        query = f"adults={request.adults}&children={request.children}&infants=0"
        # Carry the nonstop filter through too, otherwise a nonstop-only board hands you a
        # Kiwi page showing one-stop options - which looks like the filter was ignored.
        # `stopNumber=0` is the parameter that selects Kiwi's "Direct" radio (verified).
        if request.nonstop_only:
            query += "&stopNumber=0"
        return f"{base}?{query}"

    def party_total(self, request: "SearchRequest", child_factor: float) -> float:
        """What this cell costs the whole party, however the source expressed it."""
        if self.verified_total is not None:
            return self.verified_total
        if self.is_total:
            return self.price
        return request.scale(self.price, child_factor)

    @property
    def nights(self) -> int:
        return (parse_date(self.return_date) - parse_date(self.depart_date)).days

    @property
    def max_transfers(self) -> int | None:
        values = [v for v in (self.transfers, self.return_transfers) if v is not None]
        return max(values) if values else None

    @property
    def is_nonstop(self) -> bool:
        return self.max_transfers == 0

    def is_expired(self, now: datetime | None = None) -> bool:
        expiry = parse_ts(self.expires_at)
        return expiry is not None and expiry <= (now or utcnow())

    def age_hours(self, now: datetime | None = None) -> float | None:
        found = parse_ts(self.found_at)
        if found is None:
            return None
        return ((now or utcnow()) - found).total_seconds() / 3600.0

    def to_json(self, request: SearchRequest, child_factor: float, stale_after_hours: int,
                verified_stale_hours: float | None = None) -> dict[str, Any]:
        age = self.age_hours()
        # A verified cell is showing a live-checked total, which ages far faster than an
        # estimate: it is stale a lot sooner (VERIFY_FRESH_MINUTES) than a cached estimate.
        limit = (verified_stale_hours if (self.verified and verified_stale_hours is not None)
                 else stale_after_hours)
        return {
            "depart": self.depart_date,
            "ret": self.return_date,
            "nights": self.nights,
            "unit_price": round(self.price, 2),
            "estimate": round(self.party_total(request, child_factor), 2),
            "total": round(self.verified_total, 2) if self.verified_total is not None else None,
            "source": self.source,
            "is_total": self.is_total,
            "currency": self.currency,
            "airline": self.airline,
            "transfers": self.max_transfers,
            "nonstop": self.is_nonstop,
            "age_hours": round(age, 1) if age is not None else None,
            "stale": age is not None and age > limit,
            "verified": self.verified,
            "checked": self.checked,
            "link": self.booking_link(request),
        }


@dataclass
class DestinationMatrix:
    """A full 15 x 15 grid for one destination. Missing pairs are simply absent."""

    origin: str
    destination: str
    city: str | None = None
    country: str | None = None
    country_name: str = ""
    cells: dict[tuple[str, str], Cell] = field(default_factory=dict)

    def add(self, cell: Cell) -> None:
        """Keep the cheapest price seen for a given date pair."""
        key = (cell.depart_date, cell.return_date)
        existing = self.cells.get(key)
        if existing is None or cell.price < existing.price:
            self.cells[key] = cell

    def best(self, request: SearchRequest | None = None, child_factor: float = 1.0) -> Cell | None:
        """Cheapest cell by what the board actually shows.

        Ranking on raw unit price is wrong once any cell has been live-verified: a
        verified total replaces the estimate and is frequently much higher, so the cell
        with the lowest unit price is not necessarily the cheapest one on display.
        """
        if not self.cells:
            return None

        def effective(cell: Cell) -> float:
            if request is None:
                return cell.verified_total if cell.verified_total is not None else cell.price
            return cell.party_total(request, child_factor)

        return min(self.cells.values(), key=effective)

    def coverage(
        self,
        depart_dates: list[date],
        return_dates: list[date],
        nights: list[int] | None = None,
    ) -> tuple[int, int]:
        """(populated, valid) cell counts.

        `valid` excludes return-before-departure pairs. In range mode only a few trip
        lengths are askable, so counting the whole triangle would report 107/1641 for a
        grid that is actually complete.
        """
        if nights:
            allowed, wanted = set(nights), set(return_dates)
            valid = sum(
                1 for d in depart_dates for n in allowed
                if (d + timedelta(days=n)) in wanted
            )
        else:
            valid = sum(1 for d in depart_dates for r in return_dates if r >= d)
        return len(self.cells), valid

    def to_json(
        self,
        request: SearchRequest,
        depart_dates: list[date],
        return_dates: list[date],
        child_factor: float,
        stale_after_hours: int,
        verified_stale_hours: float | None = None,
    ) -> dict[str, Any]:
        populated, valid = self.coverage(
            depart_dates, return_dates,
            nights=request.nights_span(),
        )
        best = self.best(request, child_factor)
        return {
            "origin": self.origin,
            "destination": self.destination,
            "city": self.city or self.destination,
            "country": self.country,
            "country_name": self.country_name,
            "best": (best.to_json(request, child_factor, stale_after_hours, verified_stale_hours)
                     if best else None),
            "coverage": {"populated": populated, "valid": valid},
            "cells": [
                cell.to_json(request, child_factor, stale_after_hours, verified_stale_hours)
                for cell in sorted(self.cells.values(), key=lambda c: (c.depart_date, c.return_date))
            ],
        }
