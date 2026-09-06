"""Synthetic provider for developing and eyeballing the board without a token.

Deliberately reproduces the awkward parts of the real data: holes in the grid, stale
rows, expired rows, and a price surface that is cheapest midweek. Never used unless
run.py is started with --demo.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

import config
from models import Cell, DestinationMatrix, SearchRequest, utcnow

_DESTINATIONS = [
    ("ATH", 240), ("LCA", 210), ("SKG", 260), ("BUD", 320), ("SOF", 300),
    ("PRG", 380), ("ROM", 350), ("MIL", 360), ("BCN", 430), ("VIE", 400),
    ("BER", 450), ("PAR", 520), ("AMS", 500), ("TBS", 340), ("IST", 330),
    ("LON", 560), ("MAD", 540), ("ZRH", 610), ("CPH", 590), ("LIS", 640),
    ("DXB", 470), ("BKK", 980), ("TIA", 290), ("PMO", 410),
]

_AIRLINES = ["W6", "FR", "LY", "U2", "A3", "TK", "SU"]


class DemoProvider:
    def __init__(self, seed: int = 7) -> None:
        self._seed = seed
        self.strategy = "demo"

    def _rng(self, *parts: object) -> random.Random:
        key = "|".join(str(p) for p in (self._seed, *parts))
        return random.Random(int(hashlib.md5(key.encode()).hexdigest()[:12], 16))

    def discover(
        self, request: SearchRequest, depart_dates: list[date], return_dates: list[date]
    ) -> list[tuple[str, float]]:
        rng = self._rng("discover", request.origin, request.depart_date)
        picks = [(code, base * rng.uniform(0.85, 1.15)) for code, base in _DESTINATIONS]
        picks.sort(key=lambda item: item[1])
        return picks[: request.max_destinations]

    def fill_matrix(
        self, request: SearchRequest, destination: str, depart_dates: list[date], return_dates: list[date]
    ) -> DestinationMatrix:
        base = dict(_DESTINATIONS).get(destination.upper(), 400)
        matrix = DestinationMatrix(origin=request.origin.upper(), destination=destination.upper())
        now = utcnow()

        for depart in depart_dates:
            for ret in return_dates:
                if ret < depart:
                    continue
                rng = self._rng(destination, depart, ret)
                # Coverage is search-driven in the real API, so punch holes, more of them
                # on the odd date pairs nobody searches.
                nights = (ret - depart).days
                popularity = 0.92 if 4 <= nights <= 12 else 0.55
                if rng.random() > popularity:
                    continue

                price = base
                price *= 1.22 if depart.weekday() in (3, 4) else 1.0   # Thu/Fri departures
                price *= 1.15 if ret.weekday() in (6, 0) else 1.0      # Sun/Mon returns
                price *= 1.0 + max(0, nights - 14) * 0.04
                price *= 1.18 if nights <= 2 else 1.0
                price *= rng.uniform(0.82, 1.25)

                transfers = 0 if rng.random() < 0.55 else rng.choice([1, 1, 2])
                if transfers:
                    price *= 0.88                                       # stops are cheaper
                if request.nonstop_only and transfers:
                    continue

                age_hours = rng.choice([1, 3, 8, 20, 30, 55])
                found = now - timedelta(hours=age_hours)
                expires = found + timedelta(hours=rng.choice([12, 48, 96]))
                if expires <= now:                                      # already gone
                    continue

                matrix.add(
                    Cell(
                        depart_date=depart.isoformat(),
                        return_date=ret.isoformat(),
                        price=round(price, 2),
                        currency=request.currency,
                        airline=rng.choice(_AIRLINES),
                        transfers=transfers,
                        return_transfers=transfers,
                        found_at=found.isoformat(),
                        expires_at=expires.isoformat(),
                        link="https://www.aviasales.com/",
                    )
                )
        return matrix

    def close(self) -> None:
        pass
