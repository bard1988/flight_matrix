"""Day-of-week / trip-length constraints must change the ANSWER, not just hide cells."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=25)
ret = depart + timedelta(days=7)

STATE = """
() => {
  const cards = [...document.querySelectorAll('#board .card')];
  const c = cards[0];
  const best = c.querySelector('td.best-board, td.best-here');
  return {
    order: cards.map(x => x.querySelector('h2').textContent + ' ' +
                          x.querySelector('.best').textContent.trim().replace(/\\s+/g,' ')),
    excluded: document.querySelectorAll('#board td.excluded').length,
    shown: document.querySelectorAll('#board td.priced:not(.excluded)').length,
    note: document.getElementById('constraintnote').textContent,
    bestCellTitle: best ? best.parentElement.parentElement.querySelector('th.row').textContent : null,
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "0")
    page.fill("#dests", "3")
    page.uncheck("#autoverify")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 3", timeout=300000)
    page.wait_for_timeout(1200)

    s = page.evaluate(STATE)
    print("unconstrained:")
    for row in s["order"]:
        print("   ", row)
    print(f"   shown={s['shown']} excluded={s['excluded']}")

    # Thursday departures (4), Sunday returns (0)
    page.click("#dowdep button:nth-of-type(5)")
    page.click("#dowret button:nth-of-type(1)")
    page.wait_for_timeout(400)
    s = page.evaluate(STATE)
    print("\nThu depart / Sun return:")
    for row in s["order"]:
        print("   ", row)
    print(f"   shown={s['shown']} excluded={s['excluded']}")
    print(f"   note: {s['note']}")

    # Add a nights range on top
    page.fill("#nmin", "2")
    page.fill("#nmax", "4")
    page.wait_for_timeout(400)
    s = page.evaluate(STATE)
    print("\n+ 2-4 nights:")
    for row in s["order"]:
        print("   ", row)
    print(f"   shown={s['shown']} excluded={s['excluded']}")
    print(f"   note: {s['note']}")

    page.click("#clearconstraints")
    page.wait_for_timeout(400)
    s = page.evaluate(STATE)
    print(f"\ncleared: shown={s['shown']} excluded={s['excluded']} note={s['note']!r}")

    page.screenshot(path="shots/board-constraints.png")
    browser.close()
