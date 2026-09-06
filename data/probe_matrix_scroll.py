"""Confirm each matrix scrolls in both axes, axes stay pinned, and position is kept."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=21)
ret = depart + timedelta(days=7)

STATS = """
() => {
  const cards = [...document.querySelectorAll('#board .card')];
  const c = cards[0];
  const w = c.querySelector('.matrix-wrap');
  const firstCol = c.querySelector('thead th.col');
  const firstRowHead = c.querySelector('tbody th.row');
  const cs = (el) => getComputedStyle(el);
  return {
    cards: cards.length,
    boardCols: getComputedStyle(document.querySelector('.board')).gridTemplateColumns,
    cardW: Math.round(c.clientWidth),
    viewW: Math.round(w.clientWidth), contentW: Math.round(w.scrollWidth),
    viewH: Math.round(w.clientHeight), contentH: Math.round(w.scrollHeight),
    scrollableX: w.scrollWidth > w.clientWidth,
    scrollableY: w.scrollHeight > w.clientHeight,
    colSticky: cs(firstCol).position, colTop: cs(firstCol).top,
    rowSticky: cs(firstRowHead).position, rowLeft: cs(firstRowHead).left,
    at: {x: Math.round(w.scrollLeft), y: Math.round(w.scrollTop)},
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "3")
    page.fill("#dests", "4")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 3", timeout=180000)
    page.wait_for_timeout(1000)

    s = page.evaluate(STATS)
    print("initial:")
    for k, v in s.items():
        print(f"   {k}: {v}")

    print("\nscrolling the first matrix right + down...")
    page.eval_on_selector("#board .card .matrix-wrap",
                          "el => { el.scrollLeft = 140; el.scrollTop = 90; }")
    page.wait_for_timeout(400)
    s2 = page.evaluate(STATS)
    print("   at:", s2["at"], " (axes remain sticky:",
          s2["colSticky"], "/", s2["rowSticky"], ")")

    # A plain wheel at the edge must NOT widen; only sustained overscroll should.
    print("\none small wheel nudge at the right edge (should NOT widen):")
    page.eval_on_selector("#board .card .matrix-wrap", "el => el.scrollLeft = el.scrollWidth")
    page.wait_for_timeout(200)
    page.eval_on_selector(
        "#board .card .matrix-wrap",
        "el => el.dispatchEvent(new WheelEvent('wheel', {deltaX: 40, bubbles: true}))")
    page.wait_for_timeout(500)
    print("   growing text:", repr(page.text_content("#growing")))
    print("   columns still:", page.eval_on_selector_all("#board .card thead th.col", "e => e.length"))

    page.screenshot(path="shots/board-scrollable.png")
    browser.close()
