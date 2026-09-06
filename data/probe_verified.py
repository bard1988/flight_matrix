"""Check that a seeded verified cell overlays the cached estimate on the board."""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"

JS = """
() => {
  const cards = [...document.querySelectorAll('#board .card')];
  const lca = cards.find(c => c.querySelector('.code').textContent.includes('LCA'));
  if (!lca) return {error: 'no LCA card'};
  const verified = [...lca.querySelectorAll('td.verified')];
  return {
    verifiedCount: document.querySelectorAll('#board td.verified').length,
    lcaVerified: verified.map(td => td.textContent.trim()),
    lcaBest: lca.querySelector('.best').textContent,
    cardOrder: cards.map(c => c.querySelector('h2').textContent),
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1680, "height": 1150})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", "2026-12-10")
    page.fill("#ret", "2026-12-17")
    page.fill("#adults", "2")
    page.fill("#children", "3")
    page.fill("#dests", "6")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 6", timeout=30000)
    page.wait_for_timeout(500)
    print(page.evaluate(JS))
    browser.close()
