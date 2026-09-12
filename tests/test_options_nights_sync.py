"""Options' "Exact nights" fields stay reachable no matter the Trip length preset, and
stay in sync with the on-grid-steppers' inline pair shown for Flexible/Custom.

Regression: moving #nmin/#nmax out of Options and into the main bar (shown only for
Flexible/Custom) deleted Options' own nights control entirely rather than giving it its
own mirrored inputs -- for every other preset, nights became invisible and uneditable
everywhere.

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


def test_options_nights_survives_every_preset_and_stays_in_sync(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(demo_url + "/")
        page.click("#optsbtn")
        page.wait_for_selector("#nminopt")

        # Present and correct for the default (non-Flexible) preset.
        assert page.eval_on_selector("#nminopt", "el => el.value") == "6"
        assert page.eval_on_selector("#nmaxopt", "el => el.value") == "8"

        # Flexible reveals the inline pair, mirrored from Options' values.
        page.select_option("#tripselect", "3,21")
        assert page.eval_on_selector("#nightsinline", "el => !el.hidden")
        assert page.eval_on_selector("#nmin", "el => el.value") == "3"
        assert page.eval_on_selector("#nminopt", "el => el.value") == "3"

        # Editing in Options propagates to the inline pair and flips the preset to Custom.
        page.fill("#nminopt", "4")
        page.dispatch_event("#nminopt", "input")
        assert page.eval_on_selector("#nmin", "el => el.value") == "4"
        assert page.eval_on_selector("#tripselect", "el => el.value") == "custom"

        # Back to a normal preset: the inline pair hides, but Options keeps showing it.
        page.select_option("#tripselect", "6,8")
        assert page.eval_on_selector("#nightsinline", "el => el.hidden")
        assert page.eval_on_selector("#nminopt", "el => el.value") == "6"
        assert page.eval_on_selector("#nmaxopt", "el => el.value") == "8"
    finally:
        ctx.close()
