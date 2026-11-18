from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, MutableSequence
from contextlib import AbstractContextManager
from datetime import date
from decimal import Decimal
from typing import overload

from ..reservations.service import reservation_store_transaction
from .models import (
    FineItem,
    FineStatus,
    PaymentRecord,
    PaymentRequest,
    PaymentReviewRecord,
)

DEMO_MEMBER_ID = "STU-001"

_SEED_FINE_ITEMS = (
    FineItem(
        fine_id="FINE-001",
        member_id=DEMO_MEMBER_ID,
        book_title="การออกแบบซอฟต์แวร์",
        due_date=date(2026, 11, 10),
        returned_date=date(2026, 11, 12),
        overdue_days=2,
        amount=Decimal("10.00"),
    ),
    FineItem(
        fine_id="FINE-002",
        member_id=DEMO_MEMBER_ID,
        book_title="ฐานข้อมูลสำหรับนักพัฒนา",
        due_date=date(2026, 11, 8),
        returned_date=date(2026, 11, 11),
        overdue_days=3,
        amount=Decimal("15.00"),
    ),
)

PAYMENT_REQUESTS: dict[str, PaymentRequest] = {}
PAYMENT_RECORDS: dict[str, PaymentRecord] = {}
PAYMENT_REVIEW_RECORDS: list[PaymentReviewRecord] = []
_STORE_MUTEX = threading.RLock()
_STORE_LOCAL = threading.local()


def initialize_fine_store(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fine_items (
            fine_id TEXT PRIMARY KEY,
            loan_id TEXT REFERENCES loans(loan_id),
            member_id TEXT NOT NULL,
            book_title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            returned_date TEXT NOT NULL,
            overdue_days INTEGER NOT NULL CHECK (overdue_days >= 0),
            applied_rate TEXT NOT NULL,
            amount TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('outstanding', 'paid'))
        )
        """
    )
    for fine in _SEED_FINE_ITEMS:
        connection.execute(
            """
            INSERT OR IGNORE INTO fine_items (
                fine_id, loan_id, member_id, book_title, due_date, returned_date,
                overdue_days, applied_rate, amount, status
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, '5.00', ?, ?)
            """,
            (
                fine.fine_id,
                fine.member_id,
                fine.book_title,
                fine.due_date.isoformat(),
                fine.returned_date.isoformat(),
                fine.overdue_days,
                str(fine.amount),
                fine.status.value,
            ),
        )


def insert_fine_item(
    connection: sqlite3.Connection,
    fine: FineItem,
    *,
    loan_id: str,
    applied_rate: Decimal,
) -> None:
    initialize_fine_store(connection)
    connection.execute(
        """
        INSERT INTO fine_items (
            fine_id, loan_id, member_id, book_title, due_date, returned_date,
            overdue_days, applied_rate, amount, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fine.fine_id,
            loan_id,
            fine.member_id,
            fine.book_title,
            fine.due_date.isoformat(),
            fine.returned_date.isoformat(),
            fine.overdue_days,
            format(applied_rate, "f"),
            format(fine.amount, ".2f"),
            fine.status.value,
        ),
    )


def _fine_from_row(row: sqlite3.Row) -> FineItem:
    return FineItem(
        fine_id=row["fine_id"],
        member_id=row["member_id"],
        book_title=row["book_title"],
        due_date=date.fromisoformat(row["due_date"]),
        returned_date=date.fromisoformat(row["returned_date"]),
        overdue_days=row["overdue_days"],
        amount=Decimal(row["amount"]),
        status=FineStatus(row["status"]),
    )


def _load_fines(connection: sqlite3.Connection) -> list[FineItem]:
    initialize_fine_store(connection)
    return [
        _fine_from_row(row)
        for row in connection.execute(
            "SELECT * FROM fine_items ORDER BY fine_id"
        ).fetchall()
    ]


class _StoreState:
    def __init__(
        self,
        transaction: AbstractContextManager[sqlite3.Connection],
        connection: sqlite3.Connection,
    ) -> None:
        self.transaction = transaction
        self.connection = connection
        self.depth = 1
        self.fines: list[FineItem] | None = None
        self.original_ids: set[str] = set()


