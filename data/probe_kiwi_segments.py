"""Field names for Kiwi sector/segment times, so we can fetch times on click."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
HEAD = {"User-Agent": "Mozilla/5.0", "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.kiwi.com", "Referer": "https://www.kiwi.com/"}
client = httpx.Client(timeout=45.0, verify=config.CA_BUNDLE, headers=HEAD, follow_redirects=True)


def unwrap(t):
    while t and not t.get("name"):
        t = t.get("ofType")
    return (t or {}).get("name", "?")


for tn in ("SectorSegment", "Stop", "Carrier", "Segment"):
    r = client.post(ENDPOINT, content=json.dumps({"query":
        '{ __type(name: "%s") { kind fields { name type { kind name ofType '
        '{ kind name ofType { kind name } } } } } }' % tn}))
    t = ((r.json().get("data") or {}).get("__type") or {})
    print(f"{tn} ({t.get('kind')}):")
    for f in t.get("fields") or []:
        print(f"    {f['name']}: {unwrap(f['type'])}")
    print()

client.close()
