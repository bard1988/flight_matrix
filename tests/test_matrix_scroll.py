"""The open destination's grid must not jump while you scroll it.

Regression for: on a phone, opening a destination and scrolling its matrix, the grid
kept snapping back to where it started. Cause: a background repaint (auto-verify, the
open-destination live fill) called render(), which rebuilt the whole detail card and
threw away the .matrix-wrap the user was scrolling.

The fix (frontend/app.js): render() reuses the existing scroll container for the open
grid — refreshOpenCard() swaps only the head and the table and re-asserts the scroll
offset synchronously — and holds a repaint back entirely while a scroll is in flight,
flushing it once the scroll settles.

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
RETURN = (date.today() + timedelta(days=110)).isoformat()   # wide, so the grid really scrolls


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def demo_url():
    """A local demo server (synthetic data, no network, deterministic)."""
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


def _board_url(base: str) -> str:
    return (f"{base}/?from=TLV&depart={DEPART}&ret={RETURN}"
            f"&nmin=6&nmax=8&places=8&run=1")


def _prepare(page, base: str, mobile: bool):
    page.goto(_board_url(base))
    # The board is a ranked list; the grid only exists once a destination is opened
    # (a fixed focus layer on every width now, not just on a phone).
    page.wait_for_selector(".lrow", timeout=60_000)
    page.click(".lrow")
    page.wait_for_selector("table.matrix", state="attached", timeout=60_000)
    page.wait_for_selector(".matrix-wrap", state="visible", timeout=10_000)
    # Let the first-open auto-locate + any settling finish.
    page.wait_for_timeout(400)


def _scroll_into_grid(page):
    """Scroll to a point well inside the grid on both axes, and return where it landed
    (clamped to whatever this grid can actually reach)."""
    return page.evaluate(
        """() => {
          const w = document.querySelector('.matrix-wrap');
          const maxX = w.scrollWidth - w.clientWidth;
          const maxY = w.scrollHeight - w.clientHeight;
          w.scrollLeft = Math.max(20, Math.round(maxX * 0.55));
          w.scrollTop = Math.max(20, Math.round(maxY * 0.55));
          w.dispatchEvent(new Event('scroll'));
          return [Math.round(w.scrollLeft), Math.round(w.scrollTop), Math.round(maxX), Math.round(maxY)];
        }"""
    )


def _offset(page):
    return page.evaluate(
        "() => { const w = document.querySelector('.matrix-wrap');"
        " return [Math.round(w.scrollLeft), Math.round(w.scrollTop)]; }"
    )


def _tag_wrap(page):
    """Stamp the current scroll container so we can tell a reused one from a rebuilt one."""
    page.evaluate("() => { document.querySelector('.matrix-wrap').dataset.probe = 'kept'; }")


def _wrap_is_same(page) -> bool:
    return page.evaluate(
        "() => document.querySelector('.matrix-wrap').dataset.probe === 'kept'"
    )


def _repaint(page, n: int = 5):
    """What a streaming fill does: call render() several times in quick succession."""
    page.evaluate(f"() => {{ for (let i = 0; i < {n}; i++) render(); }}")


@pytest.mark.parametrize("mobile", [True, False], ids=["mobile", "desktop"])
def test_repaint_keeps_the_grid_where_you_scrolled_it(demo_url, browser, mobile):
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 800},
        has_touch=mobile, is_mobile=mobile,
    )
    page = ctx.new_page()
    try:
        _prepare(page, demo_url, mobile)

        sx, sy, maxx, maxy = _scroll_into_grid(page)
        assert maxx > 40 and maxy > 40, f"grid barely scrolls ({maxx}x{maxy}); widen the test window"
        _tag_wrap(page)
        # Past the 180ms scroll-settle window, so the repaint takes the in-place path.
        page.wait_for_timeout(300)
        assert _offset(page) == [sx, sy], "scroll did not stick before the repaint"

        _repaint(page)
        page.wait_for_timeout(50)

        # The regression: the fill rebuilt the whole card, so the scroll container the user
        # was on is gone (and the position had to be restored a frame later, which is the
        # jump). With the fix the same container is kept and the offset never moves.
        assert _wrap_is_same(page), "the repaint rebuilt the scroll container"
        assert _offset(page) == [sx, sy], "the repaint moved the grid"
    finally:
        ctx.close()


@pytest.mark.parametrize("mobile", [True, False], ids=["mobile", "desktop"])
def test_repaint_is_deferred_while_actively_scrolling(demo_url, browser, mobile):
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 800},
        has_touch=mobile, is_mobile=mobile,
    )
    page = ctx.new_page()
    try:
        _prepare(page, demo_url, mobile)

        # Scroll and *immediately* repaint — mid-fling. The repaint is held back until the
        # scroll settles, then flushed once; the container and the offset survive both.
        sx, sy, maxx, maxy = _scroll_into_grid(page)
        assert maxx > 40 and maxy > 40, f"grid barely scrolls ({maxx}x{maxy})"
        _tag_wrap(page)
        _repaint(page)
        assert _wrap_is_same(page), "a repaint rebuilt the grid mid-scroll"
        assert _offset(page) == [sx, sy], "a repaint moved the grid mid-scroll"

        page.wait_for_timeout(300)   # scroll-settle flush
        assert _wrap_is_same(page), "the deferred repaint rebuilt the grid on flush"
        assert _offset(page) == [sx, sy], "the deferred repaint moved the grid on flush"
    finally:
        ctx.close()
