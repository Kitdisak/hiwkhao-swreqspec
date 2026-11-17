"""วัด API ตรวจสอบห้องว่างด้วยข้อมูล NFR-PERF-01 (NFR-PERF-01, ASM-06)."""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as wall_time, timedelta
import json
import math
import socket
import statistics
import threading
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import uvicorn

from app.main import app
from app.rooms import store
from app.rooms.config import DEFAULT_AVAILABILITY_CONFIG
from app.rooms.models import Room, RoomBooking

_BANGKOK = ZoneInfo("Asia/Bangkok")
_TARGET_SECONDS = 3.0
_ROOM_TYPE = "ห้องอ่านหนังสือ"
_FILTERED_USER_COUNT = 12


def _build_dataset() -> tuple[list[Room], list[RoomBooking], date]:
    today = datetime.now(_BANGKOK).date()
    rooms = [
        Room(
            room_id=f"PERF-ROOM-{index + 1:02d}",
            room_type=_ROOM_TYPE if index % 2 == 0 else "ห้องประชุม",
            capacity=2 + index % 19,
        )
        for index in range(50)
    ]

    bookings: list[RoomBooking] = []
    for day_offset in range(1, 61):
        booking_date = today + timedelta(days=day_offset)
        for room in rooms:
            for slot_index in range(0, 24, 2):
                start_minutes = 8 * 60 + slot_index * 30
                end_minutes = start_minutes + 30
                bookings.append(
                    RoomBooking(
                        booking_id=(
                            f"PERF-{day_offset:02d}-{room.room_id}-{slot_index:02d}"
                        ),
                        room_id=room.room_id,
                        booking_date=booking_date,
                        start_time=wall_time(
                            start_minutes // 60, start_minutes % 60
                        ),
                        end_time=wall_time(end_minutes // 60, end_minutes % 60),
                    )
                )

    if len(bookings) != 36_000:
        raise RuntimeError(f"Expected 36,000 bookings, got {len(bookings)}")

    return rooms, bookings, today + timedelta(days=30)


def _percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def _validate_response(payload: object, user_count: int | None) -> None:
    expected_room_ids = [
        room.room_id
        for room in store.ROOMS
        if room.room_type == _ROOM_TYPE
        and (user_count is None or room.capacity >= user_count)
    ]
    if not isinstance(payload, dict) or not isinstance(payload.get("rooms"), list):
        raise RuntimeError("Availability response has no rooms list")
    if payload.get("message") is not None:
        raise RuntimeError("Benchmark query unexpectedly returned no available rooms")

    actual_room_ids = [room.get("room_id") for room in payload["rooms"]]
    if actual_room_ids != expected_room_ids:
        raise RuntimeError(
            f"Unexpected rooms in response: {actual_room_ids!r}"
        )
    if any(len(room.get("available_slots", [])) != 12 for room in payload["rooms"]):
        raise RuntimeError("Each benchmark room should have 12 available slots")


def test_AC_ตรวจสอบห้องว่าง_01_performance(
    base_url: str, users: int, user_count: int | None, selected_date: date
) -> dict[str, float]:
    """วัดตั้งแต่เริ่มส่งคำขอจนรับและตรวจสอบผลลัพธ์ครบ (NFR-PERF-01, ASM-06)."""
    params = {"date": selected_date.isoformat(), "room_type": _ROOM_TYPE}
    if user_count is not None:
        params["user_count"] = str(user_count)
    url = (
        f"{base_url.rstrip('/')}/api/rooms/availability?"
        f"{urlencode(params)}"
    )
    barrier = threading.Barrier(users)

    def search_once() -> float:
        barrier.wait(timeout=60)
        started = time.perf_counter()
        with urlopen(url, timeout=60) as response:
            if response.status != 200:
                raise RuntimeError(f"Unexpected HTTP status: {response.status}")
            payload = json.load(response)
        _validate_response(payload, user_count)
        return time.perf_counter() - started

    round_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=users) as executor:
        latencies = list(executor.map(lambda _: search_once(), range(users)))
    round_seconds = time.perf_counter() - round_started

    within_target = sum(latency <= _TARGET_SECONDS for latency in latencies)
    return {
        "average_seconds": statistics.mean(latencies),
        "maximum_seconds": max(latencies),
        "p95_seconds": _percentile(latencies, 0.95),
        "within_target_percent": within_target * 100 / len(latencies),
        "round_seconds": round_seconds,
    }


