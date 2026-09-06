"""Can we filter by departure / return TIME, and where does time data even exist?

Three questions:
  1. Does Kiwi's ItinerariesFilterInput accept time-of-day windows? (would filter the
     board prices at source, not just the display)
  2. Does the price CALENDAR return any time information? (it only returned date+price)
  3. Does fast-flights accept hour bounds? (its FlightQuery signature suggested it does)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
HEAD = {"User-Agent": "Mozilla/5.0", "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=45.0, verify=config.CA_BUNDLE, headers=HEAD, follow_redirects=True)


def unwrap(t):
    while t and not t.get("name"):
        t = t.get("ofType")
    return (t or {}).get("name", "?")


def show_input(name, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if name in seen or depth > 2:
        return
    seen.add(name)
    r = client.post(ENDPOINT, content=json.dumps({"query":
        '{ __type(name: "%s") { inputFields { name type { kind name ofType '
        '{ kind name ofType { kind name } } } } } }' % name}))
    t = ((r.json().get("data") or {}).get("__type") or {})
    if not t.get("inputFields"):
        return
    pad = "  " * depth
    print(f"{pad}{name}:")
    nested = []
    for f in t["inputFields"]:
        tn = unwrap(f["type"])
        star = "  <-- TIME" if any(k in f["name"].lower() for k in ("time", "hour", "arrival", "departure")) else ""
        print(f"{pad}  {f['name']}: {tn}{star}")
        if tn.endswith("Input") and "time" in (f["name"] + tn).lower():
            nested.append(tn)
    for n in nested:
        show_input(n, depth + 1, seen)


print("=== 1. Kiwi ItinerariesFilterInput ===")
show_input("ItinerariesFilterInput")

print("\n=== 3. fast-flights FlightQuery hour bounds ===")
try:
    import inspect

    from fast_flights import FlightQuery
    sig = inspect.signature(FlightQuery)
    hours = [p for p in sig.parameters if "hour" in p or "time" in p]
    print("   hour/time parameters:", hours or "none")
except Exception as exc:
    print("   fast-flights unavailable:", exc)

client.close()
