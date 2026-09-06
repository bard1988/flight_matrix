"""Scroll a matrix to its edge and confirm the date window grows and refills."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=21)
ret = depart + timedelta(days=7)

STATS = """
() => {
  const card = document.querySelector('#board .card');
  const wrap = card.querySelector('.matrix-wrap');
  return {
    cols: card.querySelectorAll('thead th.col').length,
    rows: card.querySelectorAll('tbody tr').length,
    priced: card.querySelectorAll('td.priced').length,
    cov: card.querySelector('.cov').textContent,
    scrollW: wrap.scrollWidth, clientW: wrap.clientWidth,
    scrollH: wrap.scrollHeight, clientH: wrap.clientHeight,
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "3")
    page.fill("#dests", "2")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 2", timeout=120000)
    page.wait_for_timeout(1000)

    before = page.evaluate(STATS)
    print("BEFORE:", before)
    print("  scrollable X:", before["scrollW"] > before["clientW"],
          " Y:", before["scrollH"] > before["clientH"])

    # A fresh 15x15 fits its card, so there is nothing to scroll yet: use the explicit
    # widen control first, then verify scrolling extends further once it does overflow.
    print("\nclicking the widen control...")
    page.click("#board .card .card-head button.fillbtn:last-of-type")
    page.wait_for_timeout(600)
    print("  growing indicator:", page.text_content("#growing"))

    page.wait_for_function(
        "document.getElementById('growing').hidden === true", timeout=180000
    )
    page.wait_for_timeout(800)
    after = page.evaluate(STATS)
    print("\nAFTER :", after)
    print(f"\ncolumns {before['cols']} -> {after['cols']},  rows {before['rows']} -> {after['rows']}")
    print(f"priced cells {before['priced']} -> {after['priced']}")
    print("  now scrollable X:", after["scrollW"] > after["clientW"],
          " Y:", after["scrollH"] > after["clientH"])

    if after["scrollW"] > after["clientW"]:
        print("\nnow scrolling to the right edge to trigger a further widening...")
        page.eval_on_selector("#board .card .matrix-wrap", "el => el.scrollLeft = el.scrollWidth")
        page.wait_for_timeout(700)
        growing = page.text_content("#growing")
        print("  growing indicator:", growing or "(none)")
        if growing:
            page.wait_for_function("document.getElementById('growing').hidden === true",
                                   timeout=240000)
            page.wait_for_timeout(600)
            final = page.evaluate(STATS)
            print(f"  columns {after['cols']} -> {final['cols']}, rows {after['rows']} -> {final['rows']}")

    page.screenshot(path="shots/board-extended.png")
    browser.close()
