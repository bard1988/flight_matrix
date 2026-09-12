"""The FlightMatrix logo links back to the homepage.

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


def test_the_logo_links_home_and_clears_the_board(demo_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 700})
    page = ctx.new_page()
    try:
        page.goto(f"{demo_url}/?from=TLV&depart=2027-05-01&ret=2027-05-25&places=5")
        page.click("#go")
        page.wait_for_selector(".lrow", timeout=60_000)

        assert page.eval_on_selector(".brand", "el => el.tagName") == "A"
        assert page.eval_on_selector(".brand", "el => el.getAttribute('href')") == "/"

        page.click(".brand")
        page.wait_for_load_state("load")

        assert page.url.rstrip("/") == demo_url.rstrip("/")
        assert page.evaluate("() => document.querySelectorAll('.lrow').length") == 0
    finally:
        ctx.close()
