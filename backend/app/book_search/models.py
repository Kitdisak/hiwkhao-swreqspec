from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Book:
    title: str
    authors: list[str] = field(default_factory=list)
    isbn: str = ""
    keywords: list[str] = field(default_factory=list)
    item_identifier: str = ""
    ddc_category: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "isbn": self.isbn,
            "keywords": self.keywords,
            "item_identifier": self.item_identifier,
            "ddc_category": self.ddc_category,
        }


BOOKS: list[Book] = [
    Book(
        title="การออกแบบซอฟต์แวร์",
        authors=["อาจารย์สมชาย รักดี"],
        isbn="9786160000011",
        keywords=["software", "design", "engineering"],
        item_identifier="BK-001",
        ddc_category="005.1",
    ),
    Book(
        title="เชิงคำนวณกับปัญญาประดิษฐ์",
        authors=["ดร.ปิยวัฒน์ มณีรัตน์"],
        isbn="9786160000028",
        keywords=["ai", "artificial intelligence", "machine learning"],
        item_identifier="BK-002",
        ddc_category="006.3",
    ),
    Book(
        title="ฐานข้อมูลสำหรับนักพัฒนา",
        authors=["นางสาวกนกวรรณ สินทรัพย์"],
        isbn="9786160000035",
        keywords=["database", "sql", "query"],
        item_identifier="BK-003",
        ddc_category="005.74",
    ),
    Book(
        title="การวิเคราะห์ระบบสารสนเทศ",
        authors=["ผู้ช่วยศาสตราจารย์กชกร ชูสกุล"],
        isbn="9786160000042",
        keywords=["information system", "analysis", "business"],
        item_identifier="BK-004",
        ddc_category="658.403",
    ),
]


def _searchable_texts(book: Book) -> Iterable[str]:
    yield book.title
    yield from book.authors
    yield book.isbn
    yield from book.keywords
