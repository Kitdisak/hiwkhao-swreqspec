from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from .book_search.service import search_books

app = FastAPI(title="Library Search API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
