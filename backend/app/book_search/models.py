from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Category:
    """หมวดหมู่ตามมาตรฐานที่ห้องสมุดกำหนด (DOM-OPAC-06)."""

    code: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "label": self.label}


@dataclass(frozen=True)
class BookCopy:
    """ตัวเล่มที่มีรหัสและสถานะของตนเอง (DOM-OPAC-05, FR-ดูรายละเอียดและตำแหน่งหนังสือ-02)."""

    book_id: str
    item_identifier: str
    status: str | None = None
    expected_return_date: str | None = None
    book_type: str | None = None


@dataclass(frozen=True)
class CatalogRecord:
    """ระเบียนชื่อเรื่องสำหรับค้นหาและแสดงรายละเอียด (FR-ค้นหาหนังสือ-01, FR-ดูรายละเอียดและตำแหน่งหนังสือ-01)."""

    book_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    isbn: str = ""
    keywords: list[str] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)
    copies: list[BookCopy] = field(default_factory=list)
    shelf: str | None = None
    zone: str | None = None
    call_number: str | None = None

    def to_dict(self) -> dict:
        """คืนข้อมูลรายการค้นหาพร้อมรหัสทุกตัวเล่ม (FR-ค้นหาหนังสือ-01, ASM-08)."""
        return {
            "book_id": self.book_id,
            "title": self.title,
            "authors": self.authors,
            "isbn": self.isbn,
            "keywords": self.keywords,
            "categories": [category.to_dict() for category in self.categories],
            "item_identifiers": [copy.item_identifier for copy in self.copies],
        }

    def to_detail_dict(self) -> dict:
        """คืนเฉพาะฟิลด์รายละเอียดที่มีอยู่ (FR-ดูรายละเอียดและตำแหน่งหนังสือ-01 ถึง FR-ดูรายละเอียดและตำแหน่งหนังสือ-05)."""
        details: dict[str, Any] = {"book_id": self.book_id}
        if self.title:
            details["title"] = self.title
        available_authors = [author for author in self.authors if author]
        if available_authors:
            details["authors"] = available_authors
        if self.isbn:
            details["isbn"] = self.isbn
        available_categories = [
            category.to_dict()
            for category in self.categories
            if category.code or category.label
        ]
        if available_categories:
            details["categories"] = available_categories

        for field_name in ("shelf", "zone", "call_number"):
            value = getattr(self, field_name)
            if value:
                details[field_name] = value

        copies = []
        for copy in self.copies:
            copy_details: dict[str, str] = {}
            if copy.item_identifier:
                copy_details["item_identifier"] = copy.item_identifier
            if copy.status:
                copy_details["status"] = copy.status
            if copy.status == "Borrowed" and copy.expected_return_date:
                copy_details["expected_return_date"] = copy.expected_return_date
            copies.append(copy_details)
        if copies:
            details["copies"] = copies
        return details


def validate_unique_item_identifiers(records: list[CatalogRecord]) -> None:
    """ตรวจว่ารหัสประจำเล่มทุกค่าไม่ว่างและไม่ซ้ำ (DOM-OPAC-05)."""

    identifiers: set[str] = set()
    for record in records:
        for copy in record.copies:
            if not copy.item_identifier or copy.item_identifier in identifiers:
                raise ValueError(
                    f"รหัสประจำเล่มต้องมีค่าและไม่ซ้ำกัน: {copy.item_identifier!r}"
                )
            identifiers.add(copy.item_identifier)


CATALOG_RECORDS: list[CatalogRecord] = [
    CatalogRecord(
        book_id="BOOK-001",
        title="การออกแบบซอฟต์แวร์",
        authors=["อาจารย์สมชาย รักดี"],
        isbn="9786160000011",
        keywords=["software", "design", "engineering"],
        categories=[Category(code="005.1", label="005.1")],
        copies=[
            BookCopy(book_id="BOOK-001", item_identifier="BK-001"),
        ],
    ),
    CatalogRecord(
        book_id="BOOK-002",
        title="เชิงคำนวณกับปัญญาประดิษฐ์",
        authors=["ดร.ปิยวัฒน์ มณีรัตน์"],
        isbn="9786160000028",
        keywords=["ai", "artificial intelligence", "machine learning"],
        categories=[Category(code="006.3", label="006.3")],
        copies=[
            BookCopy(book_id="BOOK-002", item_identifier="BK-002"),
        ],
    ),
    CatalogRecord(
        book_id="BOOK-003",
        title="ฐานข้อมูลสำหรับนักพัฒนา",
        authors=["นางสาวกนกวรรณ สินทรัพย์"],
        isbn="9786160000035",
        keywords=["database", "sql", "query"],
        categories=[Category(code="005.74", label="005.74")],
        copies=[
            BookCopy(book_id="BOOK-003", item_identifier="BK-003"),
        ],
    ),
    CatalogRecord(
        book_id="BOOK-004",
        title="การวิเคราะห์ระบบสารสนเทศ",
        authors=["ผู้ช่วยศาสตราจารย์กชกร ชูสกุล"],
        isbn="9786160000042",
        keywords=["information system", "analysis", "business"],
        categories=[Category(code="658.403", label="658.403")],
        copies=[
            BookCopy(book_id="BOOK-004", item_identifier="BK-004"),
        ],
    ),
]

validate_unique_item_identifiers(CATALOG_RECORDS)

# Keep the previous names available to feature modules that import the catalog.
BOOKS = CATALOG_RECORDS
Book = CatalogRecord
