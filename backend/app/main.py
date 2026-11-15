from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query

from .auth.service import login_user, reset_password
from .book_details.service import get_book_details
from .book_search.service import search_books

app = FastAPI(title="Library Search API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login_endpoint(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    username = payload.get("username") or payload.get("userName") or payload.get("student_id") or payload.get("studentId")
    email = payload.get("email")
    password = payload.get("password")
    result = login_user(username=username, email=email, password=password)
    return result


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
def book_details_endpoint(book_id: str) -> dict[str, Any]:
    """แสดงรายละเอียดที่มีอยู่ของหนังสือที่เลือก (FR-ดูรายละเอียดและตำแหน่งหนังสือ-01 ถึง FR-ดูรายละเอียดและตำแหน่งหนังสือ-05)."""
    details = get_book_details(book_id)
    if details is None:
        raise HTTPException(status_code=404, detail="ไม่พบหนังสือที่เลือก")
    return details
