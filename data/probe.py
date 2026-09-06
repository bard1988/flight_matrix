"""Inspect the rendered board's DOM: cell class counts, ramp usage, void placement."""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"

JS = """
() => {
  const card = document.querySelector('#board .card');
  const rows = [...card.querySelectorAll('tbody tr')];
  const counts = {};
  let rampUse = {};
  for (const td of document.querySelectorAll('#board td')) {
    const k = td.className || 'plain';
    counts[k] = (counts[k] || 0) + 1;
    if (td.classList.contains('priced')) {
      const bg = td.style.background;
      rampUse[bg] = (rampUse[bg] || 0) + 1;
    }
  }
  // First row of the first card: return date == earliest return.
  const first = rows[0];
  const cells = [...first.querySelectorAll('td')].map(td => td.className.split(' ')[0]);
  const last = [...rows[rows.length-1].querySelectorAll('td')].map(td => td.className.split(' ')[0]);
  return {
    cards: document.querySelectorAll('#board .card').length,
    counts, rampUse,
    firstRowLabel: first.querySelector('th').textContent,
    firstRow: cells,
    lastRowLabel: rows[rows.length-1].querySelector('th').textContent,
    lastRow: last,
  };
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1680, "height": 1150})
    page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
    page.fill("#depart", "2026-12-10")
    page.fill("#ret", "2026-12-17")
    page.fill("#children", "3")
    page.fill("#dests", "6")
    page.click("#go")
    page.wait_for_function("document.querySelectorAll('#board .card').length >= 6", timeout=30000)
    page.wait_for_timeout(500)
    data = page.evaluate(JS)
    browser.close()

print("cards:", data["cards"])
print("\nclass counts:")
for k, v in sorted(data["counts"].items(), key=lambda x: -x[1]):
    print(f"  {v:5}  {k}")
print("\nramp step usage (priced cells):")
for k, v in sorted(data["rampUse"].items()):
    print(f"  {v:5}  {k}")
print(f"\nfirst row ({data['firstRowLabel']}):")
print("  ", data["firstRow"])
print(f"last row ({data['lastRowLabel']}):")
print("  ", data["lastRow"])
