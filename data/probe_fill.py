"""Exercise bulk live fill end to end through the UI."""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
DAYS_OUT = int(sys.argv[2]) if len(sys.argv) > 2 else 21

depart = date.today() + timedelta(days=DAYS_OUT)
ret = depart + timedelta(days=7)

STATS = """
() => {
  const cards = [...document.querySelectorAll('#board .card')];
  const c = cards[0];
  return {
    city: c.querySelector('h2').textContent,
    head: c.querySelector('.best').textContent.trim(),
    cov: c.querySelector('.cov').textContent,
    verified: c.querySelectorAll('td.verified').length,
    priced: c.querySelectorAll('td.priced').length,
    nodata: c.querySelectorAll('td.nodata').length,
    btn: c.querySelector('.fillbtn').textContent,
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#adults", "2")
    page.fill("#children", "3")
    page.fill("#dests", "3")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 2", timeout=90000)
    page.wait_for_timeout(800)

    print("BEFORE fill:", page.evaluate(STATS))

    start = time.time()
    page.click("#board .card .fillbtn")
    page.wait_for_timeout(2000)
    print("during   :", page.evaluate(STATS))

    # Wait for the button to return to its idle label.
    page.wait_for_function(
        "document.querySelector('#board .card .fillbtn').textContent.trim() === 'Fill live'",
        timeout=600000,
    )
    page.wait_for_timeout(800)
    elapsed = time.time() - start
    print(f"AFTER fill ({elapsed:.0f}s):", page.evaluate(STATS))
    print("status:", page.text_content("#progress"))

    page.screenshot(path="shots/board-filled.png")
    browser.close()