def _state_fines(state: _StoreState) -> list[FineItem]:
    if state.fines is None:
        state.fines = _load_fines(state.connection)
        state.original_ids = {fine.fine_id for fine in state.fines}
    return state.fines


def _persist_fines(state: _StoreState) -> None:
    if state.fines is None:
        return
    current_ids = {fine.fine_id for fine in state.fines}
    for fine in state.fines:
        state.connection.execute(
            """
            INSERT INTO fine_items (
                fine_id, loan_id, member_id, book_title, due_date, returned_date,
                overdue_days, applied_rate, amount, status
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, '0.00', ?, ?)
            ON CONFLICT(fine_id) DO UPDATE SET
                member_id = excluded.member_id,
                book_title = excluded.book_title,
                due_date = excluded.due_date,
                returned_date = excluded.returned_date,
                overdue_days = excluded.overdue_days,
                amount = excluded.amount,
                status = excluded.status
            """,
            (
                fine.fine_id,
                fine.member_id,
                fine.book_title,
                fine.due_date.isoformat(),
                fine.returned_date.isoformat(),
                fine.overdue_days,
                format(fine.amount, ".2f"),
                fine.status.value,
            ),
        )
    removed_ids = state.original_ids - current_ids
    if removed_ids:
        state.connection.executemany(
            "DELETE FROM fine_items WHERE fine_id = ?",
            ((fine_id,) for fine_id in removed_ids),
        )


class _StoreLock:
    def __enter__(self) -> _StoreLock:
        _STORE_MUTEX.acquire()
        state: _StoreState | None = getattr(_STORE_LOCAL, "state", None)
        if state is not None:
            state.depth += 1
            return self

        transaction = reservation_store_transaction()
        try:
            connection = transaction.__enter__()
            initialize_fine_store(connection)
        except BaseException as error:
            transaction.__exit__(type(error), error, error.__traceback__)
            _STORE_MUTEX.release()
            raise
        _STORE_LOCAL.state = _StoreState(transaction, connection)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        state: _StoreState = _STORE_LOCAL.state
        state.depth -= 1
        try:
            if state.depth:
                return False
            if exc_type is None:
                _persist_fines(state)
            return state.transaction.__exit__(exc_type, exc_value, traceback)
        except BaseException as error:
            state.transaction.__exit__(type(error), error, error.__traceback__)
            raise
        finally:
            if state.depth == 0:
                del _STORE_LOCAL.state
            _STORE_MUTEX.release()


STORE_LOCK = _StoreLock()


class _FineItemCollection(MutableSequence[FineItem]):
    def _items(self) -> list[FineItem]:
        state: _StoreState | None = getattr(_STORE_LOCAL, "state", None)
        if state is not None:
            return _state_fines(state)
        with reservation_store_transaction() as connection:
            return _load_fines(connection)

    def __iter__(self) -> Iterator[FineItem]:
        return iter(self._items())

    def __len__(self) -> int:
        return len(self._items())

    @overload
    def __getitem__(self, index: int) -> FineItem: ...

    @overload
    def __getitem__(self, index: slice) -> list[FineItem]: ...

    def __getitem__(self, index: int | slice) -> FineItem | list[FineItem]:
        return self._items()[index]

    def __setitem__(self, index: int | slice, value: FineItem | list[FineItem]) -> None:
        if getattr(_STORE_LOCAL, "state", None) is None:
            with STORE_LOCK:
                self[index] = value
            return
        _state_fines(_STORE_LOCAL.state)[index] = value

    def __delitem__(self, index: int | slice) -> None:
        if getattr(_STORE_LOCAL, "state", None) is None:
            with STORE_LOCK:
                del self[index]
            return
        del _state_fines(_STORE_LOCAL.state)[index]

    def insert(self, index: int, value: FineItem) -> None:
        if getattr(_STORE_LOCAL, "state", None) is None:
            with STORE_LOCK:
                self.insert(index, value)
            return
        _state_fines(_STORE_LOCAL.state).insert(index, value)


FINE_ITEMS: MutableSequence[FineItem] = _FineItemCollection()


def reset_store() -> None:
    with STORE_LOCK:
        for fine in FINE_ITEMS:
            fine.status = FineStatus.OUTSTANDING
        PAYMENT_REQUESTS.clear()
        PAYMENT_RECORDS.clear()
        PAYMENT_REVIEW_RECORDS.clear()
