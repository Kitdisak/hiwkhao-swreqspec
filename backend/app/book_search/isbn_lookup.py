from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


class ISBNLookupError(Exception):
    pass


def lookup_isbn(isbn: str) -> dict[str, object]:
    url = (
        "https://openlibrary.org/api/books?bibkeys=ISBN:"
        f"{quote(isbn, safe='')}&format=json&jscmd=data"
    )
    try:
        with urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise ISBNLookupError("ไม่สามารถค้นข้อมูล ISBN ได้ กรุณากรอกข้อมูลเอง") from error
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ISBNLookupError("ไม่สามารถค้นข้อมูล ISBN ได้ กรุณากรอกข้อมูลเอง") from error

    record = data.get(f"ISBN:{isbn}") if isinstance(data, dict) else None
    title = record.get("title") if isinstance(record, dict) else None
    raw_authors = record.get("authors") if isinstance(record, dict) else None
    authors = [
        author.get("name")
        for author in raw_authors or []
        if isinstance(author, dict) and isinstance(author.get("name"), str)
    ]
    if not isinstance(title, str) or not title.strip() or not authors:
        raise ISBNLookupError("ไม่พบข้อมูล ISBN กรุณากรอกข้อมูลเอง")
    return {"title": title.strip(), "authors": authors}
