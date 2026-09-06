"""How many departure dates does ONE Kiwi calendar call actually return?

If the calendar truncates the visibleDates range, a wide window leaves each diagonal
partly unfilled and the grid shows a staircase instead of a full triangle.
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
query Cal($search: SearchReturnPricesCalendarInput, $options: ItinerariesOptionsInput) {
  returnItineraryPricesCalendar(search: $search, filter: {}, options: $options) {
    __typename ... on AppError { error: message }
    ... on ItineraryPricesCalendar { calendar { date ratedPrice { price { amount } } } }
  }
}
"""

DEST = sys.argv[1] if len(sys.argv) > 1 else "FCO"
NIGHTS = int(sys.argv[2]) if len(sys.argv) > 2 else 7
start = date.today() + timedelta(days=40)

print(f"TLV-{DEST}, {NIGHTS} nights, visibleDates starting {start}\n")
print(f"{'span asked':>11} {'dates returned':>15} {'first':>12} {'last':>12}")
print("-" * 56)
for span in (15, 31, 43, 60, 90):
    end = start + timedelta(days=span - 1)
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
        "options": {"currency": "ils", "locale": "en", "partner": "skypicker", "market": "il"},
    }
    time.sleep(1.6)
    r = client.post(ENDPOINT, content=json.dumps(
        {"query": CAL, "variables": variables, "operationName": "Cal"}))
    if r.status_code != 200:
        print(f"{span:>11} {'HTTP ' + str(r.status_code):>15}")
        continue
    node = (r.json().get("data") or {}).get("returnItineraryPricesCalendar") or {}
    if node.get("error"):
        print(f"{span:>11} {'error':>15}  {node['error'][:40]}")
        continue
    dates = sorted(str(i["date"])[:10] for i in (node.get("calendar") or []))
    print(f"{span:>11} {len(dates):>15} {dates[0] if dates else '-':>12} "
          f"{dates[-1] if dates else '-':>12}")

client.close()
