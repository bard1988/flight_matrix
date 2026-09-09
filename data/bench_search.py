"""Benchmark the board search: where does a search's wall clock actually go?

    py -3 data/bench_search.py                     # baseline, 5 destinations
    py -3 data/bench_search.py --dests 20          # full board
    py -3 data/bench_search.py --workers 8 --interval 0   # try a pacing change
    py -3 data/bench_search.py --no-cache          # force real fetches
    py -3 data/bench_search.py --model-only        # no network: call-count model

Reports Kiwi call counts per operation, time lost inside the pacing lock, time to the
first card, and an extrapolation to a full board. `--model-only` needs no network and
shows how the call count scales with the search period and nights range.

Note on the totals: per-call times are summed across worker threads, so they exceed the
wall clock. The number to compare between runs is the wall clock and the achieved
calls/second, printed against the pacer's ceiling (1 / FM_KIWI_MIN_INTERVAL).

Raising `--workers` and lowering `--interval` speeds a short run up a lot and then gets
the host IP blocked: measured, 8 workers with no pacing filled 9 destinations at ~6.6
calls/s and then took a 403 that lasted over fifteen minutes, during which the board fell
back to Travelpayouts estimates. Treat those flags as an experiment, not a setting.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import config                                          # noqa: E402
from models import SearchRequest                       # noqa: E402


def make_request(args) -> SearchRequest:
    start = date.today() + timedelta(days=args.days_out)
    return SearchRequest(
        origin=args.origin,
        depart_date=start.isoformat(),
        return_date=(start + timedelta(days=args.period - 1)).isoformat(),
        adults=args.adults, children=args.children, currency=args.currency,
        max_destinations=args.dests,
        nights_min=args.nights_min, nights_max=args.nights_max,
    )


def grid_shape(request: SearchRequest) -> tuple[int, int]:
    """(calls, cells) for one destination, mirroring KiwiProvider.fill_matrix."""
    departs, returns = request.range_axes()
    nights = request.nights_span()
    calls = cells = 0
    for ret in returns:
        if ret < departs[0]:
            continue
        window = [d for d in departs if nights[0] <= (ret - d).days <= nights[-1]]
        if window:
            calls += 1
            cells += len(window)
    return calls, cells


def model(args) -> None:
    """Call-count arithmetic only. One calendar call per RETURN date, per destination."""
    print(f"{'period':>7} {'nights':>8} | {'calls/dest':>10} {'cells/dest':>10} "
          f"{'calls':>7} {'@1.25/s':>9} {'@2.5/s':>8}")
    print("-" * 68)
    for period, lo, hi in [(14, 5, 9), (21, 5, 9), (30, 5, 9), (45, 5, 9), (60, 5, 9),
                           (30, 7, 7), (30, 6, 8), (30, 3, 14)]:
        request = make_request(argparse.Namespace(
            **{**vars(args), "period": period, "nights_min": lo, "nights_max": hi}))
        per_dest, cells = grid_shape(request)
        calls = per_dest * args.dests + 1
        print(f"{period:>5}d {lo:>3}-{hi:<3} | {per_dest:>10} {cells:>10} {calls:>7} "
              f"{calls / 1.25:>8.0f}s {calls / 2.5:>7.0f}s")
    print("\nThe call count tracks the PERIOD length (one call per return date), not the")
    print("nights range: 30d/7-7 costs 23 calls for 23 cells, 30d/3-14 costs 27 for 258.")


def live(args) -> None:
    import board
    from providers.kiwi import KiwiProvider

    config.KIWI_WORKERS = args.workers
    config.KIWI_MIN_INTERVAL = args.interval
    if args.no_cache:
        config.KIWI_CACHE_HOURS = 0.0
    if args.no_headline:
        config.CHECK_HEADLINE = False

    request = make_request(args)
    departs, returns = request.range_axes()
    per_dest, cells = grid_shape(request)
    print(f"origin={request.origin} period={args.period}d "
          f"nights={args.nights_min}-{args.nights_max} dests={args.dests} "
          f"| axes {len(departs)}x{len(returns)}, {per_dest} calls -> {cells} cells per grid")
    print(f"workers={config.KIWI_WORKERS} min_interval={config.KIWI_MIN_INTERVAL}s "
          f"cache_hours={config.KIWI_CACHE_HOURS} check_headline={config.CHECK_HEADLINE}")

    stats: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0.0, "s": 0.0})
    paced = {"s": 0.0}
    lock = threading.Lock()

    provider = KiwiProvider()
    inner_gql, inner_pace = provider._gql, provider._pace

    def gql(query, variables, operation):
        started = time.perf_counter()
        try:
            return inner_gql(query, variables, operation)
        finally:
            with lock:
                stats[operation]["n"] += 1
                stats[operation]["s"] += time.perf_counter() - started

    def pace():
        started = time.perf_counter()
        inner_pace()
        with lock:
            paced["s"] += time.perf_counter() - started

    provider._gql, provider._pace = gql, pace

    started = time.perf_counter()
    # Two different latencies matter now and they are not the same number: `first_list` is
    # when the ranked destination list is on screen (the first preview), `first_grid` is
    # when the detail pane has a grid to show. Previews are not counted as filled cards.
    first_list: float | None = None
    first_grid: float | None = None
    previews = 0
    cards = 0
    for event in board.build(request, provider=provider):
        now = time.perf_counter() - started
        kind = event.get("type")
        if kind == "destination" and event.get("preview"):
            previews += 1
            first_list = now if first_list is None else first_list
        elif kind == "destination":
            cards += 1
            first_grid = now if first_grid is None else first_grid
            print(f"  t={now:7.2f}s  card#{cards:<3d} {event['destination']:4s} "
                  f"cells={len(event.get('cells') or []):3d} "
                  f"checks={event.get('headline_checks')} "
                  f"cache={event.get('from_cache', False)}")
        elif kind in ("provider_status", "provider_fallback", "destination_error", "error"):
            print(f"  t={now:7.2f}s  [{kind}] {str(event.get('message', ''))[:110]}")
        elif kind == "done":
            print(f"  t={now:7.2f}s  [done] filled={event.get('destinations')} "
                  f"empty={event.get('empty')} failovers={event.get('failovers')} "
                  f"strategy={event.get('strategy')}")
    total = time.perf_counter() - started

    calls = sum(int(v["n"]) for v in stats.values())
    print(f"\n  wall clock            {total:8.2f} s for {cards} cards")
    for operation, value in sorted(stats.items()):
        print(f"  {operation:11s} calls={int(value['n']):4d}  "
              f"avg={value['s'] / max(value['n'], 1) * 1000:6.0f} ms")
    print(f"  total Kiwi calls      {calls:8d}")
    ceiling = (f"   (pacer ceiling {1 / config.KIWI_MIN_INTERVAL:.2f}/s)"
               if config.KIWI_MIN_INTERVAL else "   (pacer off)")
    print(f"  achieved rate         {calls / total:8.2f} calls/s{ceiling}")
    print(f"  summed time in _pace  {paced['s']:8.2f} s across {config.KIWI_WORKERS} workers")
    if previews:
        print(f"  time to ranked list   {first_list:8.2f} s  ({previews} preview cards)")
    if cards:
        print(f"  time to first grid    {first_grid:8.2f} s")
        print(f"  per destination       {total / cards:8.2f} s, {calls / cards:.1f} calls")
        print(f"  extrapolated to 20    {total / cards * 20:8.0f} s")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--origin", default="TLV")
    parser.add_argument("--dests", type=int, default=5)
    parser.add_argument("--period", type=int, default=30,
                        help="length of the travel window, days")
    parser.add_argument("--days-out", type=int, default=30,
                        help="how far ahead the window starts")
    parser.add_argument("--nights-min", type=int, default=5)
    parser.add_argument("--nights-max", type=int, default=9)
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--children", type=int, default=0)
    parser.add_argument("--currency", default="ils")
    parser.add_argument("--workers", type=int, default=config.KIWI_WORKERS)
    parser.add_argument("--interval", type=float, default=config.KIWI_MIN_INTERVAL)
    parser.add_argument("--no-cache", action="store_true", help="ignore cached grids")
    parser.add_argument("--no-headline", action="store_true",
                        help="skip the headline re-check")
    parser.add_argument("--model-only", action="store_true",
                        help="call-count model, no network")
    args = parser.parse_args()

    model(args) if args.model_only else live(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
