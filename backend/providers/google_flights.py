"""Live per-cell verification via Google Flights (the `fast-flights` package, 3.x API).

This exists because the cached board cannot price a family. Two separate distortions make
the estimate optimistic:

* there is no child fare in the cached data, so children are extrapolated from an adult
  ticket, and
* a headline fare often has only one or two seats left at that price, so a real
  5-passenger total lands materially above 5x the advertised cheapest fare.

One request per date pair, so this is only ever called on demand.

The 3.x API differs from 2.x: `create_query(flights=[FlightQuery(...)], ...)` then
`get_flights(query)`, and it takes `currency` natively so prices come back in the
requested currency rather than needing symbol parsing. It also accepts `carry_on_bags` /
`checked_bags`, which is the hook for fare variants if that gets added later.
"""
from __future__ import annotations

import re
from typing import Any

from providers.base import ProviderError

_PRICE_RE = re.compile(r"[\d][\d,.\s]*")
_INSTALL_HINT = (
    "fast-flights is not installed. Fetch the wheels with "
    "`py -3 data/get_wheel.py fast-flights primp protobuf selectolax` then "
    "`py -3 -m pip install --no-index --find-links wheels fast-flights`."
)


def _parse_price(raw: Any) -> float | None:
    """Prices normally arrive as numbers; fall back to digits out of a string."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = _PRICE_RE.search(str(raw))
    if not match:
        return None
    cleaned = match.group(0).replace(",", "").replace(" ", "").strip().rstrip(".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clock(date_parts: Any, time_parts: Any) -> str | None:
    """Format a raw Google date+time pair as 'Mon 14 Dec 06:25'.

    Google omits trailing zero components and uses null for a leading zero, so [8] means
    08:00 and [null, 31] means 00:31.
    """
    try:
        from datetime import date as _date
        y, m, d = (list(date_parts) + [None, None, None])[:3]
        stamp = _date(int(y), int(m), int(d))
    except Exception:
        return None
    padded = list(time_parts or []) + [None, None]
    hh, mm = (padded[0] or 0), (padded[1] or 0)
    return f"{stamp.strftime('%a %d %b')} {int(hh):02d}:{int(mm):02d}"


def _fmt_when(value: Any) -> str | None:
    """A SimpleDatetime (date tuple + time tuple) as 'Mon 14 Dec 06:25'."""
    if value is None:
        return None
    d, t = getattr(value, "date", None), getattr(value, "time", None)
    if not d:
        return None
    try:
        from datetime import date as _date
        stamp = _date(int(d[0]), int(d[1]), int(d[2]))
    except Exception:
        return None
    when = stamp.strftime("%a %d %b")
    if t:
        try:
            when += f" {int(t[0]):02d}:{int(t[1]):02d}"
        except Exception:
            pass
    return when


def _itinerary_times(result: Any) -> dict[str, Any] | None:
    """Departure/arrival of the first and last segment, plus each leg's airports."""
    legs = getattr(result, "flights", None)
    if not isinstance(legs, list) or not legs:
        return None
    first, last = legs[0], legs[-1]
    out = {
        "departs": _fmt_when(getattr(first, "departure", None)),
        "arrives": _fmt_when(getattr(last, "arrival", None)),
        "segments": [],
    }
    for leg in legs:
        src = getattr(leg, "from_airport", None)
        dst = getattr(leg, "to_airport", None)
        out["segments"].append({
            "from": getattr(src, "code", None) or getattr(src, "name", None),
            "to": getattr(dst, "code", None) or getattr(dst, "name", None),
            "departs": _fmt_when(getattr(leg, "departure", None)),
            "arrives": _fmt_when(getattr(leg, "arrival", None)),
        })
    return out


def _leg_count(result: Any) -> int | None:
    """Stops on the outbound leg = number of individual flights minus one."""
    legs = getattr(result, "flights", None)
    if isinstance(legs, list) and legs:
        return max(0, len(legs) - 1)
    return None


def _airlines(result: Any) -> str | None:
    value = getattr(result, "airlines", None)
    if not value:
        return None
    names = []
    for entry in value if isinstance(value, list) else [value]:
        name = getattr(entry, "name", None) or getattr(entry, "code", None) or str(entry)
        if name and name not in names:
            names.append(name)
    return ", ".join(names) or None


