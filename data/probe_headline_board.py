"""Full board run: how many cards end up confirmed, and what the check costs."""
import json
import sys
import time
import urllib.request

count = int(sys.argv[1]) if len(sys.argv) > 1 else 8
depart = sys.argv[2] if len(sys.argv) > 2 else "2027-07-31"
ret = sys.argv[3] if len(sys.argv) > 3 else "2027-08-20"
adults = int(sys.argv[4]) if len(sys.argv) > 4 else 2
children = int(sys.argv[5]) if len(sys.argv) > 5 else 3
body = json.dumps({
    "origin": "TLV", "depart_date": depart, "return_date": ret,
    "adults": adults, "children": children, "currency": "ils", "max_destinations": count,
}).encode()
req = urllib.request.Request("http://127.0.0.1:8712/api/search", body,
                             {"Content-Type": "application/json"})
sid = json.load(urllib.request.urlopen(req, timeout=120))["search_id"]

started = time.time()
confirmed = unconfirmed = checks = dropped = 0
print(f"{'dest':<6}{'headline':>10}{'drift%':>9}{'checks':>8}{'drop':>6}  state")
with urllib.request.urlopen(f"http://127.0.0.1:8712/api/search/{sid}/stream", timeout=3600) as r:
    for raw in r:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:])
        kind = ev.get("type")
        if kind == "destination":
            b = ev.get("best") or {}
            ok = ev.get("headline_checked")
            confirmed += 1 if ok else 0
            unconfirmed += 0 if ok else 1
            checks += ev.get("headline_checks") or 0
            dropped += ev.get("headline_dropped") or 0
            drift = ev.get("headline_drift")
            print(f"{ev['destination']:<6}{b.get('estimate', 0):>10,.0f}"
                  f"{(f'{drift:+.1f}' if drift is not None else '-'):>9}"
                  f"{ev.get('headline_checks', 0) or 0:>8}"
                  f"{ev.get('headline_dropped', 0) or 0:>6}"
                  f"  {'confirmed' if ok else 'UNCONFIRMED'}", flush=True)
        elif kind == "done":
            break
print(f"\n{confirmed} confirmed, {unconfirmed} unconfirmed, "
      f"{checks} check calls, {dropped} unbookable cells dropped, "
      f"{time.time() - started:.0f}s")
