"""IATA code to city/country lookup.

Travelpayouts publishes these as plain JSON with no token required, so fetch once and
cache to data/. Everything degrades to bare IATA codes if the fetch fails, which keeps a
cold start with no network from breaking the board.
"""
from __future__ import annotations

import json
import threading
from typing import Any

import httpx

from config import CA_BUNDLE, DATA_DIR

_SOURCES = {
    "cities": "https://api.travelpayouts.com/data/en/cities.json",
    "airports": "https://api.travelpayouts.com/data/en/airports.json",
}
_CACHE_FILE = DATA_DIR / "airports.json"

_lock = threading.Lock()
_index: dict[str, dict[str, str]] | None = None


def _build_index(cities: list[dict[str, Any]], airports: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    # Airports first so that a city entry with the same code wins, since the board is
    # keyed on city-level codes far more often than airport-level ones.
    for record in airports:
        code = (record.get("code") or "").upper()
        if not code:
            continue
        index[code] = {
            "city": record.get("name") or code,
            "country": record.get("country_code") or "",
        }
    for record in cities:
        code = (record.get("code") or "").upper()
        if not code:
            continue
        index[code] = {
            "city": record.get("name") or code,
            "country": record.get("country_code") or "",
        }
    return index


def _download() -> dict[str, dict[str, str]]:
    payloads: dict[str, list[dict[str, Any]]] = {}
    with httpx.Client(timeout=30.0, verify=CA_BUNDLE) as client:
        for key, url in _SOURCES.items():
            payloads[key] = client.get(url).json()
    index = _build_index(payloads["cities"], payloads["airports"])
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(index), encoding="utf-8")
    return index


def load() -> dict[str, dict[str, str]]:
    global _index
    with _lock:
        if _index is not None:
            return _index
        if _CACHE_FILE.exists():
            try:
                _index = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
                return _index
            except (json.JSONDecodeError, OSError):
                pass
        try:
            _index = _download()
        except Exception:
            _index = {}
        return _index


# The airport feed carries ISO country codes only, so "greece" would match nothing while
# "GR" worked. This covers the countries reachable from the Mediterranean/Europe region
# this tool is aimed at; anything missing still matches by code.
COUNTRY_NAMES = {
    "AL": "Albania", "AM": "Armenia", "AT": "Austria", "AZ": "Azerbaijan", "BA": "Bosnia",
    "BE": "Belgium", "BG": "Bulgaria", "BY": "Belarus", "CH": "Switzerland", "CY": "Cyprus",
    "CZ": "Czechia Czech Republic", "DE": "Germany", "DK": "Denmark", "EE": "Estonia",
    "EG": "Egypt", "ES": "Spain", "FI": "Finland", "FR": "France", "GB": "United Kingdom",
    "GE": "Georgia", "GR": "Greece", "HR": "Croatia", "HU": "Hungary", "IE": "Ireland",
    "IL": "Israel", "IS": "Iceland", "IT": "Italy", "JO": "Jordan", "KZ": "Kazakhstan",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MA": "Morocco", "MD": "Moldova",
    "ME": "Montenegro", "MK": "North Macedonia", "MT": "Malta", "NL": "Netherlands",
    "NO": "Norway", "PL": "Poland", "PT": "Portugal", "RO": "Romania", "RS": "Serbia",
    "RU": "Russia", "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia", "TR": "Turkey",
    "UA": "Ukraine", "UZ": "Uzbekistan", "XK": "Kosovo",
    "AE": "United Arab Emirates", "SA": "Saudi Arabia", "QA": "Qatar", "BH": "Bahrain",
    "IN": "India", "TH": "Thailand", "US": "United States", "CA": "Canada",
    "ZA": "South Africa", "KE": "Kenya", "TZ": "Tanzania", "MU": "Mauritius",
    "SC": "Seychelles", "MV": "Maldives", "LK": "Sri Lanka", "VN": "Vietnam",
    "JP": "Japan", "CN": "China", "SG": "Singapore", "AU": "Australia", "BR": "Brazil",
    "AR": "Argentina", "MX": "Mexico", "CL": "Chile", "PE": "Peru", "CO": "Colombia",
}


def country_name(code: str) -> str:
    return COUNTRY_NAMES.get((code or "").upper(), "")


def describe(code: str) -> dict[str, str]:
    entry = load().get((code or "").upper())
    if not entry:
        return {"city": (code or "").upper(), "country": ""}
    return entry
