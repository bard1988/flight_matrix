"""Changing a fetch-affecting control must visibly mark the board stale.

View-only controls (weekday pickers) must NOT - they update the board immediately.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
depart = date.today() + timedelta(days=25)
ret = depart + timedelta(days=7)

STATE = """
() => ({
  stale: document.getElementById('go').classList.contains('stale'),
  note: document.getElementById('stalenote').hidden ? '' : document.getElementById('stalenote').textContent,
  firstCol: (document.querySelector('#board thead th.col') || {}).textContent || null,
  shown: document.querySelectorAll('#board td.priced:not(.excluded)').length,
})
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "0")
    page.fill("#dests", "2")
    page.uncheck("#autoverify")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 2", timeout=300000)
    page.wait_for_timeout(1200)
    print("after search        :", page.evaluate(STATE))

    print("\n-- view-only control (weekday) should NOT mark stale --")
    page.click("#dowdep button:nth-of-type(5)")
    page.wait_for_timeout(400)
    print("  after weekday click:", page.evaluate(STATE))

    print("\n-- fetch controls SHOULD mark stale --")
    for label, action in [
        ("change depart date", lambda: page.fill("#depart", (depart + timedelta(days=3)).isoformat())),
        ("change adults", lambda: page.fill("#adults", "3")),
        ("set depart hours", lambda: page.select_option("#dephfrom", "6")),
    ]:
        action()
        page.dispatch_event("#depart", "change")
        page.wait_for_timeout(300)
        s = page.evaluate(STATE)
        print(f"  {label:22} stale={s['stale']}  note={s['note'][:52]!r}")

    print("\n-- pressing Search clears it and rebuilds --")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 1", timeout=300000)
    page.wait_for_timeout(1500)
    print("  after search:", page.evaluate(STATE))
    browser.close()
