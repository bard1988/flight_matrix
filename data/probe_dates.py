"""The return date must never sit before the departure date."""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page()
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")

    def state(label: str) -> None:
        dep = page.input_value("#depart")
        ret = page.input_value("#ret")
        low = page.get_attribute("#ret", "min")
        ok = "ok" if ret >= dep else "INVALID"
        print(f"  {label:32} depart={dep}  return={ret}  min={low}  {ok}")

    def set_depart(value: str) -> None:
        page.fill("#depart", value)
        page.dispatch_event("#depart", "change")
        page.wait_for_timeout(150)

    state("initial")

    set_depart("2026-11-20")
    state("depart pushed past return")

    page.fill("#ret", "2026-11-30")
    page.dispatch_event("#ret", "change")
    set_depart("2026-11-25")
    state("depart still before return")

    set_depart("2026-11-30")
    state("depart equals return")

    set_depart("2026-12-05")
    state("depart past it again")

    browser.close()
