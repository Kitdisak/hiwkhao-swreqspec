from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from json import JSONDecodeError
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from .auth.session import (
    SESSION_COOKIE,
    SESSION_TIMEOUT_SECONDS,
    create_session,
    get_session_user,
)
from .auth.service import find_borrow_member, login_user, reset_password
from .book_details.service import get_book_details
from .book_search.service import search_books
from .loans.service import (
    LoanError,
    check_copy,
    confirm_loan,
    lookup_member,
)
from .reservations.service import (
    ReservationError,
    list_reservations_for_member,
    reserve_book,
)
from .fine_payment import service as fine_payment_service
from .renew_loan.service import get_member_loans, renew_loan
from .returns import service as return_service
from .rooms import availability as room_availability
from .rooms import booking as room_booking
from .rooms.config import DEFAULT_AVAILABILITY_CONFIG
from .rooms.models import AvailabilitySlot, Room
from .rooms import store as room_store


async def _poll_payment_statuses() -> None:
    while True:
        await asyncio.to_thread(fine_payment_service.poll_pending_requests)
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(_: FastAPI):
    polling_task = asyncio.create_task(_poll_payment_statuses())
    try:
        yield
    finally:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Library API", lifespan=lifespan)


class ReservationRequest(BaseModel):
    title_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=200)


class LoanCheckRequest(BaseModel):
    member_identifier: str = Field(min_length=1)
    item_identifier: str = Field(min_length=1)
    pending_item_identifiers: list[str] = Field(default_factory=list)


class LoanRequest(BaseModel):
    member_identifier: str = Field(min_length=1)
    item_identifiers: list[str] = Field(min_length=1)
    request_id: str = Field(min_length=1, max_length=200)


class ReturnRequest(BaseModel):
    item_identifier: str = Field(min_length=1)


class RoomReservationCheckRequest(BaseModel):
    room_id: str = Field(min_length=1)
    booking_date: date
    start_time: time
    end_time: time
    user_count: Any = None


class RoomReservationRequest(RoomReservationCheckRequest):
    request_id: str = Field(min_length=1, max_length=200)


def _get_room_available_slots(
    room: Room,
    booking_date: date,
    user_count: int,
    now: datetime,
) -> tuple[AvailabilitySlot, ...]:
    results = room_availability.calculate_availability(
        rooms=[room],
        bookings=room_store.get_room_bookings(),
        selected_date=booking_date,
        room_type=room.room_type,
        user_count=user_count,
        now=now,
        config=DEFAULT_AVAILABILITY_CONFIG,
    )
    return results[0].available_slots if results else ()


def _serialize_room_slots(
    slots: tuple[AvailabilitySlot, ...],
) -> list[dict[str, str]]:
    return [
        {
            "start_time": slot.start_time.isoformat(timespec="minutes"),
            "end_time": slot.end_time.isoformat(timespec="minutes"),
        }
        for slot in slots
    ]


def _serialize_room_booking(booking: Any) -> dict[str, Any]:
    return {
        "booking_id": booking.booking_id,
        "room_id": booking.room_id,
        "booking_date": booking.booking_date.isoformat(),
        "start_time": booking.start_time.isoformat(timespec="minutes"),
        "end_time": booking.end_time.isoformat(timespec="minutes"),
        "member_id": booking.member_id,
        "user_count": booking.user_count,
        "status": booking.status,
    }


def _librarian_access_error(request: Request) -> JSONResponse | None:
    actor = get_session_user(request.cookies.get(SESSION_COOKIE))
    if actor is None:
        return JSONResponse(
            status_code=401,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบก่อนบันทึกการยืมหนังสือ",
            },
        )
    if actor.user_type != "staff":
        return JSONResponse(
            status_code=403,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "librarian_required",
                "message": "ไม่อนุญาตให้บันทึกการยืมหนังสือ",
            },
        )
    return None


def _return_librarian_access_error(request: Request) -> JSONResponse | None:
    actor = get_session_user(request.cookies.get(SESSION_COOKIE))
    if actor is None:
        return JSONResponse(
            status_code=401,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบก่อนรับคืนหนังสือ",
            },
        )
    if actor.user_type != "staff":
        return JSONResponse(
            status_code=403,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "librarian_required",
                "message": "ไม่อนุญาตให้รับคืนหนังสือ",
            },
        )
    return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/rooms/availability")
