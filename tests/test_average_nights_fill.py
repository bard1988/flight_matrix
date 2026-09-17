"""Average-nights-first band fill.

A wide trip-length band (e.g. "5-45 nights") is no longer capped -- see idea.md's
"Average-nights-first, uncapped band fill" entry. The open-grid band fill (`bandCells` in
app.js) prices the band's own average length first (floor((lo+hi)/2), the trip the search
actually asked for) and streams outward from there across as many /api/autoverify rounds
as it takes, with a one-time notice when the band is wide enough that it will visibly take
a while.

Needs the dev extras (`pip install -r requirements-dev.txt` then `playwright install
chromium`); skipped otherwise.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
DEPART = (date.today() + timedelta(days=30)).isoformat()
WIDE_RETURN = (date.today() + timedelta(days=120)).isoformat()   # a 90-day window
NARROW_RETURN = (date.today() + timedelta(days=52)).isoformat()
NMIN, NMAX = 5, 45
AVG_NIGHTS = (NMIN + NMAX) // 2   # 25, per idea.md's 12-14 -> 13 / 12-13 -> 12 examples


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def demo_url():
    port = _free_port()
    # A wide-band search deliberately verifies thousands of cells -- into the repo's real
    # data/cache.sqlite by default, since every Playwright test spawns its own subprocess
    # with no isolation of its own. Left alone, that many cells then read back as "already
    # verified" to whichever other test file's demo server happens to run next in the same
    # TLV-origin, overlapping date range. FM_CACHE_DB (config.py) keeps this module's own
    # writes out of everyone else's way.
    cache_dir = tempfile.mkdtemp(prefix="fm_test_cache_")
    env = {**os.environ, "FM_CACHE_DB": str(Path(cache_dir) / "test.sqlite")}
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py"), "--demo", "--no-open",
         "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
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
        shutil.rmtree(cache_dir, ignore_errors=True)


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


def _open_card(page, base, nmin, nmax, ret):
    page.goto(f"{base}/?from=TLV&depart={DEPART}&ret={ret}&nmin={nmin}&nmax={nmax}&places=3")
    page.click("#go")
    page.wait_for_selector(".lrow", timeout=60_000)
    page.wait_for_function("() => document.querySelectorAll('#dlist .lrow').length >= 1", timeout=60_000)
    page.click(".lrow")
    page.wait_for_selector("#ddetail table.matrix", state="attached", timeout=60_000)


def _nights(cell):
    d = date.fromisoformat(cell["depart_date"])
    r = date.fromisoformat(cell["return_date"])
    return (r - d).days


def test_the_first_round_prices_cells_nearest_the_bands_average_length(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        calls = []
        page.on("request", lambda r: calls.append(r.post_data) if "/api/autoverify" in r.url else None)
        _open_card(page, demo_url, NMIN, NMAX, WIDE_RETURN)
        page.wait_for_function("() => document.querySelectorAll('#ddetail td.loading').length > 0",
                                timeout=10_000)

        assert calls, "opening a wide-band card must fire at least one autoverify round"
        first = json.loads(calls[0])["cells"]
        assert first, "the first round must not be empty"
        nights = [_nights(c) for c in first[:5]]
        # A 90-day window offers dozens of depart dates landing on exactly the average
        # length, so the first entries should cluster tightly on it -- the old code had no
        # such preference at all and would lead with whatever was cheapest anywhere in the
        # 5-45 band, average nowhere in particular.
        assert all(abs(n - AVG_NIGHTS) <= 2 for n in nights), (
            f"first-round cells must cluster around the average ({AVG_NIGHTS}) nights, "
            f"got nights={nights}"
        )
    finally:
        ctx.close()


def test_a_wide_band_is_not_capped_it_streams_over_multiple_rounds(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        calls = []
        page.on("request", lambda r: calls.append(r.post_data) if "/api/autoverify" in r.url else None)
        _open_card(page, demo_url, NMIN, NMAX, WIDE_RETURN)
        page.wait_for_timeout(12_000)   # let a couple of rounds land (demo verify sleeps ~50-180ms/cell)

        assert len(calls) >= 2, f"a band this wide must take more than one round, got {len(calls)} call(s)"
        total_sent = sum(len(json.loads(c)["cells"]) for c in calls)
        assert total_sent > 280, (
            "the old fixed 280-cell cap must be gone -- only "
            f"{total_sent} cells were sent across {len(calls)} round(s)"
        )
    finally:
        ctx.close()


def test_a_wide_band_shows_a_notice_that_it_will_take_a_while(demo_url, browser):
    """The notice is set synchronously before the first /api/autoverify round even goes
    out, but demo mode answers so fast (workers finish a cell in ~50-180ms) that it can be
    overwritten by the first per-cell progress line before a separate, later
    `page.wait_for_function` call even gets scheduled. Delay the fill's own event stream
    (not the page, not the notice) just enough to observe it without racing real network
    timing.
    """
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        def delay_stream(route):
            time.sleep(0.4)
            route.continue_()

        page.route("**/api/fill/*/stream", delay_stream)
        _open_card(page, demo_url, NMIN, NMAX, WIDE_RETURN)
        page.wait_for_function(
            "() => (document.getElementById('growing').textContent || '').includes('Wide trip-length range')",
            timeout=5_000)
    finally:
        ctx.close()


def test_a_narrow_band_shows_no_wide_band_notice(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        _open_card(page, demo_url, 6, 8, NARROW_RETURN)
        page.wait_for_function(
            "() => document.querySelectorAll('#ddetail td.loading').length === 0", timeout=30_000)
        text = page.evaluate("() => document.getElementById('growing').textContent || ''")
        assert "Wide trip-length range" not in text
    finally:
        ctx.close()
