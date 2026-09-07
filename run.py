"""Start FlightMatrix on a free local port and open it in the browser.

    py -3 run.py                      # real data, needs TRAVELPAYOUTS_TOKEN in .env
    py -3 run.py --demo               # synthetic data, no token needed
    py -3 run.py --no-open            # do not launch a browser
    py -3 run.py --host 0.0.0.0 --port 8712 --no-open   # serve to the network

Run ONE process only. Search progress is streamed from an in-memory registry
(`app._streams`), so a second worker would answer some stream requests with "unknown
search id" - do not add `--workers`.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def free_port(preferred: int = 8712) -> int:
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def reachable_url(host: str, port: int) -> str:
    """The URL to hand to someone else, which is never the wildcard address."""
    if host not in ("0.0.0.0", "::", ""):
        return f"http://{host}:{port}/"
    return f"http://{socket.gethostname().lower()}:{port}/"


def main() -> int:
    parser = argparse.ArgumentParser(description="FlightMatrix")
    parser.add_argument("--demo", action="store_true", help="synthetic data, no API token required")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface to bind. 127.0.0.1 (default) is reachable only from this machine; "
             "0.0.0.0 serves everyone who can route to it.",
    )
    args = parser.parse_args()

    if args.demo:
        os.environ["FM_DEMO"] = "1"

    import uvicorn

    import config

    if not args.demo and not config.TRAVELPAYOUTS_TOKEN:
        print(
            "No TRAVELPAYOUTS_TOKEN found.\n"
            "  Get a free token at https://app.travelpayouts.com/profile/api-token\n"
            f"  then put TRAVELPAYOUTS_TOKEN=... in {ROOT / '.env'}\n"
            "  or run with --demo to explore the board with synthetic data.\n",
            file=sys.stderr,
        )

    port = args.port or free_port()
    url = reachable_url(args.host, port)
    print(f"FlightMatrix{' [demo]' if args.demo else ''} -> {url}")

    if args.host not in ("127.0.0.1", "localhost"):
        # Serving beyond this machine has consequences worth stating at the point of use:
        # the app has no login, and every board it builds calls Kiwi from this host's
        # egress IP, which is shared with everyone else behind the same gateway.
        print(
            f"  bound to {args.host} - anyone who can reach this host can use it, "
            "there is no authentication\n"
            "  all provider traffic leaves from this host's IP; a rate-limit block "
            "affects every user at once",
            file=sys.stderr,
        )

    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()

    uvicorn.run("app:app", host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