def room_availability_endpoint(
    search_date: date = Query(alias="date"),
    room_type: str = Query(min_length=1),
    user_count: str | None = Query(default=None),
) -> dict[str, Any]:
    """ค้นหาห้องและช่วงเวลาว่างโดยอ้างอิงรายการจองเดิม (FR-ตรวจสอบห้องว่าง-01 ถึง FR-ตรวจสอบห้องว่าง-04)."""
    try:
        parsed_user_count = room_availability.parse_user_count(user_count)
    except room_availability.InvalidUserCount:
        return JSONResponse(
            status_code=422,
            content={
                "rooms": [],
                "message": "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป",
                "code": "invalid_user_count",
            },
        )

    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    try:
        room_availability.validate_search_date(search_date, now)
    except room_availability.InvalidSearchDate:
        return JSONResponse(
            status_code=422,
            content={
                "rooms": [],
                "message": "เลือกวันที่ตั้งแต่วันนี้เป็นต้นไป",
                "code": "date_before_today",
            },
        )

    try:
        results = room_availability.calculate_availability(
            rooms=room_store.get_rooms(),
            bookings=room_store.get_room_bookings(),
            selected_date=search_date,
            room_type=room_type,
            user_count=parsed_user_count,
            now=now,
        )
    except room_availability.InvalidSearchDate as error:
        raise HTTPException(
            status_code=422,
            detail="เลือกวันที่ตั้งแต่วันนี้เป็นต้นไป",
        ) from error

    rooms = [
        {
            "room_id": room.room_id,
            "room_type": room.room_type,
            "capacity": room.capacity,
            "available_slots": [
                {
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                }
                for slot in room.available_slots
            ],
        }
        for room in results
    ]
    return {
        "rooms": rooms,
        "message": None if rooms else "ไม่มีห้องว่าง",
    }


@app.post("/api/room-reservations/check", response_model=None)
async def check_room_reservation_endpoint(
    request: Request,
) -> dict[str, Any] | JSONResponse:
    """ตรวจข้อมูลและความว่างโดยไม่สร้างรายการ (FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-04, FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-05)."""
    if get_session_user(request.cookies.get(SESSION_COOKIE)) is None:
        return JSONResponse(
            status_code=401,
            content={
                "available": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบก่อนจองห้อง",
            },
        )

    try:
        payload_data = await request.json()
    except (JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=422,
            content={
                "available": False,
                "code": "invalid_request",
                "message": "ข้อมูลคำขอไม่ถูกต้อง",
            },
        )

    try:
        payload = RoomReservationCheckRequest.model_validate(payload_data)
    except ValidationError as error:
        return JSONResponse(
            status_code=422,
            content={
                "available": False,
                "code": "invalid_request",
                "message": "ข้อมูลคำขอไม่ถูกต้อง",
                "errors": error.errors(),
            },
        )

    room = next(
        (
            candidate
            for candidate in room_store.get_rooms()
            if candidate.room_id == payload.room_id
        ),
        None,
    )
    if room is None:
        return JSONResponse(
            status_code=404,
            content={
                "available": False,
                "code": "room_not_found",
                "message": "ไม่พบห้องที่เลือก",
            },
        )

    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    try:
        room_booking.validate_booking_input(
            room=room,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            user_count=payload.user_count,
            now=now,
            config=DEFAULT_AVAILABILITY_CONFIG,
        )
    except room_booking.BookingValidationError as error:
        return JSONResponse(
            status_code=422,
            content={
                "available": False,
                "code": error.code,
                "message": error.message,
            },
        )

    available_slots = _get_room_available_slots(
        room, payload.booking_date, payload.user_count, now
    )
    selected_slots = [
        slot
        for slot in available_slots
        if slot.start_time >= payload.start_time
        and slot.end_time <= payload.end_time
    ]
    start_minutes = payload.start_time.hour * 60 + payload.start_time.minute
    end_minutes = payload.end_time.hour * 60 + payload.end_time.minute
    duration_minutes = end_minutes - start_minutes
    required_slots = duration_minutes // DEFAULT_AVAILABILITY_CONFIG.slot_minutes
    if len(selected_slots) == required_slots:
        return {
            "available": True,
            "message": None,
            "summary": {
                "room_id": room.room_id,
                "room_type": room.room_type,
                "booking_date": payload.booking_date.isoformat(),
                "start_time": payload.start_time.isoformat(timespec="minutes"),
                "end_time": payload.end_time.isoformat(timespec="minutes"),
                "user_count": payload.user_count,
            },
        }

    serialized_slots = _serialize_room_slots(available_slots)
    message = (
        "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่"
        if serialized_slots
        else "ห้องนี้ไม่มีช่วงว่างในวันที่เลือก"
    )
    return {
        "available": False,
        "message": message,
        "available_slots": serialized_slots,
    }


