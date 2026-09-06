"""Drive the board in a headless browser and screenshot it, light and dark.

Dev aid for eyeballing the heatmap (the colour validator checks colour, not layout).
    py -3 data/shoot.py [port]
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from datetime import date, timedelta

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
DAYS_OUT = int(sys.argv[2]) if len(sys.argv) > 2 else 21
DESTS = sys.argv[3] if len(sys.argv) > 3 else "6"
TAG = sys.argv[4] if len(sys.argv) > 4 else ""
DEPART = (date.today() + timedelta(days=DAYS_OUT)).isoformat()
RETURN = (date.today() + timedelta(days=DAYS_OUT + 7)).isoformat()
OUT = Path(__file__).resolve().parent.parent / "shots"


def run() -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in ("light", "dark"):
            page = browser.new_page(viewport={"width": 1680, "height": 1150})
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")

            page.fill("#depart", DEPART)
            page.fill("#ret", RETURN)
            page.fill("#adults", "2")
            page.fill("#children", "3")
            page.fill("#dests", DESTS)
            page.click("#go")
            page.wait_for_selector("#board .card", timeout=60000)
            page.wait_for_function(
                f"document.querySelectorAll('#board .card').length >= {DESTS}", timeout=60000
            )
            page.wait_for_timeout(600)

            page.screenshot(path=str(OUT / f"board{TAG}-{theme}.png"))

            # Hover a priced cell so the tooltip is in the shot too.
            cell = page.query_selector("#board .card td.priced")
            if cell:
                cell.hover()
                page.wait_for_timeout(250)
                page.screenshot(path=str(OUT / f"tooltip{TAG}-{theme}.png"), clip={"x": 0, "y": 0, "width": 900, "height": 700})
            page.close()
        browser.close()
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    run()
