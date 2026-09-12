"""Provider factories shared across the backend."""
from __future__ import annotations

import os


def verifier():
    """The per-cell price verifier.

    Synthetic (instant, always answers) in demo mode so an open grid fills in front of
    you; the real Google Flights scraper otherwise. Used by `filler`, `board`, and the
    `/api/verify` endpoint so they all agree on which one is live.
    """
    if os.environ.get("FM_DEMO") == "1":
        from providers.demo import DemoProvider

        return DemoProvider()
    from providers.google_flights import GoogleFlightsProvider

    local = GoogleFlightsProvider()
    import config

    if not config.GOOGLE_RELAYS:
        return local
    from providers.relay_verify import DistributedVerifier, RelayVerifyClient

    backends = [local] + [RelayVerifyClient(url) for url in config.GOOGLE_RELAYS]
    return DistributedVerifier(backends)