@app.post("/api/room-reservations", response_model=None)
async def create_room_reservation_endpoint(
    request: Request,
) -> dict[str, Any] | JSONResponse:
    """ยืนยันการจองด้วยการตรวจและบันทึกแบบ atomic (FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-02, FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-03)."""
    member = get_session_user(request.cookies.get(SESSION_COOKIE))
    if member is None:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบก่อนจองห้อง",
            },
        )

    try:
        payload_data = await request.json()
    except (JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "code": "invalid_request",
                "message": "ข้อมูลคำขอไม่ถูกต้อง",
            },
        )

    try:
        payload = RoomReservationRequest.model_validate(payload_data)
    except ValidationError as error:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "code": "invalid_request",
                "message": "ข้อมูลคำขอไม่ถูกต้อง",
                "errors": error.errors(),
            },
        )

    if not payload.request_id.strip():
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "code": "invalid_request_id",
                "message": "กรุณาระบุตัวระบุคำขอ",
            },
        )

    room = next(
        (
            candidate
            for candidate in room_store.get_rooms()
            if candidate.room_id == payload.room_id
        ),
        None,
    )
    if room is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "code": "room_not_found",
                "message": "ไม่พบห้องที่เลือก",
            },
        )

    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    try:
        booking = room_booking.create_room_booking(
            room=room,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            user_count=payload.user_count,
            member_id=member.student_id or member.username,
            request_id=payload.request_id,
            now=now,
            config=DEFAULT_AVAILABILITY_CONFIG,
        )
    except room_booking.BookingValidationError as error:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "code": error.code,
                "message": error.message,
            },
        )
    except room_booking.RoomBookingConflict as error:
        if error.code == "room_unavailable":
            available_slots = _serialize_room_slots(
                _get_room_available_slots(
                    room, payload.booking_date, payload.user_count, now
                )
            )
            message = (
                "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่"
                if available_slots
                else "ห้องนี้ไม่มีช่วงว่างในวันที่เลือก"
            )
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "available": False,
                    "code": error.code,
                    "message": message,
                    "available_slots": available_slots,
                },
            )
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "code": error.code,
                "message": error.message,
            },
        )

    return {
        "success": True,
        "booking": {
            "booking_id": booking.booking_id,
            "room_id": booking.room_id,
            "booking_date": booking.booking_date.isoformat(),
            "start_time": booking.start_time.isoformat(timespec="minutes"),
            "end_time": booking.end_time.isoformat(timespec="minutes"),
            "request_id": booking.request_id,
            "member_id": booking.member_id,
            "user_count": booking.user_count,
        },
    }


@app.get("/api/me/room-reservations", response_model=None)
def list_member_room_reservations(request: Request) -> dict[str, Any] | JSONResponse:
    """แสดงรายการจองของผู้ใช้จาก session พร้อมสถานะ (FR-ติดตาม-/-ยกเลิกการจองห้อง-01)."""
    member = get_session_user(request.cookies.get(SESSION_COOKIE))
    if member is None:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบ",
            },
        )

    member_id = member.student_id or member.username
    bookings = room_store.get_member_room_bookings(member_id)
    return {
        "bookings": [
            _serialize_room_booking(booking)
            for booking in bookings
        ]
    }


