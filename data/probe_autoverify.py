"""Kiwi board first, then Google Flights upgrading the cheapest cells automatically."""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 21

depart = date.today() + timedelta(days=DAYS)
ret = depart + timedelta(days=7)

STATS = """
() => {
  const cards = [...document.querySelectorAll('#board .card')];
  return {
    cards: cards.length,
    verified: document.querySelectorAll('#board td.verified').length,
    order: cards.map(c => c.querySelector('h2').textContent + ' ' +
                          c.querySelector('.best').textContent.trim().replace(/\\s+/g,' ')),
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "3")
    page.fill("#dests", "3")
    t0 = time.time()
    page.click("#go")

    page.wait_for_function("document.querySelectorAll('#board .card').length >= 3", timeout=180000)
    page.wait_for_timeout(600)
    print(f"Kiwi board up in {time.time()-t0:.0f}s")
    before = page.evaluate(STATS)
    print("  verified cells:", before["verified"])
    for row in before["order"]:
        print("   ", row)

    print("\nwaiting for the automatic Google cross-check...")
    page.wait_for_function(
        "document.getElementById('growing').textContent.includes('cross-checking')",
        timeout=60000)
    print("  status:", page.text_content("#growing"))

    page.wait_for_function("document.getElementById('growing').hidden === true", timeout=600000)
    page.wait_for_timeout(800)
    after = page.evaluate(STATS)
    print(f"\ndone in {time.time()-t0:.0f}s total")
    print("  verified cells:", after["verified"])
    for row in after["order"]:
        print("   ", row)

    page.screenshot(path="shots/board-autoverified.png")
    browser.close()
