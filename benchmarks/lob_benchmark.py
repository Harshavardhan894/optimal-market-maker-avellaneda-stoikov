from __future__ import annotations

import random
import time
from statistics import median

from core.order_book import LimitOrderBook


def _timed(fn, repeats: int = 5) -> float:
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        samples.append((t1 - t0) * 1e6)
    return median(samples)


def bench_add(n: int) -> float:
    def run() -> None:
        lob = LimitOrderBook()
        for i in range(n):
            price = 100.0 + random.randint(-50, 50) * 0.01
            qty = random.randint(1, 5)
            lob.add_order(price=price, quantity=qty, is_buy=(i % 2 == 0), timestamp=i, owner="bench")

    return _timed(run)


def bench_cancel(n: int) -> float:
    def run() -> None:
        lob = LimitOrderBook()
        ids = []
        for i in range(n):
            oid = lob.add_order(100 + (i % 10) * 0.01, 1, is_buy=(i % 2 == 0), timestamp=i, owner="bench")
            ids.append(oid)
        for oid in ids[::2]:
            lob.cancel_order(oid)

    return _timed(run)


def bench_match(n: int) -> float:
    def run() -> None:
        lob = LimitOrderBook()
        ts = 0
        for _ in range(n):
            ts += 1
            lob.add_order(100.00, 1, is_buy=True, timestamp=ts, owner="bench")
            ts += 1
            lob.add_order(100.00, 1, is_buy=False, timestamp=ts, owner="bench")
        lob.match_orders(timestamp=ts + 1)

    return _timed(run)


def main() -> None:
    random.seed(42)
    sizes = [1_000, 5_000, 10_000]

    print("LOB benchmark (median µs over 5 runs)")
    print("size,add_us,cancel_us,match_us")
    for n in sizes:
        add_us = bench_add(n)
        cancel_us = bench_cancel(n)
        match_us = bench_match(n)
        print(f"{n},{add_us:.2f},{cancel_us:.2f},{match_us:.2f}")


if __name__ == "__main__":
    main()
