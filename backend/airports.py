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


# Full ISO 3166-1 alpha-2 -> {name, continent, subregion}, derived from mledoze/countries
# with travel-taxonomy overrides. Regenerate with `py -3 data/build_countries.py`.
_COUNTRIES_FILE = DATA_DIR / "countries.json"
_countries: dict[str, dict[str, str]] | None = None


def _country_table() -> dict[str, dict[str, str]]:
    global _countries
    if _countries is None:
        try:
            _countries = json.loads(_COUNTRIES_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _countries = {}
    return _countries


def country_name(code: str) -> str:
    return _country_table().get((code or "").upper(), {}).get("name", "")


def region_of(code: str) -> tuple[str, str]:
    """(continent, subregion) for an ISO alpha-2 country code, or ('', '') if unknown."""
    entry = _country_table().get((code or "").upper())
    return (entry["continent"], entry["subregion"]) if entry else ("", "")


def taxonomy() -> list[dict[str, Any]]:
    """The region tree: continents -> subregions -> countries, for /api/regions."""
    tree: dict[str, dict[str, list[dict[str, str]]]] = {}
    for code, e in _country_table().items():
        cont, sub = e["continent"], e["subregion"]
        if cont in ("", "Antarctic"):
            continue
        tree.setdefault(cont, {}).setdefault(sub, []).append({"code": code, "name": e["name"]})
    return [
        {
            "continent": cont,
            "subregions": [
                {"name": sub, "countries": sorted(cs, key=lambda c: c["name"])}
                for sub, cs in sorted(subs.items())
            ],
        }
        for cont, subs in sorted(tree.items())
    ]


def describe(code: str) -> dict[str, str]:
    entry = load().get((code or "").upper())
    if not entry:
        return {"city": (code or "").upper(), "country": ""}
    return entry
