"""Build and run a real Kiwi search: anywhere-from-TLV, flexible dates, 2 adults + 3 kids."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

URL = "https://api.skypicker.com/umbrella/v2/graphql"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json", "Content-Type": "application/json",
      "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=60.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)


def gql(query: str, variables: dict | None = None, name: str | None = None):
    body = {"query": query, "variables": variables or {}}
    if name:
        body["operationName"] = name
    r = client.post(URL, content=json.dumps(body))
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    data = r.json()
    if data.get("errors"):
        return data.get("data"), json.dumps(data["errors"])[:400]
    return data.get("data"), None


def unwrap(t):
    while t and not t.get("name"):
        t = t.get("ofType")
    return (t or {}).get("name", "?")


print("1) result type of returnOnePerCityItineraries")
data, err = gql(
    '{ __schema { queryType { fields { name type { kind name ofType { kind name '
    'ofType { kind name } } } } } } }'
)
fields = {f["name"]: f for f in data["__schema"]["queryType"]["fields"]}
rt = unwrap(fields["returnOnePerCityItineraries"]["type"])
print(f"   -> {rt}")

data, err = gql('{ __type(name: "%s") { kind possibleTypes { name } fields { name type { kind name ofType { kind name } } } } }' % rt)
t = data["__type"]
if t.get("possibleTypes"):
    print("   union of:", [p["name"] for p in t["possibleTypes"]])
    rt = [p["name"] for p in t["possibleTypes"]][0]
    data, err = gql('{ __type(name: "%s") { fields { name type { kind name ofType { kind name } } } } }' % rt)
    t = data["__type"]
print("   fields:", [f["name"] for f in (t.get("fields") or [])])

# Drill into the itinerary node to find price + dates + destination
for holder in ("ItinerariesResponse", "Itineraries", rt):
    data, err = gql('{ __type(name: "%s") { fields { name type { kind name ofType { kind name ofType { kind name } } } } } }' % holder)
    tt = (data or {}).get("__type")
    if tt and tt.get("fields"):
        print(f"\n   {holder} fields:")
        for f in tt["fields"]:
            print(f"      {f['name']}: {unwrap(f['type'])}")
        break

print("\n2) real query: anywhere from TLV, 2 adults + 3 children")
dep = date.today() + timedelta(days=18)
QUERY = """
query OnePerCity($search: SearchReturnInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnOnePerCityItineraries(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on Itineraries {
      itineraries {
        __typename
        id
        price { amount }
        ... on ItineraryReturn {
          outbound { departure { localTime station { code city { name country { code } } } } }
          inbound  { departure { localTime station { code } } }
        }
      }
    }
  }
}
"""
variables = {
    "search": {
        "itinerary": {
            "source": {"ids": ["Station:airport:TLV"]},
            "outboundDepartureDate": {
                "start": f"{dep.isoformat()}T00:00:00",
                "end": f"{(dep + timedelta(days=6)).isoformat()}T23:59:59",
            },
            "inboundDepartureDate": {
                "start": f"{(dep + timedelta(days=5)).isoformat()}T00:00:00",
                "end": f"{(dep + timedelta(days=14)).isoformat()}T23:59:59",
            },
        },
        "passengers": {"adults": 2, "children": 3, "infants": 0},
        "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
    },
    "filter": {},
    "options": {"currency": "ils", "locale": "en", "partner": {"affilID": "skypicker"}},
}
data, err = gql(QUERY, variables, "OnePerCity")
print("   error:", err if err else "none")
if data:
    print("   ", json.dumps(data, ensure_ascii=False)[:1500])

client.close()