def _duration(result: Any) -> str | None:
    """Duration lives on the individual segments, not on the itinerary."""
    value = getattr(result, "duration", None)
    if value is None:
        legs = getattr(result, "flights", None)
        if isinstance(legs, list) and legs:
            value = getattr(legs[0], "duration", None)
    if value is None:
        return None
    if isinstance(value, int):
        return f"{value // 60}h {value % 60:02d}m"
    return str(value)


def _explain(exc: Exception) -> str:
    """Turn a fast-flights failure into something a person can act on.

    Its parser raises a bare TypeError from `payload[3][0]` when Google returns a page
    with no itinerary block at all, which in practice means the route simply is not
    served on those dates. Reporting that as a crash would be misleading.
    """
    frames = []
    tb = exc.__traceback__
    while tb is not None:
        frames.append(tb.tb_frame.f_code.co_filename)
        tb = tb.tb_next
    in_parser = any("fast_flights" in f and "parser" in f for f in frames)
    if in_parser and isinstance(exc, (TypeError, IndexError, KeyError, AttributeError)):
        return ("Google Flights returned no itineraries for this route on these dates. "
                "The route is probably not served, or not as a round trip on this pair.")
    if exc.__class__.__name__ == "FlightsNotFound":
        return "Google Flights found no flights for this route on these dates."
    return f"Google Flights lookup failed: {type(exc).__name__}: {exc}"


def _parse_all_itineraries(html: str) -> list[dict[str, Any]]:
    """Parse EVERY itinerary block Google returns, not just one.

    fast-flights' own parser reads `payload[3][0]` only. Google also returns a separate
    block at `payload[2][0]` (its "best flights" section), and measured on TLV-LON that
    block held the cheapest option by a wide margin: Israir at 8,285 ILS versus 10,974 for
    the cheapest in `payload[3]`. Reading one block understated the price of many cells.

    Returns [] if the shape is not what we expect, so the caller can fall back.
    """
    import json

    from selectolax.lexbor import LexborHTMLParser

    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        return []
    text = script.text()
    if "data:" not in text:
        return []

    body = text.split("data:", 1)[1].strip()
    # Google appends a trailer after the JSON value (", errorHasStatus: true,});" on an
    # error response), so slicing on the last comma raises "Extra data". raw_decode reads
    # the first complete value and ignores whatever follows.
    try:
        payload, _ = json.JSONDecoder().raw_decode(body)
    except json.JSONDecodeError:
        return []

    # An error response carries no itineraries; let the caller fall through to the
    # library's parser, which raises FlightsNotFound and gets a readable message.
    if "errorHasStatus" in text or "ErrorResponse" in text[:400]:
        return []

    out: list[dict[str, Any]] = []
    for index in (2, 3):
        if index >= len(payload):
            continue
        block = payload[index]
        if not isinstance(block, list) or not block or not isinstance(block[0], list):
            continue
        for row in block[0]:
            try:
                flight = row[0]
                price = row[1][0][1]
                segments = flight[2] or []
                # Segment layout, same indices the library's own parser uses:
                #   3 from-code, 6 to-code, 8 departure time, 20 departure date,
                #   10 arrival time, 21 arrival date, 11 duration minutes.
                legs = []
                for seg in segments:
                    legs.append({
                        "from": seg[3],
                        "to": seg[6],
                        "departs": _clock(seg[20], seg[8]),
                        "arrives": _clock(seg[21], seg[10]),
                    })
                out.append(
                    {
                        "price": float(price),
                        "airlines": ", ".join(flight[1] or []) or None,
                        "stops": max(0, len(segments) - 1),
                        "duration_minutes": segments[0][11] if segments else None,
                        "departs": legs[0]["departs"] if legs else None,
                        "arrives": legs[-1]["arrives"] if legs else None,
                        "segments": legs,
                        "block": index,
                    }
                )
            except (IndexError, TypeError, ValueError):
                continue
    return out


def _fmt_minutes(value: Any) -> str | None:
    if not isinstance(value, int):
        return None
    return f"{value // 60}h {value % 60:02d}m"


