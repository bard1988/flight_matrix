"""Travelpayouts / Aviasales Data API.

This is a cache of fares real Aviasales users saw recently, not a live search. That has
two consequences the rest of the app is built around:

* coverage is driven by what other people happened to search, so unpopular date pairs are
  simply absent. A missing cell means unknown, never expensive.
* rows are single-ticket prices with no child fare, so a family total is an extrapolation.

Endpoint choice was measured, not guessed (see data/probe_api.py and data/coverage.py).
For filling a departure x return grid:

    /v2/prices/latest          29 pairs, up to 14 returns per departure   <- winner
    /aviasales/v3/prices_for_dates   16 pairs, max 3 returns per departure
    /v1/prices/calendar               8 pairs, 1 return per departure
    /v2/prices/week-matrix            0 usable pairs
    /v2/prices/month-matrix           one-way only, no return_date

`latest` was a strict superset of every other source on all 8 destinations tested, so the
others are not worth unioning in. `prices_for_dates` is still used for discovery, where
omitting `destination` answers "where can I go from here" in one call.

Rate limits: latest 300/min, prices_for_dates 600/min.
Docs: https://travelpayouts.github.io/slate/
"""
from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any, Iterable

import httpx

import config
from models import Cell, DestinationMatrix, SearchRequest, utcnow
from providers.base import MissingTokenError, ProviderError

AVIASALES_WEB = "https://www.aviasales.com"


class _RateLimiter:
    """Crude per-endpoint pacer. The limits are per minute, so space calls evenly."""

    def __init__(self) -> None:
        self._next_allowed: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, endpoint: str) -> None:
        per_minute = config.RATE_LIMITS.get(endpoint, 60)
        # Use 80% of the nominal rate; a 429 costs far more than the pacing does.
        interval = 60.0 / (per_minute * 0.8)
        with self._lock:
            now = time.monotonic()
            earliest = self._next_allowed.get(endpoint, 0.0)
            delay = max(0.0, earliest - now)
            self._next_allowed[endpoint] = max(now, earliest) + interval
        if delay:
            time.sleep(delay)


