"""Reconnaissance for direct LCC feeds, the Wizz way: can we get a fare calendar or a
cheapest-fares-over-a-range response, keyless, from each carrier's own site?

Prints, per carrier: whether the homepage/bundle exposes an API base, and the HTTP status
+ a shape hint for each candidate fare endpoint tried. Nothing here is wired into the app;
this is a manual tool like the other data/probe_*.py scripts.

    py -3 data/probe_lccs.py            # all carriers
    py -3 data/probe_lccs.py pegasus    # one
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

DEP1 = (date.today() + timedelta(days=45)).isoformat()
DEP2 = (date.today() + timedelta(days=60)).isoformat()
RET1 = (date.today() + timedelta(days=59)).isoformat()
RET2 = (date.today() + timedelta(days=74)).isoformat()
YM = (date.today() + timedelta(days=52)).strftime("%Y-%m")


def client() -> httpx.Client:
    return httpx.Client(timeout=25.0, headers=UA, verify=config.CA_BUNDLE, follow_redirects=True)


def shape(r: httpx.Response) -> str:
    body = r.text[:180].replace("\n", " ")
    if r.status_code != 200:
        return f"HTTP {r.status_code}  {body}"
    try:
        j = r.json()
    except ValueError:
        return f"HTTP 200 non-JSON ({len(r.text)}b)  {body}"
    keys = list(j)[:8] if isinstance(j, dict) else f"list[{len(j)}]"
    return f"HTTP 200 JSON  top: {keys}"


def get(c: httpx.Client, url: str, label: str, **kw) -> httpx.Response | None:
    time.sleep(1.0)
    try:
        r = c.get(url, **kw)
    except httpx.HTTPError as e:
        print(f"  {label:34} ERR {type(e).__name__}: {str(e)[:70]}")
        return None
    print(f"  {label:34} {shape(r)}")
    return r


def post(c: httpx.Client, url: str, body: dict, label: str, **kw) -> httpx.Response | None:
    time.sleep(1.0)
    try:
        r = c.post(url, content=json.dumps(body), headers={"Content-Type": "application/json"}, **kw)
    except httpx.HTTPError as e:
        print(f"  {label:34} ERR {type(e).__name__}: {str(e)[:70]}")
        return None
    print(f"  {label:34} {shape(r)}")
    return r


def scan_bundle(c: httpx.Client, home: str) -> None:
    """Grep the homepage for API base URLs, the way Wizz's version is scraped."""
    try:
        html = c.get(home).text
    except httpx.HTTPError as e:
        print(f"  homepage {home}: {type(e).__name__}")
        return
    hosts = sorted(set(re.findall(r"https://[a-z0-9.\-]*(?:api|booking|nsk|services|search|fare)[a-z0-9.\-/]*", html, re.I)))
    for h in hosts[:12]:
        print(f"    bundle ref: {h}")


# --------------------------------------------------------------------------- carriers

def ryanair() -> None:
    print("\n=== Ryanair (farfnd, keyless — the reference) ===")
    c = client()
    get(c, "https://services-api.ryanair.com/farfnd/v4/roundTripFares"
           f"?departureAirportIataCode=STN&outboundDepartureDateFrom={DEP1}"
           f"&outboundDepartureDateTo={DEP2}&inboundDepartureDateFrom={RET1}"
           f"&inboundDepartureDateTo={RET2}&currency=EUR&limit=20",
        "roundTripFares STN->*")
    get(c, "https://www.ryanair.com/api/farfnd/v4/oneWayFares"
           f"?departureAirportIataCode=BER&outboundDepartureDateFrom={DEP1}"
           f"&outboundDepartureDateTo={DEP2}&currency=EUR", "oneWayFares BER->*")
    get(c, "https://www.ryanair.com/api/booking/v4/en-gb/availability"
           f"?ADT=2&CHD=0&DateOut={DEP1}&DateIn={RET1}&Origin=STN&Destination=BCN"
           "&RoundTrip=true&FlexDaysOut=3&FlexDaysIn=3", "availability STN-BCN (calendar)")
    c.close()


def pegasus() -> None:
    print("\n=== Pegasus (flypgs.com) — Turkish LCC, big at TLV ===")
    c = client()
    scan_bundle(c, "https://www.flypgs.com/en")
    get(c, "https://web-api.flypgs.com/api", "web-api root")
    post(c, "https://web-api.flypgs.com/api/flight/getFlights",
         {"originAirportCode": "SAW", "destinationAirportCode": "TLV",
          "departureDate": DEP1, "returnDate": RET1, "currency": "EUR",
          "adultCount": 2, "childCount": 0, "infantCount": 0}, "getFlights SAW-TLV")
    get(c, "https://www.flypgs.com/apixmp/api/pricetable"
           f"?depPort=SAW&arrPort=TLV&month={YM}&currency=EUR", "pricetable SAW-TLV")
    get(c, f"https://www.flypgs.com/en/cheap-flight-tickets/saw-tlv-flights", "cheap-tickets HTML page")
    c.close()


