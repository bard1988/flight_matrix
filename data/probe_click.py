"""Click the board's cheapest cell and confirm the live verification lands in the UI."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8713"
DAYS_OUT = int(sys.argv[2]) if len(sys.argv) > 2 else 21

depart = date.today() + timedelta(days=DAYS_OUT)
ret = depart + timedelta(days=7)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1680, "height": 1100})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#adults", "2")
    page.fill("#children", "3")
    page.fill("#dests", "4")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 4", timeout=90000)
    page.wait_for_timeout(500)

    before = page.eval_on_selector_all(
        "#board .card", "els => els.map(e => e.querySelector('h2').textContent + ' ' + e.querySelector('.best').textContent)"
    )
    print("card order BEFORE click:")
    for row in before:
        print("   ", row)

    target = page.query_selector("#board td.best-board")
    print("\nclicking the board-best cell:", target.text_content().strip() if target else "NOT FOUND")
    target.click()
    page.wait_for_function(
        "document.querySelector('#panel .big') !== null || document.querySelector('#panel .err') !== null",
        timeout=120000,
    )
    page.wait_for_timeout(400)

    print("\npanel:")
    print("  ", " | ".join(page.text_content("#panelbody").split("\n")[:6]))

    verified = page.eval_on_selector_all("#board td.verified", "els => els.length")
    after = page.eval_on_selector_all(
        "#board .card", "els => els.map(e => e.querySelector('h2').textContent + ' ' + e.querySelector('.best').textContent)"
    )
    print(f"\nverified cells on board: {verified}")
    print("card order AFTER click:")
    for row in after:
        print("   ", row)

    page.screenshot(path="shots/verified-click.png")
    browser.close()
