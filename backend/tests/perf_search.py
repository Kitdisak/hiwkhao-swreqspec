"""วัดเวลาตอบกลับ API ด้วยข้อมูล seed 4 ชื่อเรื่อง (NFR-PERF-01)."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import statistics
import threading
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from app.book_search.models import CATALOG_RECORDS


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def measure(base_url: str, users: int) -> tuple[list[float], float]:
    barrier = threading.Barrier(users)
    url = f"{base_url.rstrip('/')}/api/books/search?{urlencode({'query': 'ซอฟต์'})}"

    def search_once() -> float:
        barrier.wait()
        started = time.perf_counter()
        with urlopen(url, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"Unexpected HTTP status: {response.status}")
            payload = json.load(response)
        if len(payload["results"]) != 1:
            raise RuntimeError("The benchmark query must return exactly one result")
        return time.perf_counter() - started

    round_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=users) as executor:
        latencies = list(executor.map(lambda _: search_once(), range(users)))
    return latencies, time.perf_counter() - round_started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--users",
        type=int,
        choices=(50, 200),
        action="append",
        help="Run only selected concurrency levels; may be supplied more than once.",
    )
    args = parser.parse_args()

    if len(CATALOG_RECORDS) != 4:
        raise RuntimeError(
            "The team-selected benchmark dataset must contain 4 title records"
        )

    print("ชุดข้อมูล: seed 4 ชื่อเรื่อง; คำค้น: 'ซอฟต์'")
    print("หมายเหตุ: วัดเวลาตอบกลับ API ไม่รวมเวลา render ใน browser")
    for users in args.users or (50, 200):
        latencies, round_seconds = measure(args.base_url, users)
        print(
            f"{users} users: "
            f"median={statistics.median(latencies):.3f}s, "
            f"p95={percentile(latencies, 0.95):.3f}s, "
            f"max={max(latencies):.3f}s, "
            f"round={round_seconds:.3f}s"
        )
    print("เป้าหมาย NFR-PERF-01: 3 วินาที (เป้าหมาย ไม่ใช่เกณฑ์ผ่าน/ตก)")


if __name__ == "__main__":
    main()