@app.get("/api/me/room-reservations/{booking_id}", response_model=None)
def get_member_room_reservation(
    booking_id: str,
    request: Request,
) -> dict[str, Any] | JSONResponse:
    """อ่านรายละเอียดรายการโดยไม่เปลี่ยนข้อมูล (FR-ติดตาม-/-ยกเลิกการจองห้อง-05)."""
    member = get_session_user(request.cookies.get(SESSION_COOKIE))
    if member is None:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบ",
            },
        )

    member_id = member.student_id or member.username
    booking = room_store.get_room_booking(booking_id)
    if booking is None or booking.member_id != member_id:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "code": "room_reservation_not_found",
                "message": "ไม่พบรายการจอง",
            },
        )
    return {"booking": _serialize_room_booking(booking)}


@app.post("/api/me/room-reservations/{booking_id}/cancel", response_model=None)
def cancel_member_room_reservation(
    booking_id: str,
    request: Request,
) -> dict[str, Any] | JSONResponse:
    """ยกเลิกรายการของเจ้าของภายใต้ lock ต่อห้อง (FR-ติดตาม-/-ยกเลิกการจองห้อง-02 ถึง FR-04)."""
    member = get_session_user(request.cookies.get(SESSION_COOKIE))
    if member is None:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบ",
            },
        )

    member_id = member.student_id or member.username
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    result = room_booking.cancel_room_booking(
        booking_id=booking_id,
        member_id=member_id,
        now=now,
    )
    if result.outcome == "not_allowed":
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "code": "cancellation_not_allowed",
                "message": "ไม่สามารถยกเลิกได้",
            },
        )
    if result.outcome == "already_cancelled":
        return {
            "success": True,
            "outcome": "already_cancelled",
            "message": "ยกเลิกแล้ว",
            "booking": _serialize_room_booking(result.booking),
        }
    return {
        "success": True,
        "outcome": "cancelled",
        "message": None,
        "booking": _serialize_room_booking(result.booking),
    }


@app.post("/api/auth/login")
def login_endpoint(
    request: Request,
    response: Response,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    username = payload.get("username") or payload.get("userName") or payload.get("student_id") or payload.get("studentId")
    email = payload.get("email")
    password = payload.get("password")
    result = login_user(username=username, email=email, password=password)
    if result.get("success"):
        token = create_session(result["user"]["username"])
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_TIMEOUT_SECONDS,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
    return result


@app.get("/api/auth/session")
def auth_session_endpoint(request: Request) -> dict[str, Any]:
    member = get_session_user(request.cookies.get(SESSION_COOKIE))
    if member is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "member_id": member.student_id or member.username,
        "username": member.username,
    }


@app.post("/api/auth/password-reset")
def password_reset_endpoint(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    student_id = payload.get("student_id") or payload.get("studentId") or payload.get("username")
    new_password = payload.get("new_password") or payload.get("newPassword")
    result = reset_password(student_id=student_id, new_password=new_password)
    return result


@app.get("/api/books/search")
def search_books_endpoint(
    query: str | None = Query(default=None, alias="query"),
    category: list[str] | None = Query(default=None),
    author: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    """ค้นหาหนังสือและคืนข้อความเมื่อไม่พบผลลัพธ์ (FR-ค้นหาหนังสือ-01, FR-ค้นหาหนังสือ-02, FR-ค้นหาหนังสือ-03)."""

    results = search_books(
        query=query,
        categories=category,
        authors=author,
    )

    if not results:
        return {"results": [], "message": "ไม่พบหนังสือที่ค้นหา"}

    return {"results": results, "message": None}


@app.get("/api/books/{book_id}")
def book_details_endpoint(book_id: str, response: Response) -> dict[str, Any]:
    """แสดงรายละเอียดที่มีอยู่ของหนังสือที่เลือก (FR-ดูรายละเอียดและตำแหน่งหนังสือ-01 ถึง FR-ดูรายละเอียดและตำแหน่งหนังสือ-05)."""
    details = get_book_details(book_id)
    if details is None:
        raise HTTPException(status_code=404, detail="ไม่พบหนังสือที่เลือก")
    response.headers["Cache-Control"] = "no-store"
    return details


@app.post("/api/reservations")
def create_reservation_endpoint(
    payload: ReservationRequest, request: Request
) -> Any:
    """สร้างการจองและแจ้งลำดับคิว (FR-จองหนังสือ-01 ถึง FR-จองหนังสือ-05)."""
    member = get_session_user(request.cookies.get(SESSION_COOKIE))
    if member is None:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบก่อนจองหนังสือ",
            },
        )
    try:
        return reserve_book(member, payload.title_id, payload.request_id)
    except ReservationError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "success": False,
                "code": error.code,
                "message": error.message,
            },
        )


