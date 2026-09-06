"""Check no card clips its grid at a range of viewport widths."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=21)
ret = depart + timedelta(days=7)

JS = """
() => [...document.querySelectorAll('#board .card')].map(c => {
  const t = c.querySelector('table.matrix');
  return {
    city: c.querySelector('h2').textContent,
    cardInner: Math.round(c.clientWidth),
    tableWidth: Math.round(t.scrollWidth),
    clipped: t.scrollWidth > c.clientWidth + 1,
    cols: [...c.querySelectorAll('thead th.col')].length,
  };
})
"""

for width in (1024, 1366, 1600, 1920):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
        page.fill("#depart", depart.isoformat())
        page.fill("#ret", ret.isoformat())
        page.fill("#children", "3")
        page.fill("#dests", "3")
        page.click("#go")
        page.wait_for_function("document.querySelectorAll('#board .card').length >= 2", timeout=90000)
        page.wait_for_timeout(600)
        rows = page.evaluate(JS)
        cols = page.eval_on_selector(".board", "e => getComputedStyle(e).gridTemplateColumns")
        bad = [r for r in rows if r["clipped"]]
        print(f"{width}px  grid={cols}")
        for r in rows:
            flag = "CLIPPED" if r["clipped"] else "ok"
            print(f"    {r['city'][:12]:12} card={r['cardInner']:4} table={r['tableWidth']:4} cols={r['cols']} {flag}")
        browser.close()
