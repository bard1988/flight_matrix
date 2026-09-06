"""Which URL parameters make kiwi.com pick up children?

Opens candidate URLs and reads back the passenger control.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

BASE = "https://www.kiwi.com/en/search/results/tel-aviv-israel/athens-greece"
dep = (date.today() + timedelta(days=90)).isoformat()
ret = (date.today() + timedelta(days=94)).isoformat()

CANDIDATES = {
    "adults&children&infants": f"{BASE}/{dep}/{ret}?adults=2&children=3&infants=0",
    "passengers=2.3.0": f"{BASE}/{dep}/{ret}?passengers=2.3.0",
    "adults+children only": f"{BASE}/{dep}/{ret}?adults=2&children=3",
    "no params (control)": f"{BASE}/{dep}/{ret}",
}

READ = """
() => {
  const t = document.body.innerText;
  const m = t.match(/(\\d+)\\s+Passengers?/i);
  return m ? m[0] : (t.includes('Passenger') ? 'found word only' : 'none');
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for label, url in CANDIDATES.items():
        page = browser.new_page(viewport={"width": 1400, "height": 800})
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            print(f"  {label:26} -> {page.evaluate(READ)}")
        except Exception as exc:
            print(f"  {label:26} -> error {type(exc).__name__}")
        page.close()
    browser.close()
print("\n(expecting '5 Passengers' for 2 adults + 3 children)")
