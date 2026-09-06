"""Check the coverage/horizon warning renders for a far-out window."""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8713"
DAYS_OUT = int(sys.argv[2]) if len(sys.argv) > 2 else 150

depart = date.today() + timedelta(days=DAYS_OUT)
ret = depart + timedelta(days=7)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1680, "height": 1000})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", depart.isoformat())
    page.fill("#ret", ret.isoformat())
    page.fill("#children", "3")
    page.fill("#dests", "6")
    page.click("#go")
    page.wait_for_function(
        "document.getElementById('go').disabled === false && "
        "document.getElementById('progress').textContent !== 'Finding destinations…'",
        timeout=120000,
    )
    page.wait_for_timeout(500)
    print(f"depart {depart} ({DAYS_OUT} days out)")
    print("  progress:", page.text_content("#progress"))
    print("  note    :", page.text_content("#note"))
    print("  note shown:", page.is_visible("#note"))
    print("  cards   :", page.eval_on_selector_all("#board .card", "els => els.length"))
    page.screenshot(path=f"shots/board-far-{DAYS_OUT}d.png")
    browser.close()
