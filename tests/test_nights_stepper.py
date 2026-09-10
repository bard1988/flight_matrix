"""The on-grid Nights min/max steppers.

Nights is a view filter (`state.constraints`), so narrowing recolours / re-ranks the
board instantly with no refetch; widening past the priced band auto-fetches the new
lengths for the grid on screen. The steppers live in the Single card head and the Multi
chips row and stay in sync with the Options fields and the Trip length preset.

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
RETURN = (date.today() + timedelta(days=52)).isoformat()


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


def _open_card(page, base):
    page.goto(f"{base}/?from=TLV&depart={DEPART}&ret={RETURN}&nmin=6&nmax=8&places=5")
    page.click("#go")
    page.wait_for_selector(".lrow", timeout=60_000)
    page.wait_for_function("() => document.querySelectorAll('#dlist .lrow').length >= 3", timeout=60_000)
    page.click(".lrow")
    page.wait_for_selector("#ddetail table.matrix", state="attached", timeout=60_000)
    page.wait_for_selector("#ddetail .nights-stepper", timeout=10_000)


def _min_dec(page):  return "#ddetail .nights-stepper .ns-group:first-of-type button:first-child"
def _max_dec(page):  return "#ddetail .nights-stepper .ns-group:last-of-type button:first-child"
def _max_inc(page):  return "#ddetail .nights-stepper .ns-group:last-of-type button:last-child"


def test_narrowing_nights_applies_live_without_a_fetch_or_a_stale_marker(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url)

        page.click(_max_dec(page))                     # 8 -> 7, still inside the priced band
        page.wait_for_function("() => state.constraints.max === 7", timeout=3_000)

        assert page.evaluate("() => document.getElementById('nmax').value === '7'")          # field synced
        assert page.evaluate("() => document.querySelector('#ddetail .nights-stepper').textContent.includes('7')")
        assert page.evaluate("() => document.getElementById('tripselect').value === 'custom'")  # preset synced
        assert not page.evaluate("() => document.getElementById('go').classList.contains('stale')")
        assert page.evaluate("() => state.nightsBand === null")     # narrowing never triggers the widen fetch
    finally:
        ctx.close()


def test_widening_nights_fetches_the_new_band(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url)
        n11 = ("() => [...document.querySelectorAll('#ddetail td.priced')].filter(td => td.dataset.dep && "
               "Math.round((new Date(td.dataset.ret) - new Date(td.dataset.dep)) / 864e5) === 11).length")
        assert page.evaluate(n11) == 0

        for _ in range(3):                             # 8 -> 11
            page.click(_max_inc(page))
        page.wait_for_function("() => state.constraints.max === 11", timeout=3_000)
        page.wait_for_function(n11 + " > 0", timeout=30_000)      # the extend stream fills them
        assert page.evaluate("() => state.meta.nights_span.includes(11)")
        assert page.evaluate("() => document.getElementById('nmax').value === '11'")
    finally:
        ctx.close()
