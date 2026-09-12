"""Start the Google Flights relay.

    py -3 relay/run_relay.py --host 0.0.0.0 --port 8080

One process, no reload, no workers -- there is no shared state to worry about (unlike the
main app's search registry), but there is also no reason to run more than one: this is
already just a thin wrapper around one Google Flights lookup at a time per request, and
the caller (the main app) is what controls concurrency.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "relay"))


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    uvicorn.run("app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