class GoogleFlightsProvider:
    """Thin wrapper. Deliberately does not retry hard; Google rate-limits aggressively."""

    def verify(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: str,
        adults: int,
        children: int,
        currency: str,
        nonstop_only: bool = False,
    ) -> dict[str, Any]:
        try:
            from fast_flights import fetch_flights_html, get_flights

            query = _build_query(origin, destination, depart_date, return_date,
                                 adults, children, currency, nonstop_only)
        except ImportError as exc:
            raise ProviderError(f"{_INSTALL_HINT} ({exc})") from exc

        # Fetch once, parse every itinerary block ourselves. Fall back to the library's
        # own parser if Google changes the payload shape under us.
        # The link comes off the same query object that fetches the price, so the page the
        # user opens and the number they were shown describe one trip by construction.
        link = query.url()
        try:
            html = fetch_flights_html(query)
            rows = _parse_all_itineraries(html)
        except Exception as exc:
            rows = []
            html_error: Exception | None = exc
        else:
            html_error = None

        if rows:
            best = min(rows, key=lambda r: r["price"])
            return {
                "total": best["price"],
                "currency": currency,
                "airline": best["airlines"],
                "stops_out": best["stops"],
                "stops_back": None,
                "duration": _fmt_minutes(best["duration_minutes"]),
                "departs": best.get("departs"),
                "arrives": best.get("arrives"),
                "segments": best.get("segments"),
                "link": link,
                "candidates": len(rows),
            }

        try:
            results = get_flights(query)
        except Exception as exc:
            raise ProviderError(_explain(html_error or exc)) from exc

        priced = []
        for item in list(results or []):
            price = _parse_price(getattr(item, "price", None))
            if price is not None:
                priced.append((item, price))
        if not priced:
            raise ProviderError("Google Flights returned no priced itineraries for this date pair.")

        best_item, total = min(priced, key=lambda pair: pair[1])
        return {
            "total": total,
            "currency": currency,
            "airline": _airlines(best_item),
            "stops_out": _leg_count(best_item),
            "stops_back": None,
            "duration": _duration(best_item),
            "departs": (_itinerary_times(best_item) or {}).get("departs"),
            "arrives": (_itinerary_times(best_item) or {}).get("arrives"),
            "segments": (_itinerary_times(best_item) or {}).get("segments"),
            "link": link,
            "candidates": len(priced),
        }


def _build_query(
    origin: str, destination: str, depart_date: str, return_date: str,
    adults: int, children: int, currency: str, nonstop_only: bool,
):
    """The round trip as fast-flights describes it. Raises ImportError if it is missing."""
    from fast_flights import FlightQuery, Passengers, create_query

    max_stops = 0 if nonstop_only else None
    legs = [
        FlightQuery(date=depart_date, from_airport=origin.upper(),
                    to_airport=destination.upper(), max_stops=max_stops),
        FlightQuery(date=return_date, from_airport=destination.upper(),
                    to_airport=origin.upper(), max_stops=max_stops),
    ]
    return create_query(
        flights=legs,
        trip="round-trip",
        seat="economy",
        passengers=Passengers(
            adults=max(adults, 1), children=children, infants_in_seat=0, infants_on_lap=0
        ),
        currency=currency.upper(),
        max_stops=max_stops,
    )


def google_flights_url(
    origin: str, destination: str, depart_date: str, return_date: str, adults: int,
    children: int, currency: str = "USD", nonstop_only: bool = False,
) -> str:
    """A Google Flights URL that opens THIS itinerary, prefilled.

    This used to hand Google free text: `?q=Flights from TLV to ATH on 2026-10-08 through
    2026-10-29 for 2 adults`. Google parses that only sometimes, and with ISO dates plus a
    passenger clause it generally landed on the bare Flights homepage with nothing filled
    in, which is what made "Open on Google Flights" look broken. `tfs` is the real
    parameter: a base64 protobuf of the query, and the same object the verifier builds to
    price the date pair.

    Falls back to the old text form only if fast-flights is unavailable, which is itself
    one of the reasons verify() fails and reaches the caller that needs this link.
    """
    try:
        return _build_query(origin, destination, depart_date, return_date, adults,
                            children, currency, nonstop_only).url()
    except Exception:
        from urllib.parse import quote_plus

        who = f"{adults} adults" + (f" {children} children" if children else "")
        query = (
            f"Flights from {origin.upper()} to {destination.upper()} on {depart_date} "
            f"through {return_date} for {who}"
        )
        return f"https://www.google.com/travel/flights?q={quote_plus(query)}"
