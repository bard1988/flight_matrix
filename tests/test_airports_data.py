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


def test_curated_hub_table_is_clean():
    """Every code in data/country_hubs.json exists and sits in the country that claims it.

    The table is hand-maintained, so a typo or a code filed under the wrong country is the
    likely defect. Both are silent at runtime (the loader drops unknown codes), which is
    exactly why they need catching here.
    """
    table = airports.load()
    hubs = airports._hub_table()
    assert len(hubs) > 100, f"only {len(hubs)} countries curated"
    for country, codes in hubs.items():
        assert codes, f"{country} has an empty hub list"
        for code in codes:
            assert code in table, f"{country}: {code} is not in the airport table"
            actual = (table[code].get("country") or "").upper()
            assert actual == country, f"{code} is filed under {country} but is in {actual}"


def test_shortlist_leads_with_each_countrys_real_hub():
    """Regression: the seeding shortlist probed the ALPHABETICALLY first large airport.

    OurAirports' `type` is a runway/facility category, so Istanbul and Izmir, Dubai and
    Al Ain, Haneda and Aomori all sit in the same "large" tier. With scheduled and tier
    tied the sort fell through to the IATA code, so a TLV -> Asia search probed ADB, AAN
    and AOJ and never probed IST, DXB or HND at all. Fails without `hub_priority`.
    """
    expected = {
        "TR": ("IST", "ADB"), "AE": ("DXB", "AAN"), "JP": ("HND", "AOJ"),
        "KR": ("ICN", "CJJ"), "CN": ("PEK", "BAV"), "EG": ("CAI", "AAC"),
        "IN": ("DEL", "AMD"), "ID": ("CGK", "AMQ"), "QA": ("DOH", "DIA"),
        "PK": ("KHI", None),  "VN": ("SGN", None), "MY": ("KUL", None),
    }
    for country, (hub, alphabetical_decoy) in expected.items():
        picked = airports.shortlist([country], 1)
        assert picked == [hub], f"{country}: expected {hub} first, got {picked}"
        if alphabetical_decoy:
            assert picked[0] != alphabetical_decoy, country


def test_asia_shortlist_contains_the_regions_actual_hubs():
    """The whole-region case the user hit: a 51-country Asian search must probe the hubs.

    Before the fix this shortlist was AAC, AAN, ABD, ADB, ADE, ... -- El Arish, Al Ain,
    Abadan, Izmir -- and contained none of these.
    """
    asia = ("AM AZ GE KZ KG TJ TM UZ CN HK JP MO MN KP KR TW BH EG IR IQ IL JO KW LB "
            "OM PS QA SA SY TR AE YE AF BD BT IN MV NP PK LK BN KH ID LA MY MM PH SG "
            "TH TL VN").split()
    picked = set(airports.shortlist(asia, 60))
    must_have = {"IST", "DXB", "DEL", "DOH", "PEK", "HND", "ICN", "CAI",
                 "CGK", "KUL", "SIN", "HKG", "TPE", "BKK", "MLE"}
    assert must_have <= picked, f"missing: {sorted(must_have - picked)}"
    # and the decoys must no longer crowd them out of a 60-slot budget
    assert not ({"AAC", "AAN", "ABD", "AOJ", "AMQ", "BAV"} & picked)


def test_hub_caches_do_not_clobber_each_other():
    """`_hubs()` (typeahead airport list) and `_hub_table()` (curated country hubs) are
    two separate lazy caches. An early version of the curated one reused the `_hub_index`
    global that already backed `_hubs()`, so whichever populated first handed its contents
    to the other's callers -- a dict where a list of (code, entry) pairs was expected.
    Priming the curated cache first is what exposes it."""
    airports.hub_priority("IST")                  # populates the curated cache
    rows = airports._hubs()                       # must still be the airport list
    assert isinstance(rows, list) and rows
    code, entry = rows[0]
    assert isinstance(code, str) and isinstance(entry, dict)
    assert airports._country_hub("GR") == "ATH"
    assert any(r["code"] == "IST" for r in airports.search_places("istanbul"))


def test_hub_priority_falls_back_for_uncurated_countries():
    """A country absent from the table keeps the old ordering rather than breaking."""
    assert airports.hub_priority("IST") == 0
    assert airports.hub_priority("ADB") > 0
    # AQ (Antarctica) is not curated; anything there ranks as uncurated, not as a hub.
    assert airports.hub_priority("ZZZ", "AQ") == 99
    assert airports.hub_priority("") == 99


def test_africa_has_a_real_shortlist_of_scheduled_airports():
    table = airports.load()
    africa = {"KE", "TZ", "ZA", "ET", "MA", "EG", "NG", "GH", "SN", "MU", "SC", "RW"}
    hubs = [
        code for code, e in table.items()
        if e.get("country") in africa and e.get("scheduled") and e.get("type") in ("large", "medium")
    ]
    assert len(hubs) > 60, len(hubs)
