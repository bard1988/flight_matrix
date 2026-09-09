"""Two phone-only layout regressions.

1. The destination tree popover lives inside `.field-dest`, so the mobile
   `.field input { width: 100% }` / `min-height: 44px` rules used to hit every tree
   checkbox and blow it up to the full row width — shoving each country name to zero
   width. On a phone the tree looked empty. `.region-tree input[type='checkbox']` now
   pins a real 16px box.

2. The Table/Matrix toggle used to sit in the board toolbar above the ranked list;
   pressed there on a phone it read as "open something as a table" and swapped a
   full-screen table in over the list. It now lives in the open-destination head
   (`.detail-astable`), so it only ever changes how the OPEN destination is drawn; the
   toolbar button (`#tabletoggle`) is hidden on a phone.

Needs the dev extras (`pip install -r requirements-dev.txt` then `playwright install
chromium`); skipped otherwise.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
DEPART = (date.today() + timedelta(days=30)).isoformat()
RETURN = (date.today() + timedelta(days=44)).isoformat()
PHONE = {"width": 390, "height": 844}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def demo_url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py"), "--demo", "--no-open",
         "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("demo server did not come up")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def browser():
    try:
        with sync_api.sync_playwright() as pw:
            try:
                b = pw.chromium.launch()
            except Exception as exc:                       # noqa: BLE001
                pytest.skip(f"no chromium for playwright ({exc}); run `playwright install chromium`")
            yield b
            b.close()
    except Exception as exc:                               # noqa: BLE001
        pytest.skip(f"playwright unavailable ({exc})")


@pytest.fixture()
def phone(browser):
    ctx = browser.new_context(viewport=PHONE, has_touch=True, is_mobile=True)
    page = ctx.new_page()
    try:
        yield page
    finally:
        ctx.close()


def test_region_tree_labels_have_width_on_a_phone(phone, demo_url):
    phone.goto(demo_url)
    phone.wait_for_selector(".region-tree .rname", state="attached", timeout=30_000)
    phone.click("#regionsearch")
    phone.wait_for_selector("#destpop:not([hidden])", timeout=5_000)
    # Expand the first two continents so subregion and country rows are on screen too.
    for toggle in phone.locator(".region-tree > .rnode > .rhead > .rtoggle").all()[:2]:
        toggle.click()

    labels = phone.evaluate(
        """() => {
          const pop = document.querySelector('#destpop').getBoundingClientRect();
          return [...document.querySelectorAll('.region-tree .rname')]
            .map(el => {
              const r = el.getBoundingClientRect();
              return {t: el.textContent.trim(), w: r.width,
                      shown: r.width > 0 && r.height > 0,
                      inside: r.left >= pop.left - 1 && r.right <= pop.right + 1};
            })
            .filter(n => n.shown && n.t);
        }"""
    )
    assert len(labels) >= 8, f"expansion revealed too few rows: {labels}"
    thin = [n["t"] for n in labels if n["w"] < 15]
    assert not thin, f"these visible region labels collapsed to ~0 width: {thin}"
    assert all(n["inside"] for n in labels), \
        f"region labels spilled outside the popover: {[n['t'] for n in labels if not n['inside']]}"


def _run_board(page, demo_url):
    page.goto(f"{demo_url}/?from=TLV&depart={DEPART}&ret={RETURN}&nmin=6&nmax=8&places=6&run=1")
    page.wait_for_selector(".lrow", timeout=60_000)
    page.wait_for_timeout(1500)


def test_table_toggle_is_in_the_detail_head_not_the_list(phone, demo_url):
    _run_board(phone, demo_url)

    # On the list, there is no Table button at all — nothing to mis-press.
    assert phone.evaluate("() => getComputedStyle(document.querySelector('#tabletoggle')).display") == "none"
    assert "detail-open" not in phone.evaluate("() => document.body.className")

    # Open a destination: the toggle appears in its head, the grid shows, the table does not.
    phone.click(".lrow")
    phone.wait_for_selector("body.detail-open .ddetail .card.is-open", timeout=5_000)
    state = phone.evaluate(
        """() => {
          const vis = s => { const e = document.querySelector(s); if (!e) return false;
            const r = e.getBoundingClientRect(); const c = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && c.display !== 'none'; };
          return {astable: vis('.detail-astable'), grid: vis('.ddetail'), table: vis('.tableview')};
        }"""
    )
    assert state == {"astable": True, "grid": True, "table": False}

    # Tap it: the table swaps in over the grid, with its own way back.
    phone.click(".detail-astable")
    phone.wait_for_timeout(300)
    swapped = phone.evaluate(
        """() => {
          const vis = s => { const e = document.querySelector(s); if (!e) return false;
            const r = e.getBoundingClientRect(); const c = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && c.display !== 'none'; };
          return {cls: document.body.className, grid: vis('.ddetail'),
                  table: vis('.tableview'), back: vis('.table-back'),
                  rows: document.querySelectorAll('.tableview tbody tr').length};
        }"""
    )
    assert "show-table" in swapped["cls"]
    assert swapped["table"] and not swapped["grid"]
    assert swapped["back"] and swapped["rows"] > 0

    # The table's own back control returns to the grid.
    phone.click(".table-back")
    phone.wait_for_timeout(300)
    back = phone.evaluate(
        """() => {
          const vis = s => { const e = document.querySelector(s); if (!e) return false;
            const r = e.getBoundingClientRect(); const c = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && c.display !== 'none'; };
          return {cls: document.body.className, grid: vis('.ddetail'), table: vis('.tableview')};
        }"""
    )
    assert "show-table" not in back["cls"]
    assert back["grid"] and not back["table"]
