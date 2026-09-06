"""Provider protocol.

Two very different kinds of source sit behind this interface:

* a cached price warehouse (Travelpayouts) which can answer "where can I go" and fill a
  whole grid in one call, but has no passenger parameter, and
* a live scraper (Google Flights) which prices a real passenger mix but only one date
  pair at a time.

Only the first implements `discover` / `fill_matrix`; only the second implements `verify`.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from models import DestinationMatrix, SearchRequest


class DiscoveryProvider(Protocol):
    def discover(
        self,
        request: SearchRequest,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> list[tuple[str, float]]:
        """Candidate destinations from the origin, as (IATA, cheapest in-window price)."""

    def fill_matrix(
        self,
        request: SearchRequest,
        destination: str,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> DestinationMatrix:
        """Every (departure, return) pair we can find inside the window."""


class VerifyProvider(Protocol):
    def verify(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str,
        adults: int,
        children: int,
        currency: str,
        nonstop_only: bool = False,
    ) -> dict[str, Any]:
        """A live, bookable total for the real passenger mix."""


class ProviderError(RuntimeError):
    """Raised for anything the caller should surface rather than retry blindly."""


class MissingTokenError(ProviderError):
    pass


class NoItinerariesError(ProviderError):
    """A full search for one exact date pair came back empty.

    Distinct from the other provider errors because it is a fact about the route, not a
    transport failure: retrying will not help, and a board cell claiming a price for that
    pair is simply wrong and should be dropped rather than shown."""

