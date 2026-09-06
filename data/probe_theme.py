"""Reproduce 'text is invisible' / 'only one location'.

Exercises the OS-dark-mode path (@media prefers-color-scheme) which the theme toggle
bypasses, at a realistic desktop viewport.

    py -3 data/probe_theme.py [port] [width] [height]
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8712"
W = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
H = int(sys.argv[3]) if len(sys.argv) > 3 else 720

depart = date.today() + timedelta(days=21)
ret = depart + timedelta(days=7)

JS = """
() => {
  const root = getComputedStyle(document.documentElement);
  const td = document.querySelector('#board td.priced');
  const flip = document.querySelector('#board td.priced.ink-flip');
  const read = (el) => {
    if (!el) return null;
    const cs = getComputedStyle(el);
    return {text: el.textContent.trim(), color: cs.color, bg: cs.backgroundColor};
  };
  const board = document.querySelector('.board');
  return {
    tokens: {
      inkOnFill: root.getPropertyValue('--ink-on-fill').trim(),
      inkFlipped: root.getPropertyValue('--ink-flipped').trim(),
      rampFlip: root.getPropertyValue('--ramp-flip').trim(),
      q0: root.getPropertyValue('--q0').trim(),
      q6: root.getPropertyValue('--q6').trim(),
      surface: root.getPropertyValue('--surface-1').trim(),
    },
    normalCell: read(td),
    flippedCell: read(flip),
    cards: document.querySelectorAll('#board .card').length,
    boardCols: getComputedStyle(board).gridTemplateColumns,
    cardWidth: document.querySelector('#board .card')?.getBoundingClientRect().width,
    pageHeight: document.body.scrollHeight,
    viewportHeight: window.innerHeight,
  };
}
"""

for scheme in ("light", "dark"):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, color_scheme=scheme)
        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
        page.fill("#depart", depart.isoformat())
        page.fill("#ret", ret.isoformat())
        page.fill("#children", "3")
        page.fill("#dests", "6")
        page.click("#go")
        page.wait_for_function("document.querySelectorAll('#board .card').length >= 3", timeout=90000)
        page.wait_for_timeout(800)
        data = page.evaluate(JS)
        print(f"=== OS scheme: {scheme}  viewport {W}x{H} ===")
        print("  tokens      :", data["tokens"])
        print("  normal cell :", data["normalCell"])
        print("  flipped cell:", data["flippedCell"])
        print(f"  cards={data['cards']}  cols={data['boardCols']}  cardWidth={data['cardWidth']}")
        print(f"  page height {data['pageHeight']} vs viewport {data['viewportHeight']}")
        page.screenshot(path=f"shots/os-{scheme}-{W}x{H}.png")
        print()
        browser.close()
