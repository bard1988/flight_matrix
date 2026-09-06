"""Get the input shapes for Kiwi's calendar / one-per-city queries."""
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


def gql(query: str):
    r = client.post(URL, content=json.dumps({"query": query}))
    if r.status_code != 200:
        return None
    return r.json().get("data")


def unwrap(t: dict) -> str:
    if not t:
        return "?"
    if t.get("name"):
        return t["name"] + ("!" if t.get("kind") == "NON_NULL" else "")
    inner = unwrap(t.get("ofType") or {})
    return f"[{inner}]" if t.get("kind") == "LIST" else inner + ("!" if t.get("kind") == "NON_NULL" else "")


def show_type(name: str, depth: int = 0, seen: set | None = None) -> None:
    seen = seen if seen is not None else set()
    if name in seen or depth > 2:
        return
    seen.add(name)
    data = gql(
        "{ __type(name: \"%s\") { kind inputFields { name type { kind name ofType "
        "{ kind name ofType { kind name ofType { kind name } } } } } } }" % name
    )
    t = (data or {}).get("__type")
    if not t or not t.get("inputFields"):
        return
    pad = "  " * depth
    print(f"{pad}{name}:")
    nested = []
    for f in t["inputFields"]:
        tn = unwrap(f["type"])
        print(f"{pad}  {f['name']}: {tn}")
        base = tn.strip("[]!")
        if base.endswith("Input") or base.endswith("InputType"):
            nested.append(base)
    for n in nested:
        show_type(n, depth + 1, seen)


print("=== args of the two key queries ===")
data = gql("{ __schema { queryType { fields { name args { name type { kind name ofType { name } } } } } } }")
fields = {f["name"]: f for f in data["__schema"]["queryType"]["fields"]}
for q in ("returnItineraryPricesCalendar", "returnOnePerCityItineraries", "returnItineraries"):
    if q in fields:
        print(f"\n{q}(")
        for a in fields[q]["args"]:
            print(f"    {a['name']}: {unwrap(a['type'])}")
        print(")")

print("\n=== input type details ===")
for tname in ("SearchReturnInput", "SearchOnewayInput", "ItinerariesFilterInput",
              "ItinerariesOptionsInput", "PassengersInput", "TripInput"):
    show_type(tname)
    print()

client.close()
