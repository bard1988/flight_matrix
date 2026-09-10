"""Browser Back steps out of an overlay; it does not leave the board.

Regression for: open a destination's grid, press the browser Back button, and the whole
board was gone — the board is one `history.replaceState` entry, so Back navigated off the
page. It should behave like the "‹ All destinations" control: collapse the focus layer
and show the ranked list. A cell sheet opened over the grid gets its own entry too, so
Back closes the sheet first, then the grid.

Needs the dev extras (`pip install -r requirements-dev.txt` then `playwright install
chromium`); skipped otherwise so it never breaks a plain `pytest` run.
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
RETURN = (date.today() + timedelta(days=110)).isoformat()


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


def _open_board(page, base: str):
    page.goto(f"{base}/?from=TLV&depart={DEPART}&ret={RETURN}&nmin=6&nmax=8&places=6&run=1")
    page.wait_for_selector(".lrow", timeout=60_000)


def _detail_open(page) -> bool:
    return page.evaluate("() => document.body.classList.contains('detail-open')")


def _panel_open(page) -> bool:
    return page.evaluate("() => document.getElementById('panel').classList.contains('open')")


@pytest.mark.parametrize("mobile", [True, False], ids=["mobile", "desktop"])
def test_back_from_a_card_returns_to_the_list(demo_url, browser, mobile):
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 800},
        has_touch=mobile, is_mobile=mobile,
    )
    page = ctx.new_page()
    try:
        _open_board(page, demo_url)
        page.click(".lrow")
        page.wait_for_selector("table.matrix", state="attached", timeout=60_000)
        assert _detail_open(page)

        page.go_back()
        page.wait_for_function("() => !document.body.classList.contains('detail-open')", timeout=5_000)
        # The board is still here — Back did not leave the page.
        assert page.evaluate("() => document.body.classList.contains('has-board')")
        assert page.locator(".lrow").first.is_visible()
    finally:
        ctx.close()


def test_back_closes_the_cell_sheet_before_the_card(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_board(page, demo_url)
        page.click(".lrow")
        page.wait_for_selector("#ddetail table.matrix td.priced", timeout=60_000)
        page.click("#ddetail table.matrix td.priced")
        page.wait_for_function("() => document.getElementById('panel').classList.contains('open')",
                               timeout=10_000)

        page.go_back()
        page.wait_for_function("() => !document.getElementById('panel').classList.contains('open')",
                               timeout=5_000)
        assert _detail_open(page), "first Back should close the sheet but leave the grid"

        page.go_back()
        page.wait_for_function("() => !document.body.classList.contains('detail-open')", timeout=5_000)
        assert page.evaluate("() => document.body.classList.contains('has-board')")
    finally:
        ctx.close()