@app.get("/api/me/reservations")
def list_my_reservations_endpoint(request: Request, response: Response) -> Any:
    """แสดงรายการจองของผู้ใช้และสถานะล่าสุด (FR-ติดตามสถานะการจองหนังสือ-01 ถึง FR-ติดตามสถานะการจองหนังสือ-03, NFR-ACC-01)."""
    response.headers["Cache-Control"] = "no-store"
    member = get_session_user(request.cookies.get(SESSION_COOKIE))
    if member is None:
        return JSONResponse(
            status_code=401,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "authentication_required",
                "message": "กรุณาเข้าสู่ระบบก่อนดูรายการจอง",
            },
        )
    try:
        return {"reservations": list_reservations_for_member(member)}
    except ReservationError as error:
        return JSONResponse(
            status_code=error.status_code,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": error.code,
                "message": error.message,
            },
        )


@app.get("/api/members/lookup")
def borrowing_member_lookup_endpoint(
    request: Request,
    response: Response,
    identifier: str = Query(min_length=1),
) -> Any:
    """ค้นหาสมาชิกสำหรับบันทึกการยืม (FR-บันทึกการยืมหนังสือ-01, ASM-19)."""
    access_error = _librarian_access_error(request)
    if access_error:
        return access_error
    response.headers["Cache-Control"] = "no-store"
    member = lookup_member(identifier)
    if member is None:
        return JSONResponse(
            status_code=404,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "member_not_found",
                "message": "ไม่พบข้อมูลสมาชิก",
            },
        )
    return {"member": member}


@app.post("/api/loans/check")
def check_loan_copy_endpoint(
    payload: LoanCheckRequest, request: Request, response: Response
) -> Any:
    """ตรวจ Copy ที่สแกนก่อนยืนยัน (FR-บันทึกการยืมหนังสือ-02, FR-06)."""
    access_error = _librarian_access_error(request)
    if access_error:
        return access_error
    response.headers["Cache-Control"] = "no-store"
    member = find_borrow_member(payload.member_identifier)
    if member is None:
        return JSONResponse(
            status_code=404,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "member_not_found",
                "message": "ไม่พบข้อมูลสมาชิก",
            },
        )
    return check_copy(
        member,
        payload.item_identifier,
        payload.pending_item_identifiers,
    )


@app.post("/api/loans")
def record_loan_endpoint(
    payload: LoanRequest, request: Request, response: Response
) -> Any:
    """บันทึก Loan/Copy และ reservation ใน transaction เดียว (FR-04, NFR-DATA-01)."""
    access_error = _librarian_access_error(request)
    if access_error:
        return access_error
    response.headers["Cache-Control"] = "no-store"
    member = find_borrow_member(payload.member_identifier)
    if member is None:
        return JSONResponse(
            status_code=404,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": "member_not_found",
                "message": "ไม่พบข้อมูลสมาชิก",
            },
        )
    try:
        return confirm_loan(
            member,
            payload.item_identifiers,
            payload.request_id,
        )
    except LoanError as error:
        return JSONResponse(
            status_code=error.status_code,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": error.code,
                "message": error.message,
            },
        )


@app.get("/api/returns/lookup", response_model=None)
def lookup_return_endpoint(
    request: Request,
    response: Response,
    item_identifier: str = Query(min_length=1),
) -> Any:
    """ค้นหารายการยืมและประมาณค่าปรับ (FR-01 ถึง FR-03)."""
    access_error = _return_librarian_access_error(request)
    if access_error:
        return access_error
    response.headers["Cache-Control"] = "no-store"
    try:
        return return_service.lookup_return(item_identifier)
    except return_service.ReturnError as error:
        return JSONResponse(
            status_code=error.status_code,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": error.code,
                "message": error.message,
            },
        )


