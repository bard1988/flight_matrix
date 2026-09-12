"""A cell's live cross-check retries itself once before ever falling back.

`/api/verify` answers 200 either way, so a soft failure (no live price, or a fallback to
the last stored one) never trips postJSON's own transport-level retries -- those only fire
on an actual network/timeout error. Before this, a soft failure showed the fallback with
"tap the cell again to retry"; now the frontend retries once on its own, with a visible
"re-checking" note, and only falls back for good if that retry also comes back soft.

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
    page.wait_for_selector("#ddetail table.matrix td.priced", timeout=60_000)


def test_a_soft_failure_retries_itself_once_before_falling_back(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url)

        # Patched in page JS, not via page.route: a Python-side route handler that delays
        # (needed so the "re-checking" interim state is observable at all, rather than a
        # zero-width flicker between two instantly-fulfilled fakes) blocks the very driver
        # thread this test's own wait_for_function polls over -- see the nights-stepper
        # tests for the same lesson.
        page.evaluate("""() => {
            const real = window.fetch.bind(window);
            let n = 0;
            window.fetch = (url, opts) => {
                if (typeof url !== 'string' || !url.includes('/api/verify')) return real(url, opts);
                n += 1;
                const body = n === 1
                    ? { total: 1234, cached: true, cache_age_minutes: 5, stale: false,
                        link: 'https://example.com/g1' }
                    : { total: 999, cached: false, departs: '10:00', arrives: '14:00',
                        airline: 'Demo Air', duration: '4h', stops_out: 0,
                        link: 'https://example.com/g2' };
                const respond = () => new Response(JSON.stringify(body),
                    { status: 200, headers: { 'Content-Type': 'application/json' } });
                return n === 1 ? Promise.resolve(respond())
                    : new Promise((resolve) => setTimeout(() => resolve(respond()), 600));
            };
            window.__verifyCalls = () => n;
        }""")
        page.click("#ddetail table.matrix td.priced")

        # The first (faked) answer is the cached fallback -- the panel must show that a
        # re-check is under way on its own, with no click required from the user.
        page.wait_for_function(
            "() => (document.getElementById('panelbody').textContent || '')"
            ".includes('re-checking')", timeout=5_000)

        # The retry (the second, delayed, faked answer) is a fresh live total -- it must
        # land without any further interaction, and the old "tap the cell again"
        # instruction is gone.
        page.wait_for_function(
            "() => (document.getElementById('panelbody').textContent || '').includes('999')",
            timeout=5_000)
        body_text = page.evaluate("() => document.getElementById('panelbody').textContent")
        assert "tap the cell again" not in body_text.lower()
        assert "1,234" not in body_text and "1234" not in body_text   # the stale figure is gone
        assert page.evaluate("() => window.__verifyCalls()") == 2     # exactly one automatic retry
    finally:
        ctx.close()


def test_two_soft_failures_settle_on_the_fallback_without_asking_to_retry(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url)

        page.evaluate("""() => {
            const real = window.fetch.bind(window);
            let n = 0;
            window.fetch = (url, opts) => {
                if (typeof url !== 'string' || !url.includes('/api/verify')) return real(url, opts);
                n += 1;
                const body = { total: 1234, cached: true, cache_age_minutes: 5, stale: false,
                    link: 'https://example.com/g1' };
                return Promise.resolve(new Response(JSON.stringify(body),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }));
            };
            window.__verifyCalls = () => n;
        }""")
        page.click("#ddetail table.matrix td.priced")

        page.wait_for_function(
            "() => (document.getElementById('panelbody').textContent || '')"
            ".includes(\"didn't answer, even on a retry\")", timeout=5_000)
        body_text = page.evaluate("() => document.getElementById('panelbody').textContent")
        assert "tap the cell again" not in body_text.lower()
        assert page.evaluate("() => window.__verifyCalls()") == 2   # the one automatic retry, then it stops
    finally:
        ctx.close()
