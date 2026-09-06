"""Open a generated Kiwi booking link and confirm it actually prefills a search.

The previous link used IATA codes and loaded with empty From/To and "Nothing here yet ...".
Checking the URL shape is not enough; the page has to come up populated.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from models import SearchRequest  # noqa: E402
from providers.kiwi import KiwiProvider  # noqa: E402

DEST = sys.argv[1] if len(sys.argv) > 1 else "VCE"
dep = date.today() + timedelta(days=90)
req = SearchRequest(origin="TLV", depart_date=dep.isoformat(),
                    return_date=(dep + timedelta(days=4)).isoformat(),
                    adults=2, children=0, currency="ils")
url = KiwiProvider()._deeplink(req, DEST, dep, 4)
print("generated:", url)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)

    body = page.inner_text("body")
    empty = "Nothing here yet" in body or "must be filled in" in body
    # Kiwi renders the chosen places into the search inputs; read whatever is visible.
    values = page.eval_on_selector_all(
        "input", "els => els.map(e => e.value).filter(v => v && v.length > 1).slice(0, 6)")
    print("inputs :", values)
    print("empty-state present:", empty)
    print("RESULT :", "BROKEN - search not prefilled" if empty else "OK - search prefilled")
    page.screenshot(path="shots/kiwi-deeplink.png", full_page=False)
    browser.close()
