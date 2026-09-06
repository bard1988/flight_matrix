"""Introspect Kiwi's open umbrella GraphQL to find the flight-search query."""
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


def gql(query: str, variables: dict | None = None):
    r = client.post(URL, content=json.dumps({"query": query, "variables": variables or {}}))
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} {r.text[:120]}"
    data = r.json()
    if "errors" in data and not data.get("data"):
        return None, json.dumps(data["errors"])[:200]
    return data.get("data"), None


print("1) root query fields")
data, err = gql("{ __schema { queryType { fields { name description } } } }")
if err:
    print("   introspection blocked:", err)
else:
    fields = data["__schema"]["queryType"]["fields"]
    print(f"   {len(fields)} root fields")
    interesting = [f for f in fields
                   if any(k in f["name"].lower() for k in
                          ("search", "flight", "itiner", "onewa", "return", "price", "grid", "calendar"))]
    for f in interesting:
        desc = (f.get("description") or "").split("\n")[0][:70]
        print(f"     {f['name']:34} {desc}")
    if not interesting:
        for f in fields[:40]:
            print(f"     {f['name']}")

print("\n2) argument shape for the most likely search field")
for candidate in ("onewayItineraries", "returnItineraries", "searchReturnItinerariesV2",
                  "searchOneWayItinerariesV2", "itineraries"):
    data, err = gql(
        "query($n:String!){ __type(name:\"RootQuery\"){ fields(includeDeprecated:true){ name } } }"
    ) if False else gql(
        "{ __schema { queryType { fields { name args { name type { name kind ofType { name } } } } } } }"
    )
    if err:
        print("   ", err)
        break
    fields = {f["name"]: f for f in data["__schema"]["queryType"]["fields"]}
    if candidate in fields:
        print(f"   {candidate}:")
        for a in fields[candidate]["args"]:
            t = a["type"]
            tname = t.get("name") or (t.get("ofType") or {}).get("name") or t.get("kind")
            print(f"     - {a['name']}: {tname}")
    break

client.close()
