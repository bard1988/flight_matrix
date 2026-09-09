"""Build data/airports.v3.json: IATA code -> {city, country, name?, type?, scheduled?, lat?, lon?}.

Two sources, merged:

  - **OurAirports** (`airports.csv`, public domain) — every airport with an IATA code,
    plus the `type` (large / medium / small) and `scheduled_service` signal that
    discovery seeding (idea.md #15A) ranks candidates on, and coordinates. OurAirports
    has no concept of a metropolitan-area code.
  - **Travelpayouts** (`cities.json`, keyless) — the metro codes (LON, PAR, NYC, MIL,
    MOW, ...) and city-level codes that the Kiwi / Travelpayouts boards hand back as
    destinations. Filtered to `has_flightable_airport`.

On a code that exists in both, the city/metro name and country win (the board is keyed on
those far more often than on a specific terminal), but any coordinates / type / airport
name from the OurAirports row are kept.

Everything downstream degrades to the bare IATA code if this file is missing, same as
`countries.json`. Re-run when either upstream changes:

    py -3 data/build_airports.py
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

OURAIRPORTS = "https://davidmegginson.github.io/ourairports-data/airports.csv"
TP_CITIES = "https://api.travelpayouts.com/data/en/cities.json"
OUT = Path(__file__).resolve().parent / "airports.v3.json"

# OurAirports `type` -> our short tier. Heliports, seaplane bases, balloonports and
# closed fields are dropped: nothing schedules a board-worthy flight from them.
TIER = {"large_airport": "large", "medium_airport": "medium", "small_airport": "small"}

_UA = {"User-Agent": "flightmatrix-build (+https://github.com/bard1988/flight_matrix)"}


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=60) as resp:
        return resp.read()


def _iata_ok(code: str) -> bool:
    return len(code) == 3 and code.isalpha()


def main() -> None:
    index: dict[str, dict[str, object]] = {}

    # --- OurAirports: airport-level, with the ranking signal ---
    airports = csv.DictReader(io.StringIO(_fetch(OURAIRPORTS).decode("utf-8")))
    for row in airports:
        code = (row["iata_code"] or "").upper()
        tier = TIER.get(row["type"])
        if not tier or not _iata_ok(code):
            continue
        entry: dict[str, object] = {
            "city": (row["municipality"] or row["name"] or code).strip(),
            "country": (row["iso_country"] or "").upper(),
            "name": (row["name"] or "").strip(),
            "type": tier,
            "scheduled": row["scheduled_service"] == "yes",
        }
        try:
            entry["lat"] = round(float(row["latitude_deg"]), 4)
            entry["lon"] = round(float(row["longitude_deg"]), 4)
        except (TypeError, ValueError):
            pass
        index[code] = entry
    from_airports = len(index)

    # --- Travelpayouts: metro + city codes the boards return ---
    cities = json.loads(_fetch(TP_CITIES).decode("utf-8"))
    metro_only = 0
    for city in cities:
        code = (city.get("code") or "").upper()
        if not _iata_ok(code) or not city.get("has_flightable_airport"):
            continue
        existing = index.get(code, {})
        if not existing:
            metro_only += 1
        index[code] = {
            **existing,
            "city": city.get("name") or code,
            "country": (city.get("country_code") or "").upper(),
        }

    OUT.write_text(
        json.dumps(dict(sorted(index.items())), ensure_ascii=False, indent=0),
        encoding="utf-8",
    )

    scheduled = sum(1 for e in index.values() if e.get("scheduled"))
    countries = {e["country"] for e in index.values() if e.get("country")}
    print(f"wrote {len(index)} codes -> {OUT}")
    print(f"  {from_airports} from OurAirports ({scheduled} with scheduled service), "
          f"{metro_only} metro/city-only from Travelpayouts")
    print(f"  {len(countries)} countries")


if __name__ == "__main__":
    main()
