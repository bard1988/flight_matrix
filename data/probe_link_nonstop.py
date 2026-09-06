"""With nonstop checked, the Kiwi booking link must carry the direct-only filter."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
dep = date.today() + timedelta(days=30)
ret = dep + timedelta(days=7)

for nonstop in (True, False):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 900})
        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
        page.fill("#depart", dep.isoformat())
        page.fill("#ret", ret.isoformat())
        page.fill("#children", "0")
        page.fill("#dests", "1")
        page.uncheck("#autoverify")
        if nonstop:
            page.check("#nonstop")
        page.click("#go")
        page.wait_for_function("document.querySelectorAll('#board .card').length >= 1", timeout=300000)
        page.wait_for_timeout(1500)
        page.click("#board .card td.best-board, #board .card td.best-here")
        page.wait_for_function(
            "document.querySelector('#panel a') !== null", timeout=180000)
        page.wait_for_timeout(600)
        links = [a.get_attribute("href") for a in page.query_selector_all("#panel a")
                 if "kiwi.com" in (a.get_attribute("href") or "")]
        print(f"nonstop={nonstop}:")
        for l in links:
            print("  ", l)
            print("   carries stopNumber=0:", "stopNumber=0" in l)
        browser.close()
