import { useEffect, useState } from "react";

const POSITION_FIELDS = [
  ["shelf", "ชั้น"],
  ["zone", "โซน"],
  ["call_number", "เลขเรียกหนังสือ"],
];

function hasValue(value) {
  return value !== undefined && value !== null && value !== "";
}

function categoryText(category) {
  if (category.code && category.label && category.code !== category.label) {
    return `${category.code} - ${category.label}`;
  }
  return category.label || category.code;
}

export default function BookDetailPage({ bookId }) {
  const [book, setBook] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [reservationMessage, setReservationMessage] = useState("");
  const [reservationError, setReservationError] = useState("");
  const [isReserving, setIsReserving] = useState(false);
  const [requestId, setRequestId] = useState(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadDetails() {
      try {
        const response = await fetch(`/api/books/${encodeURIComponent(bookId)}`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Book details request failed with status ${response.status}`);
        }

        const data = await response.json();
        if (isCurrent) {
          setBook(data);
        }
      } catch (requestError) {
        console.error("Book details request failed", requestError);
        if (isCurrent) {
          setError("ไม่สามารถโหลดรายละเอียดหนังสือได้");
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    loadDetails();
    return () => {
      isCurrent = false;
    };
  }, [bookId]);

  useEffect(() => {
    let isCurrent = true;
    fetch("/api/auth/session", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Session request failed with status ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        if (isCurrent) {
          setSession(data);
        }
      })
      .catch((requestError) => {
        console.error("Session request failed", requestError);
        if (isCurrent) {
          setSession({ authenticated: false });
        }
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  async function submitReservation() {
    const activeRequestId = requestId || crypto.randomUUID();
    setRequestId(activeRequestId);
    setIsReserving(true);
    setReservationError("");
    setReservationMessage("");

    try {
      const response = await fetch("/api/reservations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title_id: bookId, request_id: activeRequestId }),
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status < 500) {
          setRequestId(null);
        }
        throw new Error(result.message || `Reservation request failed with status ${response.status}`);
      }

      setReservationMessage(result.message);
      setRequestId(null);
    } catch (requestError) {
      console.error("Reservation request failed", requestError);
      setReservationError(requestError.message || "ไม่สามารถส่งคำขอจองได้ กรุณาลองใหม่");
    } finally {
      setIsReserving(false);
    }
  }

  const position = book
    ? POSITION_FIELDS.filter(([field]) => hasValue(book[field])).map(
        ([field, label]) => `${label} ${book[field]}`,
      )
    : [];

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>รายละเอียดหนังสือ</h1>
      </header>

      <a className="back-link" href="/">
        กลับไปหน้าค้นหาหนังสือ
      </a>

      <section className="book-card detail-card" aria-live="polite" aria-busy={isLoading}>
        {isLoading && <p>กำลังโหลดรายละเอียด...</p>}
        {!isLoading && error && <p className="feedback error-message" role="alert">{error}</p>}
        {!isLoading && !error && book && (
          <>
            {hasValue(book.title) && <h2>{book.title}</h2>}
            {book.authors?.length > 0 && (
              <p>
                <strong>ผู้แต่ง:</strong> {book.authors.join(", ")}
              </p>
            )}
            {hasValue(book.isbn) && (
              <p>
                <strong>ISBN:</strong> {book.isbn}
              </p>
            )}
            {book.categories?.length > 0 && (
              <p>
                <strong>หมวดหมู่:</strong>{" "}
                {book.categories.map(categoryText).filter(Boolean).join(", ")}
              </p>
            )}
            {position.length > 0 && (
              <p>
                <strong>ตำแหน่ง:</strong> {position.join(" · ")}
              </p>
            )}
            {book.copies?.length > 0 && (
              <section className="copy-list" aria-label="รายการตัวเล่ม">
                <h3>รายการตัวเล่ม</h3>
                <ul>
                  {book.copies.map((copy, index) => (
                    <li key={copy.item_identifier || `copy-${index}`}>
                      {hasValue(copy.item_identifier) && (
                        <p>
                          <strong>รหัสประจำเล่ม:</strong> {copy.item_identifier}
                        </p>
                      )}
                      {hasValue(copy.status) && (
                        <p>
                          <strong>สถานะ:</strong> {copy.status}
                        </p>
                      )}
                      {copy.status === "Borrowed" && hasValue(copy.expected_return_date) && (
                        <p>
                          <strong>วันที่คาดว่าจะคืน:</strong> {copy.expected_return_date}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <section className="reservation-panel" aria-live="polite">
              <h3>จองหนังสือ</h3>
              {session?.authenticated ? (
                <button type="button" onClick={submitReservation} disabled={isReserving}>
                  {isReserving ? "กำลังส่งคำขอ..." : "ยืนยันการจอง"}
                </button>
              ) : session ? (
                <p>
                  กรุณาเข้าสู่ระบบก่อนจองหนังสือ{" "}
                  <a href="/src/features/002-สมัครสมาชิก-เข้าสู่ระบบ/index.html">
                    ไปหน้าเข้าสู่ระบบ
                  </a>
                </p>
              ) : (
                <p>กำลังตรวจสอบสถานะการเข้าสู่ระบบ...</p>
              )}
              {reservationMessage && (
                <p className="feedback success-message" role="status">{reservationMessage}</p>
              )}
              {reservationError && (
                <p className="feedback error-message" role="alert">{reservationError}</p>
              )}
            </section>
          </>
        )}
      </section>
    </main>
  );
}
