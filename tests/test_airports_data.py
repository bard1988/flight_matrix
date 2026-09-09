"""The committed airport table (`data/airports.v3.json`, built by data/build_airports.py).

Guards the two things the rest of the app leans on:
  - every long-haul destination the old Travelpayouts dump missed now resolves to a real
    city + ISO country (so the region filter keeps it), and
  - real airports carry the `type` / `scheduled` signal that discovery seeding (#15A)
    ranks on, while metro codes still resolve.
"""
from __future__ import annotations

import airports


def test_metro_and_hub_codes_resolve():
    for code in ("LON", "NYC", "PAR", "MOW", "TYO"):          # metropolitan-area codes
        entry = airports.describe(code)
        assert entry["city"] and entry["country"], code

    ath = airports.describe("ATH")
    assert ath["city"] == "Athens" and ath["country"] == "GR"
    assert ath["type"] == "large" and ath["scheduled"] is True


def test_longhaul_destinations_now_have_city_and_country():
    # Precisely the places a TLV -> "Africa" / "Asia" search used to lose because the old
    # table had only the IATA code.
    expected = {
        "NBO": ("KE", "Nairobi"), "ZNZ": ("TZ", "Zanzibar"), "CPT": ("ZA", "Cape Town"),
        "JNB": ("ZA", None), "ADD": ("ET", "Addis Ababa"), "RAK": ("MA", "Marrakech"),
        "SSH": ("EG", None), "CAI": ("EG", "Cairo"), "HKT": ("TH", "Phuket"),
        "DPS": ("ID", None), "MLE": ("MV", None), "GIG": ("BR", None),
    }
    for code, (country, city) in expected.items():
        entry = airports.describe(code)
        assert entry["country"] == country, f"{code}: {entry}"
        assert entry["city"] and entry["city"] != code, f"{code}: {entry}"
        if city:
            assert entry["city"] == city, f"{code}: {entry}"


def test_table_is_worldwide_and_carries_the_ranking_signal():
    table = airports.load()
    assert len(table) > 7000
    scheduled = [e for e in table.values() if e.get("scheduled")]
    assert len(scheduled) > 3000
    # a spread of continents, not just Europe
    countries = {e["country"] for e in scheduled if e.get("country")}
    assert {"KE", "TZ", "ZA", "ET", "TH", "ID", "BR", "AU", "JP", "US"} <= countries


def test_africa_has_a_real_shortlist_of_scheduled_airports():
    table = airports.load()
    africa = {"KE", "TZ", "ZA", "ET", "MA", "EG", "NG", "GH", "SN", "MU", "SC", "RW"}
    hubs = [
        code for code, e in table.items()
        if e.get("country") in africa and e.get("scheduled") and e.get("type") in ("large", "medium")
    ]
    assert len(hubs) > 60, len(hubs)