class TravelpayoutsProvider:
    def __init__(self, token: str | None = None, timeout: float = 20.0) -> None:
        self.token = (token if token is not None else config.TRAVELPAYOUTS_TOKEN).strip()
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Accept-Encoding": "gzip, deflate"},
            verify=config.CA_BUNDLE,
        )
        self._limiter = _RateLimiter()
        self.strategy = config.GRID_STRATEGY if config.GRID_STRATEGY != "auto" else "latest"

    # ------------------------------------------------------------------ transport

    def _get(self, path: str, params: dict[str, Any], endpoint: str) -> list[dict[str, Any]]:
        if not self.token:
            raise MissingTokenError(
                "No Travelpayouts token. Register at https://travelpayouts.com then copy the "
                "token from https://app.travelpayouts.com/profile/api-token into a .env file "
                "as TRAVELPAYOUTS_TOKEN=..."
            )
        self._limiter.wait(endpoint)
        url = f"{config.TRAVELPAYOUTS_HOST}{path}"
        query = {k: v for k, v in params.items() if v is not None and v != ""}
        for attempt in range(3):
            try:
                response = self._client.get(url, params=query, headers={"X-Access-Token": self.token})
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderError(f"{path} failed: {exc}") from exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code == 429:
                time.sleep(3.0 * (attempt + 1))
                continue
            if response.status_code in (401, 403):
                raise MissingTokenError(f"Travelpayouts rejected the token ({response.status_code}).")
            if response.status_code >= 500:
                if attempt == 2:
                    raise ProviderError(f"{path} returned {response.status_code}")
                time.sleep(1.5 * (attempt + 1))
                continue
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("success") is False:
                raise ProviderError(f"{path}: {payload.get('error') or payload}")
            data = payload.get("data") if isinstance(payload, dict) else payload
            if isinstance(data, dict):          # some endpoints key by destination
                flattened: list[dict[str, Any]] = []
                for value in data.values():
                    if isinstance(value, list):
                        flattened.extend(value)
                    elif isinstance(value, dict):
                        flattened.append(value)
                return flattened
            return list(data or [])
        raise ProviderError(f"{path}: rate limited after 3 attempts")

    # ------------------------------------------------------------------ parsing

    @staticmethod
    def _search_link(origin: str, destination: str, depart: str, ret: str, passengers: int) -> str:
        """Aviasales deeplink: ORIGIN DDMM DEST DDMM PAX, e.g. /search/TLV0812ATH22121."""
        def ddmm(iso: str) -> str:
            return f"{iso[8:10]}{iso[5:7]}"

        url = (
            f"{AVIASALES_WEB}/search/{origin.upper()}{ddmm(depart)}"
            f"{destination.upper()}{ddmm(ret)}{max(1, min(passengers, 9))}"
        )
        if config.TRAVELPAYOUTS_MARKER:
            url = f"{url}?marker={config.TRAVELPAYOUTS_MARKER}"
        return url

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _row_to_cell(self, row: dict[str, Any], request: SearchRequest) -> Cell | None:
        """Normalise a row from any of the price endpoints into a Cell."""
        depart = row.get("departure_at") or row.get("depart_date")
        ret = row.get("return_at") or row.get("return_date")
        price = row.get("price") if row.get("price") is not None else row.get("value")
        if not depart or not ret or price is None:
            return None
        try:
            price = float(price)
        except (TypeError, ValueError):
            return None

        transfers = self._as_int(row.get("transfers"))
        if transfers is None:
            transfers = self._as_int(row.get("number_of_changes"))
        depart, ret = str(depart)[:10], str(ret)[:10]

        link = row.get("link")
        if link and str(link).startswith("/"):
            link = f"{AVIASALES_WEB}{link}"
        elif not link:
            link = self._search_link(request.origin, str(row.get("destination") or ""), depart, ret,
                                     request.passengers)

        return Cell(
            depart_date=depart,
            return_date=ret,
            price=price,
            currency=request.currency,
            airline=row.get("airline") or row.get("gate"),
            transfers=transfers,
            return_transfers=self._as_int(row.get("return_transfers")),
            found_at=row.get("found_at"),
            expires_at=row.get("expires_at"),
            link=link,
        )

    @staticmethod
    def _month_starts(*date_lists: Iterable[date]) -> list[str]:
        """Every calendar month the windows touch, as YYYY-MM-01."""
        seen: list[str] = []
        for dates in date_lists:
            for value in dates:
                key = value.strftime("%Y-%m-01")
                if key not in seen:
                    seen.append(key)
        return sorted(seen)

    # ------------------------------------------------------------------ discovery

    def discover(
        self,
        request: SearchRequest,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> list[tuple[str, float]]:
        """Destinations reachable from the origin, ranked by cheapest fare in the month.

        `destination` is deliberately omitted, which is the one thing this API can do that
        a per-route scraper cannot: answer "where can I go" in a single call.

        Ranking is month-level rather than strictly in-window: cached coverage is thin, so
        requiring a row to already sit inside the +-7 window here would discard
        destinations whose grid the detailed pass can still fill. The caller over-fetches
        candidates and stops once enough grids come back non-empty.
        """
        cheapest: dict[str, float] = {}
        months = {d.strftime("%Y-%m") for d in depart_dates}

        for month in sorted(months):
            rows = self._get(
                "/aviasales/v3/prices_for_dates",
                {
                    "origin": request.origin.upper(),
                    "departure_at": month,
                    "one_way": "false",
                    "direct": "true" if request.nonstop_only else "false",
                    "currency": request.currency,
                    "limit": 1000,
                    "sorting": "price",
                    "market": "il",
                },
                endpoint="prices_for_dates",
            )
            for row in rows:
                destination = (row.get("destination") or "").upper()
                if not destination or destination == request.origin.upper():
                    continue
                try:
                    price = float(row.get("price") or row.get("value"))
                except (TypeError, ValueError):
                    continue
                if request.max_price is not None and request.scale(price, config.CHILD_FACTOR) > request.max_price:
                    continue
                if destination not in cheapest or price < cheapest[destination]:
                    cheapest[destination] = price

        return sorted(cheapest.items(), key=lambda item: item[1])

    # ------------------------------------------------------------------ grid fill

    def fill_matrix(
        self,
        request: SearchRequest,
        destination: str,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> DestinationMatrix:
        if self.strategy == "prices_for_dates":
            cells = self._fill_prices_for_dates(request, destination, depart_dates, return_dates)
        else:
            cells = self._fill_latest(request, destination, depart_dates, return_dates)
        return self._assemble(request, destination, cells, depart_dates, return_dates)

    def _fill_latest(
        self,
        request: SearchRequest,
        destination: str,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> list[Cell]:
        """The grid filler. One call per calendar month the window touches."""
        cells: list[Cell] = []
        for month_start in self._month_starts(depart_dates, return_dates):
            rows = self._get(
                "/v2/prices/latest",
                {
                    "origin": request.origin.upper(),
                    "destination": destination.upper(),
                    "currency": request.currency,
                    "period_type": "month",
                    "beginning_of_period": month_start,
                    "one_way": "false",
                    "limit": 1000,
                    "show_to_affiliates": "false",
                    "sorting": "price",
                },
                endpoint="latest",
            )
            for row in rows:
                row.setdefault("destination", destination.upper())
                cell = self._row_to_cell(row, request)
                if cell:
                    cells.append(cell)
        return cells

    def _fill_prices_for_dates(
        self,
        request: SearchRequest,
        destination: str,
        depart_dates: list[date],
        return_dates: list[date],
    ) -> list[Cell]:
        cells: list[Cell] = []
        for month in sorted({d.strftime("%Y-%m") for d in depart_dates}):
            rows = self._get(
                "/aviasales/v3/prices_for_dates",
                {
                    "origin": request.origin.upper(),
                    "destination": destination.upper(),
                    "departure_at": month,
                    "one_way": "false",
                    "direct": "true" if request.nonstop_only else "false",
                    "currency": request.currency,
                    "limit": 1000,
                    "sorting": "price",
                    "market": "il",
                },
                endpoint="prices_for_dates",
            )
            for row in rows:
                row.setdefault("destination", destination.upper())
                cell = self._row_to_cell(row, request)
                if cell:
                    cells.append(cell)
        return cells

    def _assemble(
        self,
        request: SearchRequest,
        destination: str,
        cells: list[Cell],
        depart_dates: list[date],
        return_dates: list[date],
    ) -> DestinationMatrix:
        matrix = DestinationMatrix(origin=request.origin.upper(), destination=destination.upper())
        lo_d, hi_d = depart_dates[0].isoformat(), depart_dates[-1].isoformat()
        lo_r, hi_r = return_dates[0].isoformat(), return_dates[-1].isoformat()
        now = utcnow()
        for cell in cells:
            if not (lo_d <= cell.depart_date <= hi_d):
                continue
            if not (lo_r <= cell.return_date <= hi_r):
                continue
            if cell.return_date < cell.depart_date:
                continue
            if cell.is_expired(now):          # never show a fare that is already gone
                continue
            if request.nonstop_only and cell.max_transfers not in (0, None):
                continue
            matrix.add(cell)
        return matrix

    def close(self) -> None:
        self._client.close()
