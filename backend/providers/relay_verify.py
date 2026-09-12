"""Spread Google Flights verify() calls across this box and any configured relays.

`config.GOOGLE_RELAYS` names zero or more relay/app.py instances (each doing lookups
from its own IP -- see deploy/provision_relay.sh). `DistributedVerifier` round-robins
calls across [local GoogleFlightsProvider] + [one RelayVerifyClient per relay], so total
safe throughput scales with the number of boxes instead of concentrating every call on
this VM's single IP. With no relays configured it behaves exactly like the bare local
provider (used directly by `providers.verifier()` in that case, so this module changes
nothing when FM_GOOGLE_RELAYS is unset).
"""
from __future__ import annotations

import itertools
import threading
from typing import Any

import httpx

from providers.base import ProviderError


class RelayVerifyClient:
    """One relay box, spoken to over its /verify endpoint."""

    def __init__(self, base_url: str, timeout: float = 45.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

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
        body = {
            "origin": origin, "destination": destination,
            "depart_date": depart_date, "return_date": return_date,
            "adults": adults, "children": children,
            "currency": currency, "nonstop_only": nonstop_only,
        }
        try:
            resp = httpx.post(f"{self.base_url}/verify", json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(f"relay {self.base_url} unreachable: {exc}") from exc
        if resp.status_code != 200:
            # The relay wraps its own ProviderError as a 502 with the message as the body
            # detail -- surface it so a caller reading the exception text still sees why.
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except ValueError:
                pass
            raise ProviderError(f"relay {self.base_url} returned {resp.status_code}: {detail}")
        return resp.json()


class DistributedVerifier:
    """Round-robins verify() calls across a fixed list of backends.

    Thread-safe: `_seed_candidates` and the Kiwi upgrade pass both build one instance and
    reuse it across a ThreadPoolExecutor, so concurrent calls must not race the counter
    onto the same backend every time (that would defeat the whole point -- every probe
    landing on this box regardless of how many relays are configured).
    """

    def __init__(self, backends: list[Any]) -> None:
        if not backends:
            raise ValueError("DistributedVerifier needs at least one backend")
        self._backends = backends
        self._counter = itertools.count()
        self._lock = threading.Lock()

    def _next(self) -> Any:
        with self._lock:
            i = next(self._counter)
        return self._backends[i % len(self._backends)]

    def verify(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._next().verify(*args, **kwargs)
