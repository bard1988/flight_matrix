"""What does Kiwi's price-calendar entry actually carry?

The board infers each cell's return date as departure + nightsCount. If the calendar entry
exposes the itinerary's real inbound date, we can bin on fact instead of on an assumption.
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path("backend").resolve()))

import httpx
import config

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
TYPES = sys.argv[1:] or ["ItineraryPricesCalendar", "ItineraryPriceCalendarEntry",
                         "SearchReturnPricesCalendarInput", "NightsCountInput"]

QUERY = """
query T($name: String!) {
  __type(name: $name) {
    name
    kind
    fields { name type { name kind ofType { name kind ofType { name kind } } } }
    inputFields { name type { name kind ofType { name kind ofType { name kind } } } }
  }
}
"""


def type_name(t):
    while t:
        if t.get("name"):
            return t["name"]
        t = t.get("ofType")
    return "?"


with httpx.Client(timeout=40, verify=config.CA_BUNDLE,
                  headers={"content-type": "application/json"}) as client:
    for name in TYPES:
        r = client.post(ENDPOINT, json={"query": QUERY, "variables": {"name": name}})
        node = (r.json().get("data") or {}).get("__type")
        if not node:
            print(f"\n=== {name}: not in schema ===")
            continue
        print(f"\n=== {name} ({node['kind']}) ===")
        for key in ("fields", "inputFields"):
            for f in node.get(key) or []:
                print(f"  {f['name']:<28} {type_name(f['type'])}")
