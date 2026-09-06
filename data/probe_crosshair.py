"""Hovering a cell must light its departure column and return row; clicking pins it."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=25)
ret = depart + timedelta(days=7)

STATE = """
() => {
  const t = document.querySelector('#board .card table.matrix');
  return {
    cols: t.querySelectorAll('.cross-col').length,
    rows: t.querySelectorAll('.cross-row').length,
    at: t.querySelectorAll('td.cross-at').length,
    colHeader: (t.querySelector('th.col.cross-col') || {}).textContent || null,
    rowHeader: (t.querySelector('th.row.cross-row') || {}).textContent || null,
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "0")
    page.fill("#dests", "2")
    page.uncheck("#autoverify")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 2", timeout=300000)
    page.wait_for_timeout(1200)

    print("before hover:", page.evaluate(STATE))

    page.hover("#board .card td.priced:nth-of-type(6)")
    page.wait_for_timeout(250)
    hovered = page.evaluate(STATE)
    print("on hover    :", hovered)
    print(f"   -> column header {hovered['colHeader']!r}, row header {hovered['rowHeader']!r}")

    # Move off the grid: highlight should clear (nothing pinned yet).
    page.hover(".controls")
    page.wait_for_timeout(250)
    print("after leave :", page.evaluate(STATE))

    # Click pins it, and it survives leaving the grid.
    page.click("#board .card td.priced:nth-of-type(6)")
    page.wait_for_timeout(400)
    page.hover(".controls")
    page.wait_for_timeout(300)
    print("after click+leave:", page.evaluate(STATE))

    page.screenshot(path="shots/board-crosshair.png")
    browser.close()
