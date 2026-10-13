from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, Query
from fastapi.responses import JSONResponse

from .auth.service import login_user, reset_password
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
    category: str | None = Query(default=None),
    author: str | None = Query(default=None),
    search_type: str | None = Query(default=None, alias="searchType"),
) -> dict[str, Any]:
    results = search_books(
        query=query,
        category=category,
        author=author,
        search_type=search_type,
    )

    if not results:
        return JSONResponse(content={"results": [], "message": "ไม่พบหนังสือที่ค้นหา"})

    return {"results": results, "message": None}