def airarabia() -> None:
    print("\n=== Air Arabia (Navitaire New Skies) — TLV routes ===")
    c = client()
    scan_bundle(c, "https://www.airarabia.com/en")
    get(c, "https://api.airarabia.com/api/nsk/v1/token", "nsk v1 token (GET)")
    post(c, "https://api.airarabia.com/api/nsk/v1/token", {}, "nsk v1 token (POST)")
    get(c, "https://booking.airarabia.com/api/nsk/v2/availability/lowfare"
           f"?origin=SHJ&destination=TLV&beginDate={DEP1}&endDate={DEP2}", "lowfare SHJ-TLV")
    c.close()


def ajet() -> None:
    print("\n=== AJet (ex-AnadoluJet) — Turkish, TLV ===")
    c = client()
    scan_bundle(c, "https://www.ajet.com/en")
    get(c, "https://web.ajet.com/api", "web api root")
    post(c, "https://web.ajet.com/api/availability/search",
         {"origin": "SAW", "destination": "TLV", "departureDate": DEP1,
          "returnDate": RET1, "adult": 2, "child": 0, "infant": 0, "currency": "EUR"},
         "availability/search SAW-TLV")
    get(c, f"https://web.ajet.com/api/pricetable?origin=SAW&destination=TLV&month={YM}",
        "pricetable SAW-TLV")
    c.close()


def easyjet() -> None:
    print("\n=== easyJet — flies TLV, Akamai-protected ===")
    c = client()
    scan_bundle(c, "https://www.easyjet.com/en")
    get(c, "https://www.easyjet.com/api/routepriceservice/v2/lowestdailyfares"
           f"?departureAirport=MXP&arrivalAirport=TLV&currency=EUR&departureDateFrom={DEP1}"
           f"&departureDateTo={DEP2}", "lowestdailyfares MXP-TLV")
    get(c, "https://www.easyjet.com/ejcms/service/pricefinder/roundtrip"
           f"?origin=LTN&destination=TLV&outboundDate={DEP1}&inboundDate={RET1}", "pricefinder LTN-TLV")
    get(c, f"https://www.easyjet.com/api/lowfares/v1/roundtrip?origin=LGW&destination=TLV"
           f"&outbound={DEP1}&inbound={RET1}&adults=2", "lowfares v1 LGW-TLV")
    c.close()


def flydubai() -> None:
    print("\n=== flydubai — one route (TLV-DXB) but a busy one ===")
    c = client()
    scan_bundle(c, "https://www.flydubai.com/en")
    get(c, "https://www.flydubai.com/en/api/flight-search/calendar"
           f"?origin=DXB&destination=TLV&month={YM}&currency=AED", "calendar DXB-TLV")
    post(c, "https://api.flydubai.com/res/v3/Availability",
         {"origin": "DXB", "destination": "TLV", "departureDate": DEP1,
          "returnDate": RET1, "adults": 2, "children": 0, "infants": 0}, "res/v3 Availability")
    c.close()


def aegean() -> None:
    print("\n=== Aegean — not an LCC, but TLV-ATH is huge; has a fare calendar ===")
    c = client()
    scan_bundle(c, "https://en.aegeanair.com/")
    get(c, "https://api.aegeanair.com/farecalendar/v1"
           f"?origin=ATH&destination=TLV&month={YM}&currency=EUR", "farecalendar ATH-TLV")
    get(c, "https://prod-api.aegeanair.com/aegean/v2/lowfares"
           f"?from=ATH&to=TLV&dateFrom={DEP1}&dateTo={DEP2}", "lowfares ATH-TLV")
    c.close()


def transavia() -> None:
    print("\n=== Transavia — had an open API; recheck the gate ===")
    c = client()
    get(c, "https://api.transavia.com/v3/flightoffers"
           f"?origin=AMS&destination=TLV&originDepartureDate={DEP1}"
           f"&destinationDepartureDate={RET1}&adults=2", "v3 flightoffers (no key)")
    get(c, "https://api.transavia.com/v1/flightapi/availableflights"
           f"?origin=AMS&destination=TLV&departuredate={DEP1}", "v1 availableflights (no key)")
    c.close()


CARRIERS = {
    "ryanair": ryanair, "pegasus": pegasus, "airarabia": airarabia, "ajet": ajet,
    "easyjet": easyjet, "flydubai": flydubai, "aegean": aegean, "transavia": transavia,
}

if __name__ == "__main__":
    want = sys.argv[1:] or list(CARRIERS)
    for name in want:
        fn = CARRIERS.get(name.lower())
        if fn:
            fn()
        else:
            print(f"unknown carrier: {name}  (have: {', '.join(CARRIERS)})")
