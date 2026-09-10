"""Build data/countries.json: ISO alpha-2 -> {name, continent, subregion}.

Derived from mledoze/countries (MIT, UN M49 region + subregion), with a handful of
travel-taxonomy overrides so the region filter matches how people think about trips
rather than strict UN geography:

  - "Western Asia" is presented as "Middle East"
  - the Caucasus (Georgia, Armenia, Azerbaijan) is its own subregion, not Middle East
  - Iran is Middle East (convention: "West Asia except the Caucasus, plus Egypt and
    Turkey"); Turkey is already Western Asia so it lands there naturally
  - Egypt keeps its primary UN M49 home in Africa / Northern Africa but is ALSO listed
    under Middle East (see ALSO_IN) -- Sharm / Hurghada / Cairo are the best-connected
    "Middle East" break from TLV, and the Africa filter needs the one well-connected part
    of Africa in it. `region_of()` returns the primary; `taxonomy()` lists both.
  - Cyprus is Southern Europe (EU member)

Re-run when the upstream list changes:  py -3 data/build_countries.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SOURCE = "https://raw.githubusercontent.com/mledoze/countries/master/dist/countries.json"
OUT = Path(__file__).resolve().parent / "countries.json"

# UN M49 subregion -> our display name. Everything not listed passes through unchanged.
SUBREGION_RENAME = {
    "Western Asia": "Middle East",
    "South-Eastern Asia": "Southeast Asia",
    "Eastern Asia": "East Asia",
    "Southern Asia": "South Asia",
}

# code -> (continent, subregion) overrides, applied after the rename.
OVERRIDES = {
    "CY": ("Europe", "Southern Europe"),
    "GE": ("Asia", "Caucasus"),
    "AM": ("Asia", "Caucasus"),
    "AZ": ("Asia", "Caucasus"),
    "IR": ("Asia", "Middle East"),
    "RU": ("Europe", "Eastern Europe"),
    "MX": ("Americas", "Central America"),   # a Latin-America trip, not a US/Canada one
}

# code -> extra (continent, subregion) placements, ON TOP of the primary above. The
# country's primary home (what `region_of()` returns, what the typeahead shows) is
# unchanged; `taxonomy()` also files it under each placement here, so either branch of
# the region tree selects it.
ALSO_IN = {
    # Egypt's primary is Africa / Northern Africa (UN M49). Also list it under Middle
    # East: from TLV, Sharm / Hurghada / Cairo are the archetypal Middle East break, and
    # without this the Africa filter would exclude the best-connected part of Africa
    # while the Middle East filter would drop the obvious pick. (idea.md #15.1)
    "EG": [("Asia", "Middle East")],
}

# A couple of names read better short.
NAME_OVERRIDES = {
    "GB": "United Kingdom",
    "US": "United States",
    "TR": "Turkey",
    "AE": "United Arab Emirates",
    "CZ": "Czechia",
    "KR": "South Korea",
    "KP": "North Korea",
    "MK": "North Macedonia",
    "BA": "Bosnia and Herzegovina",
    "RU": "Russia",
    "SY": "Syria",
    "LA": "Laos",
    "MD": "Moldova",
    "TZ": "Tanzania",
    "VE": "Venezuela",
    "BO": "Bolivia",
}


def main() -> None:
    with urllib.request.urlopen(SOURCE, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    out: dict[str, dict[str, str]] = {}
    for c in raw:
        code = (c.get("cca2") or "").upper()
        if not code:
            continue
        name = NAME_OVERRIDES.get(code) or (c.get("name", {}).get("common") or code)
        continent = (c.get("region") or "").strip() or "Other"
        subregion = (c.get("subregion") or "").strip() or continent
        subregion = SUBREGION_RENAME.get(subregion, subregion)
        if code in OVERRIDES:
            continent, subregion = OVERRIDES[code]
        entry = {"name": name, "continent": continent, "subregion": subregion}
        if code in ALSO_IN:
            entry["also"] = [[c, s] for c, s in ALSO_IN[code]]
        out[code] = entry

    # Kosovo isn't ISO-official; mledoze uses "XK" which some feeds also use.
    out.setdefault("XK", {"name": "Kosovo", "continent": "Europe", "subregion": "Southern Europe"})

    OUT.write_text(json.dumps(dict(sorted(out.items())), ensure_ascii=False, indent=0),
                   encoding="utf-8")
    subs: dict[str, set[str]] = {}
    for v in out.values():
        subs.setdefault(v["continent"], set()).add(v["subregion"])
    print(f"wrote {len(out)} countries -> {OUT}")
    for cont in sorted(subs):
        print(f"  {cont}: {', '.join(sorted(subs[cont]))}")


if __name__ == "__main__":
    main()
