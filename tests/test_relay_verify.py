"""Distributing Google Flights verify() calls across the local box + relays.

No network: RelayVerifyClient's httpx.post is monkeypatched, and DistributedVerifier's
round-robin is exercised against plain fake backends.
"""
from __future__ import annotations

import pytest

from providers.base import ProviderError
from providers.relay_verify import DistributedVerifier, RelayVerifyClient


class _FakeBackend:
    def __init__(self, name):
        self.name = name
        self.calls = 0

    def verify(self, *a, **kw):
        self.calls += 1
        return {"total": 100, "backend": self.name}


class TestDistributedVerifier:
    def test_needs_at_least_one_backend(self):
        with pytest.raises(ValueError):
            DistributedVerifier([])

    def test_round_robins_across_backends_in_order(self):
        a, b, c = _FakeBackend("a"), _FakeBackend("b"), _FakeBackend("c")
        v = DistributedVerifier([a, b, c])
        seen = [v.verify()["backend"] for _ in range(7)]
        assert seen == ["a", "b", "c", "a", "b", "c", "a"]

    def test_a_single_backend_just_gets_every_call(self):
        a = _FakeBackend("a")
        v = DistributedVerifier([a])
        for _ in range(5):
            v.verify()
        assert a.calls == 5

    def test_passes_args_and_kwargs_through_unchanged(self):
        captured = {}

        class Recording:
            def verify(self, *a, **kw):
                captured["args"], captured["kwargs"] = a, kw
                return {"total": 1}

        v = DistributedVerifier([Recording()])
        v.verify("TLV", "JFK", "2026-10-01", "2026-10-08", 2, 0,
                 currency="ils", nonstop_only=True)
        assert captured["args"] == ("TLV", "JFK", "2026-10-01", "2026-10-08", 2, 0)
        assert captured["kwargs"] == {"currency": "ils", "nonstop_only": True}

    def test_is_thread_safe_no_backend_is_skipped_or_double_hit_unevenly(self):
        """The counter is shared across a ThreadPoolExecutor in real use (board.py's
        seeding pass); a racy increment would let two threads land on the same backend
        and starve another, silently defeating the whole point of having relays."""
        import threading

        backends = [_FakeBackend(str(i)) for i in range(4)]
        v = DistributedVerifier(backends)
        n_calls = 400

        def hit():
            v.verify()

        threads = [threading.Thread(target=hit) for _ in range(n_calls)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total = sum(b.calls for b in backends)
        assert total == n_calls
        # Perfectly even since n_calls is a multiple of len(backends); a race would show
        # up as an uneven split (some backend under- or over-hit).
        assert all(b.calls == n_calls // len(backends) for b in backends)


class TestRelayVerifyClient:
    def test_posts_to_verify_and_returns_the_json_body(self, monkeypatch):
        seen = {}

        def fake_post(url, json, timeout):
            seen["url"], seen["json"], seen["timeout"] = url, json, timeout

            class Resp:
                status_code = 200

                def json(self):
                    return {"total": 456}
            return Resp()

        monkeypatch.setattr("providers.relay_verify.httpx.post", fake_post)
        client = RelayVerifyClient("http://10.0.0.126:8080")
        result = client.verify("TLV", "JFK", "2026-10-01", "2026-10-08", 2, 0, "ils", False)

        assert result == {"total": 456}
        assert seen["url"] == "http://10.0.0.126:8080/verify"
        assert seen["json"]["origin"] == "TLV"
        assert seen["json"]["destination"] == "JFK"

    def test_a_non_200_response_raises_providererror_with_the_relays_detail(self, monkeypatch):
        def fake_post(url, json, timeout):
            class Resp:
                status_code = 502
                text = "boom"

                def json(self):
                    return {"detail": "no itineraries"}
            return Resp()

        monkeypatch.setattr("providers.relay_verify.httpx.post", fake_post)
        client = RelayVerifyClient("http://10.0.0.126:8080")
        with pytest.raises(ProviderError, match="no itineraries"):
            client.verify("TLV", "JFK", "2026-10-01", "2026-10-08", 2, 0, "ils")

    def test_a_transport_error_raises_providererror_not_the_raw_httpx_exception(self, monkeypatch):
        import httpx

        def fake_post(url, json, timeout):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr("providers.relay_verify.httpx.post", fake_post)
        client = RelayVerifyClient("http://10.0.0.126:8080")
        with pytest.raises(ProviderError, match="unreachable"):
            client.verify("TLV", "JFK", "2026-10-01", "2026-10-08", 2, 0, "ils")


class TestVerifierFactory:
    def test_no_relays_configured_returns_the_bare_local_provider(self, monkeypatch):
        import config
        import providers
        from providers.google_flights import GoogleFlightsProvider

        monkeypatch.setattr(config, "GOOGLE_RELAYS", [])
        monkeypatch.delenv("FM_DEMO", raising=False)
        result = providers.verifier()
        assert isinstance(result, GoogleFlightsProvider)

    def test_relays_configured_returns_a_distributed_verifier_over_local_plus_each_relay(self, monkeypatch):
        import config
        import providers

        monkeypatch.setattr(config, "GOOGLE_RELAYS",
                             ["http://10.0.0.126:8080", "http://10.0.0.5:8080"])
        monkeypatch.delenv("FM_DEMO", raising=False)
        result = providers.verifier()
        assert isinstance(result, DistributedVerifier)
        assert len(result._backends) == 3   # local + 2 relays
        assert isinstance(result._backends[1], RelayVerifyClient)
        assert result._backends[1].base_url == "http://10.0.0.126:8080"
        assert isinstance(result._backends[2], RelayVerifyClient)
        assert result._backends[2].base_url == "http://10.0.0.5:8080"

    def test_demo_mode_ignores_relays_entirely(self, monkeypatch):
        import config
        import providers
        from providers.demo import DemoProvider

        monkeypatch.setattr(config, "GOOGLE_RELAYS", ["http://10.0.0.126:8080"])
        monkeypatch.setenv("FM_DEMO", "1")
        result = providers.verifier()
        assert isinstance(result, DemoProvider)
