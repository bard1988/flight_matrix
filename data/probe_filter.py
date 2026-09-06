"""Destination filter: matches city / IATA / country, instantly, with no refetch."""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=21)
ret = depart + timedelta(days=7)

SHOWN = """
() => ({
  cards: [...document.querySelectorAll('#board .card h2')].map(h => h.textContent),
  count: document.getElementById('filtercount').textContent,
  tableRows: document.querySelectorAll('#tableview tbody tr').length,
  winner: (document.querySelector('#board .card.is-winner h2') || {}).textContent || null,
})
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "3")
    page.fill("#dests", "8")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 4", timeout=180000)
    page.wait_for_timeout(1500)

    base = page.evaluate(SHOWN)
    print(f"unfiltered: {len(base['cards'])} cards -> {base['cards']}")
    print(f"  winner card: {base['winner']}")

    for query in ["ath", "larn", "IT", "cy", "zzz", ""]:
        t0 = time.time()
        page.fill("#destfilter", query)
        page.wait_for_timeout(180)
        s = page.evaluate(SHOWN)
        print(f"\nfilter {query!r:8} -> {len(s['cards'])} cards in {(time.time()-t0)*1000:.0f}ms")
        print(f"   {s['cards']}")
        print(f"   status: {s['count']!r}  winner: {s['winner']}  table rows: {s['tableRows']}")

    page.screenshot(path="shots/board-filtered.png")
    browser.close()