@app.post("/api/returns", response_model=None)
def confirm_return_endpoint(
    payload: ReturnRequest,
    request: Request,
    response: Response,
) -> Any:
    """ยืนยันคืนและอัปเดต Loan/Copy/Fine/Reservation แบบ atomic (FR-04)."""
    access_error = _return_librarian_access_error(request)
    if access_error:
        return access_error
    response.headers["Cache-Control"] = "no-store"
    try:
        return return_service.confirm_return(payload.item_identifier)
    except return_service.ReturnError as error:
        return JSONResponse(
            status_code=error.status_code,
            headers={"Cache-Control": "no-store"},
            content={
                "success": False,
                "code": error.code,
                "message": error.message,
            },
        )


@app.get("/api/loans")
def list_loans_endpoint(member_id: str | None = Query(default=None, alias="member_id")) -> dict[str, Any]:
    """แสดงรายการยืมที่เปิดอยู่สำหรับสมาชิก (FR-ต่ออายุการยืมหนังสือ-01)."""
    return {"loans": get_member_loans(member_id)}


@app.get("/api/members/{member_id}/loans")
def member_loans_endpoint(member_id: str) -> dict[str, Any]:
    return {"member_id": member_id, "loans": get_member_loans(member_id)}


@app.post("/api/loans/{loan_id}/renew")
def renew_loan_endpoint(
    loan_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """ส่งคำขอต่ออายุหนังสือและคืนผลตามเงื่อนไข (FR-ต่ออายุการยืมหนังสือ-02 ถึง FR-ต่ออายุการยืมหนังสือ-05)."""
    member_id = payload.get("member_id") or payload.get("memberId") or payload.get("user_id")
    member_type = payload.get("member_type") or payload.get("memberType")
    renewed_by = payload.get("renewed_by") or payload.get("renewedBy") or member_id

    result = renew_loan(
        loan_id=loan_id,
        member_id=member_id,
        member_type=member_type,
        renewed_by=renewed_by,
    )
    return result


@app.get("/api/me/fines")
def member_fines_endpoint(
    member_id: str = Query(default=fine_payment_service.DEMO_MEMBER_ID, alias="member_id"),
) -> dict[str, Any]:
    """แสดงรายการค่าปรับค้างและยอดรวม (FR-ชำระค่าปรับออนไลน์-01)."""
    return fine_payment_service.list_member_fines(member_id)


@app.post("/api/payments")
def start_payment_endpoint(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """สร้างคำขอชำระและส่งไปยัง Gateway (FR-ชำระค่าปรับออนไลน์-02, FR-ชำระค่าปรับออนไลน์-05)."""
    member_id = payload.get("member_id") or fine_payment_service.DEMO_MEMBER_ID
    channel = payload.get("channel")
    try:
        return fine_payment_service.start_payment(member_id=member_id, channel=channel or "")
    except fine_payment_service.PaymentDomainError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.post("/api/payments/result")
def gateway_payment_result_endpoint(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """ตรวจผล callback ผ่าน adapter ก่อนอัปเดตสถานะ (FR-ชำระค่าปรับออนไลน์-02, FR-ชำระค่าปรับออนไลน์-03, NFR-REL-01)."""
    try:
        return fine_payment_service.handle_gateway_callback(payload)
    except fine_payment_service.PaymentDomainError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.post("/api/payments/{payment_ref}/status-check")
def payment_status_check_endpoint(
    payment_ref: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """ตรวจสถานะคำขอเดิมโดยใช้ payment_ref เดิม (FR-ชำระค่าปรับออนไลน์-04)."""
    member_id = payload.get("member_id") or fine_payment_service.DEMO_MEMBER_ID
    try:
        return fine_payment_service.check_payment_status(
            payment_ref,
            member_id=member_id,
        )
    except fine_payment_service.PaymentDomainError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
