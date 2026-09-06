"""Introspect Kiwi itinerary result types so we can select the right fields."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

URL = "https://api.skypicker.com/umbrella/v2/graphql"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json", "Content-Type": "application/json",
      "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=45.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)


def gql(q):
    r = client.post(URL, content=json.dumps({"query": q}))
    return r.json().get("data") if r.status_code == 200 else None


def unwrap(t):
    while t and not t.get("name"):
        t = t.get("ofType")
    return (t or {}).get("name", "?")


def describe(name, indent=0):
    d = gql('{ __type(name: "%s") { kind possibleTypes { name } fields { name type '
            '{ kind name ofType { kind name ofType { kind name } } } } } }' % name)
    t = (d or {}).get("__type")
    if not t:
        print("  " * indent + f"{name}: <not found>")
        return
    pad = "  " * indent
    if t.get("possibleTypes"):
        print(f"{pad}{name} = union/interface of {[p['name'] for p in t['possibleTypes']]}")
    if t.get("fields"):
        print(f"{pad}{name}:")
        for f in t["fields"]:
            print(f"{pad}  {f['name']}: {unwrap(f['type'])}")


for tn in ("Itinerary", "ItineraryReturn", "Sector", "SegmentSector", "TripSegment",
           "Money", "Price", "Station", "City"):
    describe(tn)
    print()

client.close()
