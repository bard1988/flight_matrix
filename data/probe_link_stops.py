"""Which kiwi.com URL parameter carries the 'direct flights only' filter?

Our booking link drops every search filter, so a nonstop-only board sends you to a Kiwi
page happily showing 1-stop options.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

BASE = "https://www.kiwi.com/en/search/results/tel-aviv-israel/athens-greece"
dep = (date.today() + timedelta(days=60)).isoformat()
ret = (date.today() + timedelta(days=67)).isoformat()
PAX = "adults=2&children=0&infants=0"

CANDIDATES = {
    "no stops param (control)": f"{BASE}/{dep}/{ret}?{PAX}",
    "stopNumber=0": f"{BASE}/{dep}/{ret}?{PAX}&stopNumber=0",
    "maxStopsCount=0": f"{BASE}/{dep}/{ret}?{PAX}&maxStopsCount=0",
    "maxstopovers=0": f"{BASE}/{dep}/{ret}?{PAX}&maxstopovers=0",
}

# The Stops filter renders as radio buttons; read which one is selected.
READ = """
() => {
  const labels = [...document.querySelectorAll('label, div')]
    .map(e => e.innerText || '')
    .filter(t => /^(Any|Direct|Up to 1 stop|Up to 2 stops)$/m.test(t.trim()));
  const checked = [...document.querySelectorAll('input[type=radio]')]
    .map((r, i) => r.checked ? i : null).filter(v => v !== null);
  const t = document.body.innerText;
  return {checkedRadioIndexes: checked,
          hasDirect: t.includes('Direct'),
          firstLines: t.split('\\n').slice(0, 3)};
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for label, url in CANDIDATES.items():
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(7000)
            print(f"  {label:26} -> {page.evaluate(READ)['checkedRadioIndexes']}")
        except Exception as exc:
            print(f"  {label:26} -> {type(exc).__name__}")
        page.close()
    browser.close()
print("\n(radio index 0 = Any, 1 = Direct, on Kiwi's Stops filter)")
