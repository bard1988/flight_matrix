"""Kiwi's returnItineraryPricesCalendar: a real round-trip date grid, keyless."""
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
client = httpx.Client(timeout=90.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)


def gql(q, v=None, name=None):
    body = {"query": q, "variables": v or {}}
    if name:
        body["operationName"] = name
    r = client.post(URL, content=json.dumps(body))
    try:
        payload = r.json()
    except Exception:
        return None, f"HTTP {r.status_code} {r.text[:120]}"
    if payload.get("errors"):
        return payload.get("data"), "; ".join(e.get("message", "")[-260:] for e in payload["errors"][:3])
    return payload.get("data"), None


def unwrap(t):
    while t and not t.get("name"):
        t = t.get("ofType")
    return (t or {}).get("name", "?")


print("1) calendar input + result shape")
for tn in ("SearchReturnPricesCalendarInput", "ItineraryPricesCalendarResult",
           "ItineraryPricesCalendar", "PriceCalendarItem"):
    d, e = gql('{ __type(name: "%s") { kind possibleTypes { name } inputFields { name type '
               '{ kind name ofType { kind name } } } fields { name type { kind name ofType '
               '{ kind name ofType { kind name } } } } } }' % tn)
    t = (d or {}).get("__type")
    if not t:
        continue
    print(f"  {tn} ({t.get('kind')})")
    if t.get("possibleTypes"):
        print("    union of:", [p["name"] for p in t["possibleTypes"]])
    for f in (t.get("inputFields") or t.get("fields") or []):
        print(f"    {f['name']}: {unwrap(f['type'])}")

print("\n2) run the calendar for TLV -> LCA")
dep = date.today() + timedelta(days=18)
d, e = gql('{ __type(name: "RatedPrice") { fields { name type { kind name ofType { kind name } } } } }')
print("   RatedPrice fields:", [f["name"] for f in ((d or {}).get("__type") or {}).get("fields") or []])

QUERY = """
query Cal($search: SearchReturnPricesCalendarInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnItineraryPricesCalendar(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError { error: message }
    ... on ItineraryPricesCalendar {
      calendar { date ratedPrice { price { amount } } }
    }
  }
}
"""

for nights in (5, 7, 9):
    variables = {
        "search": {
            "source": {"ids": ["Station:airport:TLV"]},
            "destination": {"ids": ["Station:airport:LCA"]},
            "visibleDates": {
                "start": f"{dep.isoformat()}T00:00:00",
                "end": f"{(dep + timedelta(days=14)).isoformat()}T23:59:59",
            },
            "nightsCount": {"start": nights, "end": nights},
            "passengers": {"adults": 2, "children": 3, "infants": 0},
            "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
        },
        "filter": {},
        "options": {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"},
    }
    data, err = gql(QUERY, variables, "Cal")
    node = (data or {}).get("returnItineraryPricesCalendar") or {}
    cal = node.get("calendar") or []
    print(f"\n   nights={nights}: {node.get('__typename')} err={err or 'none'} "
          f"appError={node.get('error')!r} -> {len(cal)} dated prices")
    rows = []
    for c in cal:
        try:
            rows.append((str(c["date"])[:10], float(c["ratedPrice"]["price"]["amount"])))
        except Exception:
            continue
    for d_, p in rows[:8]:
        ret = (date.fromisoformat(d_) + timedelta(days=nights)).isoformat()
        print(f"      {d_} -> {ret}   {p:>9,.0f} ILS")

client.close()
