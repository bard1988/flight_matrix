"""The mobile search bar: From/To, the two date fields, and Trip length/Travellers each
share a row instead of stacking one field per line, and "Flexible" (or the once-you've-
edited-it "Custom" state) reveals the exact nights fields inline.

The pairing CSS existed before this fix but was dead: an older, wider breakpoint's
column-direction container and its `!important` full-width field rule both outrank a
same-specificity, non-important rule below them regardless of source order, so nothing
ever paired up on an actual phone.

Needs the dev extras (`pip install -r requirements-dev.txt` then `playwright install
chromium`); skipped otherwise.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent


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


def _same_row(box_a, box_b) -> bool:
    return abs(box_a["y"] - box_b["y"]) < 2


def test_from_to_and_dates_and_trip_pax_each_pair_on_mobile(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    try:
        page.goto(demo_url + "/")
        page.wait_for_selector("#tripselect")

        box = lambda sel: page.query_selector(sel).bounding_box()          # noqa: E731
        from_, dest = box(".field-from"), box(".field-dest")
        depart, ret = box(".field-date.field-from-date"), box(".field-date.field-until-date")
        trip, pax = box(".field-trip"), box(".field-pax")

        assert _same_row(from_, dest), "From/To should share a row on mobile"
        assert _same_row(depart, ret), "the two date fields should share a row on mobile"
        assert _same_row(trip, pax), "Trip length/Travellers should share a row on mobile"
        # And genuinely side by side, not just vertically aligned on separate lines that
        # happen to start at the same y (each pair's second field must sit to the right).
        assert dest["x"] > from_["x"]
        assert ret["x"] > depart["x"]
        assert pax["x"] > trip["x"]
    finally:
        ctx.close()


def test_flexible_reveals_nights_inline_other_presets_do_not(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    try:
        page.goto(demo_url + "/")
        page.wait_for_selector("#tripselect")

        assert page.eval_on_selector("#nightsinline", "el => el.hidden")   # default preset: hidden

        page.select_option("#tripselect", "3,21")                          # Flexible
        assert not page.eval_on_selector("#nightsinline", "el => el.hidden")
        assert page.eval_on_selector("#nmin", "el => el.value") == "3"
        assert page.eval_on_selector("#nmax", "el => el.value") == "21"

        page.select_option("#tripselect", "6,8")                           # back to a preset
        assert page.eval_on_selector("#nightsinline", "el => el.hidden")
    finally:
        ctx.close()
