from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth.session import (
    SESSION_COOKIE,
    SESSION_TIMEOUT_SECONDS,
    create_session,
    get_session_user,
)
from .auth.service import login_user, reset_password
from .book_details.service import get_book_details
from .book_search.service import search_books
from .reservations.service import ReservationError, reserve_book

app = FastAPI(title="Library Search API")


class ReservationRequest(BaseModel):
    title_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=200)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
