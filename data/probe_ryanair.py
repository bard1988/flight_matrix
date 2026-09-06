"""Does Ryanair's keyless farfnd endpoint work, and does it serve our origin?"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

ORIGIN = sys.argv[1] if len(sys.argv) > 1 else "TLV"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}
client = httpx.Client(timeout=30.0, verify=config.CA_BUNDLE, headers=UA, follow_redirects=True)

# --- is the origin served at all? -------------------------------------------
airports = client.get("https://www.ryanair.com/api/views/locate/5/airports/en/active").json()
codes = {a.get("code"): a for a in airports}
print(f"Ryanair active airports: {len(codes)}")
hit = codes.get(ORIGIN)
print(f"  {ORIGIN} served by Ryanair? {'YES - ' + hit['name'] if hit else 'NO'}")

if not hit:
    il = [f"{c} {a.get('name')}" for c, a in codes.items()
          if (a.get("country") or {}).get("code") == "il"]
    print(f"  Israeli airports in Ryanair's network: {il or 'none'}")

# --- what limit does farfnd accept? -----------------------------------------
out_from = date.today() + timedelta(days=14)
out_to = out_from + timedelta(days=14)
in_from = out_from + timedelta(days=7)
in_to = in_from + timedelta(days=14)

print("\nfarfnd v4 roundTripFares limit probing")
for limit in (10, 16, 20, 50):
    r = client.get(
        "https://services-api.ryanair.com/farfnd/v4/roundTripFares",
        params={"departureAirportIataCode": ORIGIN,
                "outboundDepartureDateFrom": out_from.isoformat(),
                "outboundDepartureDateTo": out_to.isoformat(),
                "inboundDepartureDateFrom": in_from.isoformat(),
                "inboundDepartureDateTo": in_to.isoformat(),
                "market": "en-gb", "adultPaxCount": 1, "limit": limit, "offset": 0},
    )
    note = ""
    if r.status_code == 200:
        fares = r.json().get("fares", [])
        note = f"{len(fares)} fares"
        if fares:
            f0 = fares[0]
            note += (f" | e.g. {f0['outbound']['arrivalAirport']['iataCode']} "
                     f"{f0['summary']['price']['value']} {f0['summary']['price']['currencyCode']}")
    else:
        note = r.text[:70]
    print(f"  limit={limit:3} -> HTTP {r.status_code}  {note}")

# --- a control origin known to be a big Ryanair base ------------------------
print("\ncontrol: same call from a major Ryanair base (STN, London Stansted)")
r = client.get(
    "https://services-api.ryanair.com/farfnd/v4/roundTripFares",
    params={"departureAirportIataCode": "STN",
            "outboundDepartureDateFrom": out_from.isoformat(),
            "outboundDepartureDateTo": out_to.isoformat(),
            "inboundDepartureDateFrom": in_from.isoformat(),
            "inboundDepartureDateTo": in_to.isoformat(),
            "market": "en-gb", "adultPaxCount": 1, "limit": 16, "offset": 0},
)
print(f"  HTTP {r.status_code}")
if r.status_code == 200:
    fares = r.json().get("fares", [])
    print(f"  {len(fares)} fares, cheapest first:")
    for f in fares[:8]:
        o, i = f["outbound"], f["inbound"]
        print(f"    STN -> {o['arrivalAirport']['iataCode']:4} "
              f"{o['departureDate'][:10]} / {i['departureDate'][:10]}  "
              f"{f['summary']['price']['value']:>7.2f} {f['summary']['price']['currencyCode']}")

client.close()
