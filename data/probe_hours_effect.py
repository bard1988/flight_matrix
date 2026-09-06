"""Does a departure-hour window actually change the calendar prices?

If it does, a time filter is a real search parameter (prices become "cheapest flight
leaving in this window"), not a display filter - which matters because the calendar
returns no times at all, so a client-side time filter is impossible.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json", "Content-Type": "application/json",
        "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=60.0, verify=config.CA_BUNDLE, headers=HEAD, follow_redirects=True)

CAL = """
query Cal($search: SearchReturnPricesCalendarInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnItineraryPricesCalendar(search: $search, filter: $filter, options: $options) {
    __typename ... on AppError { error: message }
    ... on ItineraryPricesCalendar { calendar { date ratedPrice { price { amount } } } }
  }
}
"""

DEST = sys.argv[1] if len(sys.argv) > 1 else "ATH"
NIGHTS = 7
start = date.today() + timedelta(days=45)
end = start + timedelta(days=13)


def run(label, flt):
    variables = {
        "search": {
            "source": {"ids": ["Station:airport:TLV"]},
            "destination": {"ids": [f"Station:airport:{DEST}"]},
            "visibleDates": {"start": f"{start.isoformat()}T00:00:00",
                             "end": f"{end.isoformat()}T23:59:59"},
            "nightsCount": {"start": NIGHTS, "end": NIGHTS},
            "passengers": {"adults": 2, "children": 0, "infants": 0},
            "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
        },
        "filter": flt,
        "options": {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"},
    }
    time.sleep(1.6)
    r = client.post(ENDPOINT, content=json.dumps(
        {"query": CAL, "variables": variables, "operationName": "Cal"}))
    if r.status_code != 200:
        print(f"  {label:34} HTTP {r.status_code}")
        return {}
    node = (r.json().get("data") or {}).get("returnItineraryPricesCalendar") or {}
    if node.get("error"):
        print(f"  {label:34} app error: {node['error'][:60]}")
        return {}
    out = {}
    blank = 0
    for item in node.get("calendar") or []:
        rated = item.get("ratedPrice")
        # A dated entry with no price means nothing matched the filter that day.
        if not rated or not rated.get("price"):
            blank += 1
            continue
        out[str(item["date"])[:10]] = float(rated["price"]["amount"])
    lo = min(out.values()) if out else None
    print(f"  {label:34} {len(out):>2} priced, {blank:>2} empty, "
          f"cheapest {lo if lo is None else f'{lo:,.0f}'}")
    return out


print(f"TLV-{DEST}, {NIGHTS} nights, departures {start}..{end}, 2 adults\n")
base = run("no time filter", {})
morning = run("outbound departs 06:00-11:00", {"outbound": {"departureHours": {"start": 6, "end": 11}}})
evening = run("outbound departs 17:00-23:00", {"outbound": {"departureHours": {"start": 17, "end": 23}}})
both = run("out 06-11 AND inbound 17-23", {
    "outbound": {"departureHours": {"start": 6, "end": 11}},
    "inbound": {"departureHours": {"start": 17, "end": 23}},
})

if base:
    print("\n  date        no-filter   morning   evening   both")
    for d in sorted(base)[:8]:
        def f(x):
            return f"{x[d]:>9,.0f}" if d in x else f"{'-':>9}"
        print(f"  {d} {f(base)} {f(morning)} {f(evening)} {f(both)}")
    changed = sum(1 for d in base if d in morning and morning[d] != base[d])
    print(f"\n  morning window changed the price on {changed}/{len(base)} dates")
    print(f"  dates dropped entirely by the morning window: {len(base) - len(morning)}")

client.close()
