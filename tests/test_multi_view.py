"""The Single / Multi board toggle.

Multi replaces the ranked list + focus layer with one combined departure x return grid
where every cell stacks the chosen destinations, each shaded against its own range. This
checks the toggle seeds the grid from the three cheapest, that a cell click still opens
the live-price panel, and that switching back to Single restores the list unchanged.

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


def _board(page, base: str):
    page.goto(f"{base}/?from=TLV&depart={DEPART}&ret={RETURN}&nmin=6&nmax=8&places=6")
    page.click("#go")
    page.wait_for_selector(".lrow", timeout=60_000)
    # let a few destinations stream in
    page.wait_for_function("() => document.querySelectorAll('#dlist .lrow').length >= 4", timeout=60_000)


def test_multi_toggle_builds_a_combined_grid_from_the_top_three(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _board(page, demo_url)

        page.click("#viewmulti")
        page.wait_for_function("() => document.querySelectorAll('#multichips .mchip').length === 3", timeout=10_000)
        page.wait_for_selector("#multigrid .msub", timeout=10_000)

        # every cell stacks all three destinations
        assert page.evaluate("() => [...document.querySelectorAll('.mstack')].every(s => s.children.length === 3)")
        # each destination is shaded against its own scale -> the ramp classes are in use
        assert page.evaluate("() => document.querySelectorAll('.msub[class*=\"q\"]').length > 20")
        assert page.evaluate("() => new URLSearchParams(location.search).get('view') === 'multi'")

        # a cell click opens the live-price panel, same as Single
        page.click("#multigrid .msub[class*='q']")
        page.wait_for_function("() => document.getElementById('panel').classList.contains('open')", timeout=10_000)

        # back to Single -> the ranked list is intact
        page.evaluate("() => document.getElementById('panelclose').click()")
        page.click("#viewsingle")
        page.wait_for_function("() => !document.body.classList.contains('show-multi')", timeout=5_000)
        assert page.locator("#dlist .lrow").first.is_visible()
        assert page.evaluate("() => !new URLSearchParams(location.search).has('view')")
    finally:
        ctx.close()


def test_hide_and_remove_a_destination_from_the_grid(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _board(page, demo_url)
        page.click("#viewmulti")
        page.wait_for_selector("#multigrid .msub", timeout=10_000)

        page.click("#multichips .mchip-vis >> nth=1")              # hide the 2nd destination
        page.wait_for_function("() => document.querySelector('.mstack').children.length === 2", timeout=5_000)
        assert page.locator("#multichips .mchip.hid").count() == 1

        page.click("#multichips .mchip-vis >> nth=1")              # show it again
        page.wait_for_function("() => document.querySelector('.mstack').children.length === 3", timeout=5_000)

        page.click("#multichips .mchip-x >> nth=2")                # remove the 3rd entirely
        page.wait_for_function("() => document.querySelectorAll('#multichips .mchip').length === 2", timeout=5_000)
        assert page.evaluate("() => document.querySelector('.mstack').children.length === 2")
    finally:
        ctx.close()


def test_hiding_preserves_relative_scroll_not_a_clamped_pixel_offset(demo_url, browser):
    """Reported as the grid "jumping" to a different spot when a destination is hidden.

    Stacked density lays a cell's destinations out horizontally within their column, so
    hiding one narrows every column and shrinks the table's scrollWIDTH (measured: hiding
    one of three shrank it by nearly a third), not its height. Re-applying the old
    scrollLeft pixel-for-pixel against the rebuilt (now narrower) table gets clamped by
    the browser -- often straight to the right edge, which is the reported "jump".
    Scroll position is preserved as a FRACTION of the scrollable range instead.
    """
    ctx = browser.new_context(viewport={"width": 1280, "height": 700})
    page = ctx.new_page()
    try:
        _board(page, demo_url)
        page.click("#viewmulti")
        page.wait_for_selector("#multigrid .msub", timeout=10_000)
        # Stacked density is what makes a column's width depend on how many destinations
        # are shown -- Strip (the desktop default) gives every column a fixed width. A
        # narrow viewport clamps every column to its CSS min-width regardless, which
        # hides the effect entirely -- this needs room for a column to actually shrink.
        page.evaluate("() => { state.multi.density = 'stack'; render(); }")

        metrics = ("() => { const w = document.getElementById('multiwrap'); "
                   "return {sl: w.scrollLeft, max: w.scrollWidth - w.clientWidth}; }")
        before = page.evaluate(metrics)
        assert before["max"] > 40, f"grid barely scrolls ({before['max']}px); widen the fixture"
        page.evaluate(f"() => {{ document.getElementById('multiwrap').scrollLeft = {before['max'] // 2}; }}")
        mid = page.evaluate(metrics)
        fraction_before = mid["sl"] / before["max"]
        assert 0.3 < fraction_before < 0.7          # actually landed mid-scroll, not clamped already

        page.click("#multichips .mchip-vis >> nth=1")     # hide a destination -> columns narrow
        page.wait_for_function("() => document.querySelector('.mstack').children.length === 2", timeout=5_000)

        after = page.evaluate(metrics)
        assert after["max"] < before["max"], "hiding a destination should narrow the scrollable table"
        fraction_after = after["sl"] / after["max"] if after["max"] else 1
        assert abs(fraction_after - fraction_before) < 0.1, (
            f"scroll fraction moved from {fraction_before:.2f} to {fraction_after:.2f} -- "
            "looks like exactly the reported jump"
        )
    finally:
        ctx.close()