def _print_result(users: int, user_count: int | None, metrics: dict[str, float]) -> None:
    filter_label = (
        "ไม่ใช้ตัวกรอง"
        if user_count is None
        else f"กรอง {user_count} คนขึ้นไป"
    )
    target_status = (
        "ถึงเป้าหมาย"
        if metrics["within_target_percent"] >= 95
        else "ต่ำกว่าเป้าหมาย"
    )
    print(
        f"{users} users, {filter_label}: "
        f"<=3s={metrics['within_target_percent']:.1f}%, "
        f"p95={metrics['p95_seconds']:.3f}s, "
        f"เฉลี่ย={metrics['average_seconds']:.3f}s, "
        f"สูงสุด={metrics['maximum_seconds']:.3f}s, "
        f"รอบรวม={metrics['round_seconds']:.3f}s ({target_status})"
    )


async def _run_scenarios(
    base_url: str, user_levels: tuple[int, ...], selected_date: date
) -> None:
    print(
        f"ชุดข้อมูล: {len(store.ROOMS)} ห้อง, {len(store.ROOM_BOOKINGS):,} "
        f"รายการจอง, 60 วัน; เลือกวันที่ {selected_date}"
    )
    print(
        "วัดเวลาจากเริ่มส่ง HTTP request จนรับและตรวจสอบ JSON response ครบ; "
        "ไม่รวมเวลา render ใน browser"
    )
    for users in user_levels:
        for user_count in (None, _FILTERED_USER_COUNT):
            metrics = await asyncio.to_thread(
                test_AC_ตรวจสอบห้องว่าง_01_performance,
                base_url,
                users,
                user_count,
                selected_date,
            )
            _print_result(users, user_count, metrics)
    print("เป้าหมาย NFR-PERF-01: อย่างน้อย 95% ของคำขอไม่เกิน 3 วินาที")


async def _run_server(
    user_levels: tuple[int, ...],
    selected_date: date,
    port: int = 0,
    serve_only: bool = False,
) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(256)
    listener.setblocking(False)
    base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            lifespan="off",
            log_level="error",
            access_log=False,
        )
    )
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        deadline = asyncio.get_running_loop().time() + 15
        while not server.started:
            if server_task.done():
                await server_task
                raise RuntimeError("Availability benchmark server did not start")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Availability benchmark server startup timed out")
            await asyncio.sleep(0.01)

        if serve_only:
            print(
                f"Benchmark API พร้อมใช้งานที่ {base_url}; "
                f"เลือกวันที่ {selected_date}; หยุดด้วย Ctrl+C"
            )
            await server_task
        else:
            await _run_scenarios(base_url, user_levels, selected_date)
    finally:
        server.should_exit = True
        try:
            await server_task
        finally:
            listener.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--users",
        type=int,
        choices=(50, 200),
        action="append",
        help="เลือก concurrency ที่ต้องการ; ใช้ซ้ำได้ ค่าเริ่มต้นคือ 50 และ 200",
    )
    parser.add_argument(
        "--base-url",
        help="ยิง benchmark ไปยัง backend ที่รันข้อมูล benchmark อยู่แล้ว",
    )
    parser.add_argument(
        "--serve-only",
        action="store_true",
        help="เริ่ม API ด้วยข้อมูล benchmark และรอรับคำขอจาก browser/benchmark client",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port สำหรับ --serve-only (ค่าเริ่มต้น 8000)",
    )
    args = parser.parse_args()
    if args.base_url and args.serve_only:
        parser.error("--base-url and --serve-only cannot be used together")

    if (
        DEFAULT_AVAILABILITY_CONFIG.opening_time != wall_time(8, 0)
        or DEFAULT_AVAILABILITY_CONFIG.closing_time != wall_time(20, 0)
        or DEFAULT_AVAILABILITY_CONFIG.slot_minutes != 30
    ):
        raise RuntimeError(
            "Run with the ASM-03 defaults: opening 08:00, closing 20:00, slots 30 minutes"
        )

    rooms, bookings, selected_date = _build_dataset()
    store.ROOMS = rooms
    store.ROOM_BOOKINGS = bookings
    if selected_date not in {booking.booking_date for booking in bookings}:
        raise RuntimeError("Selected benchmark date has no booking data")

    user_levels = tuple(args.users or (50, 200))
    if args.base_url:
        asyncio.run(_run_scenarios(args.base_url, user_levels, selected_date))
    else:
        asyncio.run(
            _run_server(
                user_levels,
                selected_date,
                port=args.port if args.serve_only else 0,
                serve_only=args.serve_only,
            )
        )


if __name__ == "__main__":
    main()
