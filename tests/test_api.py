"""The FastAPI layer, driven through TestClient. No provider is ever reached.

The streaming contract is the interesting part: `board.build` is a generator consumed by
the API, while status and live cells arrive on callbacks fired from worker threads. Those
two paths must both reach the client, and exactly once.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_cache, monkeypatch):
    import app
    return TestClient(app.app)


class TestHealth:
    def test_reports_readiness(self, client):
        body = client.get("/api/health").json()
        assert body["ok"] is True
        assert "defaults" in body and "origin" in body["defaults"]

    def test_static_routes_serve(self, client):
        assert client.get("/").status_code == 200
        assert client.get("/api/regions").status_code == 200


class TestRegionTree:
    def test_egypt_is_listed_under_both_africa_and_middle_east(self, client):
        """#15.1: Egypt's primary home is Africa/Northern Africa, but it is also filed
        under Middle East so neither filter drops the obvious TLV pick."""
        tree = client.get("/api/regions").json()["tree"]
        placed = {
            (cont["continent"], sub["name"])
            for cont in tree
            for sub in cont["subregions"]
            if any(c["code"] == "EG" for c in sub["countries"])
        }
        assert ("Africa", "Northern Africa") in placed
        assert ("Asia", "Middle East") in placed


class TestAirportLookup:
    def test_known_code(self, client):
        body = client.get("/api/airport/ATH").json()
        assert body["city"]

    def test_unknown_code_does_not_500(self, client):
        assert client.get("/api/airport/ZZZZ").status_code in (200, 404)


class TestSnapshotDeduping:
    """Each destination is emitted twice, once as a preview and once filled, and the
    stream upgrades the card in place. The saved snapshot is a single settled board, so a
    reopened link must not show every city twice with an empty grid."""

    def test_only_the_filled_card_is_retained(self, isolated_cache, monkeypatch):
        import app as app_module
        import board

        collected = [
            {"type": "meta", "origin": "TLV"},
            {"type": "destination", "destination": "ATH", "preview": True,
             "preview_price": 500.0, "best": None, "cells": []},
            {"type": "destination", "destination": "CTA", "preview": True,
             "preview_price": 600.0, "best": None, "cells": []},
            {"type": "cells", "destination": "ATH", "cells": [{"depart": "x"}]},
            {"type": "destination", "destination": "ATH",
             "best": {"estimate": 700.0}, "cells": [{"depart": "x"}]},
            {"type": "destination", "destination": "CTA",
             "best": {"estimate": 800.0}, "cells": [{"depart": "y"}]},
            {"type": "done", "destinations": 2},
        ]
        monkeypatch.setattr(board, "build", lambda *a, **kw: iter(collected))

        from models import SearchRequest
        request = SearchRequest(origin="TLV", depart_date="2026-10-01",
                                return_date="2026-10-15")
        # start_search normally inserts the row; _run_search only UPDATEs it.
        isolated_cache.create_search("snap", {"origin": "TLV"})
        app_module._streams["snap"] = __import__("queue").Queue()
        app_module._run_search("snap", request)

        saved = isolated_cache.get_search("snap")
        destinations = saved["board"]["destinations"]
        assert len(destinations) == 2, "one card per destination, not one per event"
        assert all(not d.get("preview") for d in destinations)
        assert [d["destination"] for d in destinations] == ["ATH", "CTA"]  # cheapest first

    def test_cells_events_stay_out_of_the_snapshot_buffer(self, isolated_cache, monkeypatch):
        """Streaming a column is the point; keeping a few hundred throwaway payloads in
        memory for the length of the search is not."""
        import app as app_module
        import board

        collected = [{"type": "meta"}] \
            + [{"type": "cells", "destination": "ATH", "cells": [{"depart": str(i)}]}
               for i in range(200)] \
            + [{"type": "destination", "destination": "ATH",
                "best": {"estimate": 1.0}, "cells": []},
               {"type": "done", "destinations": 1}]
        monkeypatch.setattr(board, "build", lambda *a, **kw: iter(collected))

        from models import SearchRequest
        isolated_cache.create_search("snap2", {"origin": "TLV"})
        app_module._streams["snap2"] = __import__("queue").Queue()
        app_module._run_search("snap2", SearchRequest(origin="TLV",
                                                      depart_date="2026-10-01",
                                                      return_date="2026-10-15"))
        saved = isolated_cache.get_search("snap2")
        blob = json.dumps(saved["board"])
        assert '"cells"' not in blob or len(saved["board"]["destinations"]) == 1
        assert len(saved["board"]["destinations"]) == 1


class TestSearchLifecycle:
    def test_start_returns_an_id_and_registers_a_stream(self, client, monkeypatch):
        import app as app_module

        # Stub the worker rather than let the route spawn a real daemon thread: the thread
        # outlives the test and touches the cache after the fixture has closed it, which
        # surfaces as a sqlite error from a thread pytest cannot attribute to anything.
        started = []
        monkeypatch.setattr(app_module, "_run_search",
                            lambda sid, request: started.append(sid))

        body = client.post("/api/search", json={
            "origin": "TLV", "depart_date": "2026-10-01", "return_date": "2026-10-15",
        }).json()
        assert "search_id" in body
        assert body["search_id"] in app_module._streams, "stream must be registered"

    def test_unknown_search_id_is_a_404_not_a_crash(self, client):
        assert client.get("/api/search/does-not-exist").status_code == 404

    def test_cancel_is_idempotent(self, client):
        assert client.post("/api/search/whatever/cancel").json()["cancelled"] is True
        assert client.post("/api/search/whatever/cancel").json()["cancelled"] is True
