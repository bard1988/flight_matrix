"""Clicking a cell should show flight times, and a Kiwi link with the right passengers."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
ADULTS = sys.argv[2] if len(sys.argv) > 2 else "2"
CHILDREN = sys.argv[3] if len(sys.argv) > 3 else "3"

dep = date.today() + timedelta(days=25)
ret = dep + timedelta(days=7)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", dep.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#adults", ADULTS)
    page.fill("#children", CHILDREN)
    page.fill("#dests", "2")
    page.uncheck("#autoverify")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 2", timeout=300000)
    page.wait_for_timeout(1200)

    page.click("#board .card td.best-board, #board .card td.best-here")
    page.wait_for_function(
        "document.querySelector('#panel .big') || document.querySelector('#panel .err')",
        timeout=180000)
    page.wait_for_timeout(700)

    print("--- panel ---")
    print(page.text_content("#panelbody"))
    print("\n--- links ---")
    for a in page.query_selector_all("#panel a"):
        print(f"  {a.text_content()} -> {a.get_attribute('href')}")
    page.screenshot(path="shots/panel-times.png")
    browser.close()
