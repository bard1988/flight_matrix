"""The on-grid Nights min/max steppers.

Nights is a view filter (`state.constraints`), so narrowing recolours / re-ranks the
board instantly with no refetch; widening past the priced band auto-fetches the new
lengths for the grid on screen. The steppers live in the Single card head and the Multi
chips row and stay in sync with the Options fields and the Trip length preset.

Needs the dev extras (`pip install -r requirements-dev.txt` then `playwright install
chromium`); skipped otherwise.
"""
from __future__ import annotations

import json
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


def test_widening_nights_shows_a_loading_cue_while_the_fetch_is_out(demo_url, browser):
    """The demo board fills in milliseconds and never errors, which is exactly why this
    regressed unnoticed: nightsExtend() never marked the newly in-range cells pending, so
    a genuinely slow /api/extend (the real, rate-limited board in production) just showed
    flat empty tiles -- indistinguishable from a request that silently did nothing.
    Delaying the POST here stands in for that slowness against a real backend.
    """
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url)
        # Let the open-card cross-check fill settle first, so the loading cells we look for
        # below are unambiguously caused by the nights widen, not the unrelated auto-fill.
        page.wait_for_function(
            "() => document.querySelectorAll('#ddetail td.loading').length === 0", timeout=30_000)

        # Delay purely in page JS (a Python-side blocking route handler would stall the
        # same driver thread this test's own wait_for_function polls over, which just
        # measures how long the delay handler blocked rather than what the page does).
        page.evaluate("""() => {
            const real = window.fetch.bind(window);
            window.fetch = (url, opts) => (
                typeof url === 'string' && url.includes('/api/extend') && !url.includes('/stream')
                    ? new Promise((resolve) => setTimeout(() => resolve(real(url, opts)), 3000))
                    : real(url, opts)
            );
        }""")
        t0 = time.monotonic()

        # One jump, not three separate clicks: the steppers debounce (350ms), and three
        # clicks spaced wider than that would fire more than one nightsExtend() call --
        # exactly what the guard is for, but it would also fire more than one delayed
        # /api/extend and muddy the single fetch this test means to observe.
        page.evaluate("() => stepNights('max', 3)")    # 8 -> 11, past the priced band

        # Cells are marked pending synchronously, before the (now-delayed) fetch is even
        # issued -- so the cue must show well before the artificial delay elapses.
        page.wait_for_function(
            "() => document.querySelectorAll('#ddetail td.loading').length > 0", timeout=2_500)
        assert time.monotonic() - t0 < 3          # detected mid-delay, not after it resolved
        assert page.evaluate("() => document.querySelectorAll('#ddetail td.loading').length > 0")

        # Once the delayed response lands, the cue clears and the band is actually priced.
        page.wait_for_function(
            "() => document.querySelectorAll('#ddetail td.loading').length === 0", timeout=5_000)
        n11 = ("() => [...document.querySelectorAll('#ddetail td.priced')].filter(td => td.dataset.dep && "
               "Math.round((new Date(td.dataset.ret) - new Date(td.dataset.dep)) / 864e5) === 11).length")
        assert page.evaluate(n11) > 0
    finally:
        ctx.close()


def test_a_provider_miss_clears_the_loading_cue_instead_of_sticking(demo_url, browser):
    """destination_error -- what board.fill_one raising (rate limit, timeout) turns into on
    the wire -- had no handler in nightsExtend's onmessage at all, so a genuine provider
    failure left that destination's cells pulsing forever with no way out. Fully fake the
    extend endpoints (the real demo backend does not fail) to inject one and confirm the
    cells settle back to plain-empty instead.
    """
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url)
        page.wait_for_function(
            "() => document.querySelectorAll('#ddetail td.loading').length === 0", timeout=30_000)
        dest = page.evaluate("() => state.selected")

        def fake_extend_start(route):
            route.fulfill(status=200, content_type="application/json",
                           body=json.dumps({"extend_id": "fake-err-1"}))

        def fake_extend_stream(route):
            body = (
                "data: " + json.dumps({
                    "type": "destination_error", "destination": dest,
                    "message": "simulated rate limit",
                }) + "\n\n"
                "event: end\ndata: {}\n\n"
            )
            route.fulfill(status=200, content_type="text/event-stream", body=body)

        page.route("**/api/extend", fake_extend_start)
        page.route("**/api/extend/fake-err-1/stream", fake_extend_stream)

        page.evaluate("() => stepNights('max', 3)")    # 8 -> 11, one jump (see the other test)

        # Marked pending before the (faked) fetch fires...
        page.wait_for_function("() => state.pendingCells.size > 0", timeout=2_000)
        # ...and the faked destination_error must clear it back out, not leave it stuck.
        page.wait_for_function("() => state.pendingCells.size === 0", timeout=2_000)
        assert page.evaluate(
            "() => document.querySelectorAll('#ddetail td.loading').length === 0")
        assert page.evaluate("() => !nightsExtending")
        # The view still reflects the widen the user asked for, even with no new data.
        assert page.evaluate("() => document.getElementById('nmax').value === '11'")
        assert page.evaluate("() => state.meta.nights_span.includes(11)")
    finally:
        ctx.close()


def test_widening_re_arms_the_cross_check_for_the_new_band(demo_url, browser):
    """Reported as "it blinks, stops fast, and doesn't look like it filled the new
    nights". The extend fetch is the fast estimate source (routed through _base_provider
    for speed -- see the board.fill_one commit), and that source often does not actually
    cover every night in a widened band; it has whatever fares it happens to have, not
    necessarily this exact one. Before this fix, `openFilled` already marked the
    destination "done" from when the card first opened, so the extend's (possibly
    incomplete) result was final -- nothing ever went back to check it again. Widening
    must re-arm the destination's cross-check (autoverify), the same one a freshly-opened
    card gets, so whatever the fast source left empty gets a second, real pass.
    """
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url)
        page.wait_for_function(
            "() => document.querySelectorAll('#ddetail td.loading').length === 0", timeout=30_000)

        autoverify_calls = {"n": 0}
        page.on("request", lambda r: autoverify_calls.__setitem__("n", autoverify_calls["n"] + 1)
                 if "/api/autoverify" in r.url else None)

        page.evaluate("() => stepNights('max', 3)")    # 8 -> 11, past the priced band
        page.wait_for_function("() => state.constraints.max === 11", timeout=3_000)
        page.wait_for_function("() => !nightsExtending", timeout=30_000)   # the extend settles
        page.wait_for_timeout(500)   # the re-armed cross-check runs off the render right after

        assert autoverify_calls["n"] > 0, \
            "widening a destination past its priced band must re-run its cross-check"
    finally:
        ctx.close()
