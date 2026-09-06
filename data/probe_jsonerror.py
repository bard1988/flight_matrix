"""Reproduce the JSONDecodeError when parsing Google's embedded payload.

We slice the script text with `split("data:")` then `rsplit(",", 1)[0]`, which assumes a
particular trailing fragment. When the trailer differs, json.loads sees a valid value
followed by extra characters and raises "Extra data".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fast_flights import FlightQuery, Passengers, create_query, fetch_flights_html  # noqa: E402
from selectolax.lexbor import LexborHTMLParser  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "LCA"
DEP = sys.argv[2] if len(sys.argv) > 2 else "2027-08-16"
RET = sys.argv[3] if len(sys.argv) > 3 else "2027-08-26"

q = create_query(
    flights=[FlightQuery(date=DEP, from_airport="TLV", to_airport=DEST),
             FlightQuery(date=RET, from_airport=DEST, to_airport="TLV")],
    trip="round-trip", seat="economy",
    passengers=Passengers(adults=2, children=3, infants_in_seat=0, infants_on_lap=0),
    currency="ILS",
)
html = fetch_flights_html(q)
script = LexborHTMLParser(html).css_first(r"script.ds\:1")
print("script found:", script is not None)
text = script.text()
print(f"script length: {len(text)}")
print("head:", text[:120].replace("\n", " "))

body = text.split("data:", 1)[1]
print("\nafter split('data:'), tail:", repr(body[-90:]))

old = body.rsplit(",", 1)[0]
try:
    json.loads(old)
    print("\nOLD slicing: parsed fine")
except Exception as exc:
    print(f"\nOLD slicing: {type(exc).__name__}: {exc}")

# raw_decode reads the first complete JSON value and tells us where it ended, so whatever
# trailer follows is simply ignored.
try:
    value, end = json.JSONDecoder().raw_decode(body.strip())
    print(f"NEW raw_decode: OK, consumed {end} chars, top-level length {len(value)}")
    print("   trailer that was ignored:", repr(body.strip()[end:end + 60]))
except Exception as exc:
    print(f"NEW raw_decode: {type(exc).__name__}: {exc}")
