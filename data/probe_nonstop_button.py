"""Two reported bugs:
   1. Nonstop-only still returns itineraries with a stop on the RETURN leg.
   2. Once the Search button goes amber (settings changed) it cannot be pressed again.

Runs with Auto cross-check ON, which is the default and which the earlier test disabled.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
dep = date.today() + timedelta(days=30)
ret = dep + timedelta(days=7)

BTN = """
() => {
  const b = document.getElementById('go');
  const cs = getComputedStyle(b);
  return {disabled: b.disabled, stale: b.classList.contains('stale'),
          pointerEvents: cs.pointerEvents, text: b.textContent};
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")

    page.fill("#depart", dep.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "0")
    page.fill("#dests", "2")
    page.check("#nonstop")            # <-- nonstop only
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 1", timeout=300000)
    page.wait_for_timeout(2500)
    print("after search, button:", page.evaluate(BTN))

    # 1. Ask the details endpoint for the cheapest cell and inspect BOTH legs' stops.
    info = page.evaluate("""
      () => {
        const c = document.querySelector('#board .card');
        const td = c.querySelector('td.best-board, td.best-here');
        return {dest: c.querySelector('.code').textContent.trim().split(' ')[0],
                title: td ? td.getAttribute('title') : null};
      }
    """)
    print("first card:", info)

    page.click("#board .card td.best-board, #board .card td.best-here")
    page.wait_for_function(
        "document.querySelector('#paneltimes') && document.querySelector('#paneltimes').innerHTML.length > 0",
        timeout=180000)
    page.wait_for_timeout(800)
    print("\npanel times block:")
    print(" ", page.text_content("#paneltimes"))

    # 2. Make the button stale, then try to press it.
    page.fill("#adults", "3")
    page.dispatch_event("#adults", "change")
    page.wait_for_timeout(400)
    print("\nafter changing adults, button:", page.evaluate(BTN))
    try:
        page.click("#go", timeout=5000)
        page.wait_for_timeout(2500)
        print("click succeeded; button now:", page.evaluate(BTN))
    except Exception as exc:
        print("CLICK FAILED:", type(exc).__name__, str(exc)[:120])

    if errors:
        print("\nJS errors:")
        for e in errors[:5]:
            print("  ", e[:160])
    browser.close()
