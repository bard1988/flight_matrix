"""The locate button must scroll a card's grid to its own cheapest cell."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=21)
ret = depart + timedelta(days=7)

STATE = """
() => {
  const card = [...document.querySelectorAll('#board .card')][1] || document.querySelector('#board .card');
  const wrap = card.querySelector('.matrix-wrap');
  const best = card.querySelector('td.best-board') || card.querySelector('td.best-here');
  const wr = wrap.getBoundingClientRect(), br = best.getBoundingClientRect();
  return {
    city: card.querySelector('h2').textContent,
    scroll: {x: Math.round(wrap.scrollLeft), y: Math.round(wrap.scrollTop)},
    bestText: best.textContent.trim(),
    visible: br.left >= wr.left - 1 && br.right <= wr.right + 1 &&
             br.top >= wr.top - 1 && br.bottom <= wr.bottom + 1,
    flashing: best.classList.contains('flash'),
    status: document.getElementById('growing').textContent,
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
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 2", timeout=180000)
    page.wait_for_timeout(1200)

    # Widen so the grid is far bigger than its viewport and the winner is off-screen.
    page.click("#board .card .card-head button.fillbtn:last-of-type")
    page.wait_for_function("document.getElementById('growing').hidden === true", timeout=300000)
    page.wait_for_timeout(800)

    # Scroll the second card away from its cheapest cell.
    page.eval_on_selector_all(
        "#board .card .matrix-wrap",
        "els => els.forEach(e => { e.scrollLeft = e.scrollWidth; e.scrollTop = e.scrollHeight; })")
    page.wait_for_timeout(400)
    before = page.evaluate(STATE)
    print(f"before locate ({before['city']}): scroll={before['scroll']} "
          f"best={before['bestText']!r} visible={before['visible']}")

    page.click("#board .card:nth-of-type(2) .card-head button.locate")
    page.wait_for_timeout(1200)
    after = page.evaluate(STATE)
    print(f"after  locate ({after['city']}): scroll={after['scroll']} "
          f"best={after['bestText']!r} visible={after['visible']} flashing={after['flashing']}")
    print(f"status: {after['status']!r}")

    page.screenshot(path="shots/board-located.png")
    browser.close()
