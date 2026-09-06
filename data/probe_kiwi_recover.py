"""How long does a Kiwi search block actually last? Poll a real search until it passes."""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from models import SearchRequest, window  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.kiwi import KiwiProvider  # noqa: E402

MAX_MINUTES = int(sys.argv[1]) if len(sys.argv) > 1 else 12
INTERVAL = 60

d = date.today() + timedelta(days=21)
r = d + timedelta(days=7)
request = SearchRequest(origin="TLV", depart_date=d.isoformat(), return_date=r.isoformat(),
                        adults=2, children=3, currency="ils", max_destinations=5)
dep_dates = window(d, 7)
ret_dates = window(r, 7)

provider = KiwiProvider()
start = time.time()
attempt = 0
while time.time() - start < MAX_MINUTES * 60:
    attempt += 1
    elapsed = int(time.time() - start)
    try:
        found = provider.discover(request, dep_dates, ret_dates)
        print(f"[{elapsed:4}s] attempt {attempt}: OK - {len(found)} destinations, "
              f"cheapest {found[0][0]} at {found[0][1]:,.0f} ILS")
        print(f"\nKiwi search recovered after about {elapsed // 60} min {elapsed % 60}s of waiting.")
        break
    except ProviderError as exc:
        blocked = "403" in str(exc) or "rate-limit" in str(exc).lower()
        print(f"[{elapsed:4}s] attempt {attempt}: {'still blocked' if blocked else str(exc)[:70]}")
    time.sleep(INTERVAL)
else:
    print(f"\nStill blocked after {MAX_MINUTES} minutes.")
