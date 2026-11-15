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

  useEffect(() => {
    let isCurrent = true;

    async function loadDetails() {
      try {
        const response = await fetch(`/api/books/${encodeURIComponent(bookId)}`);
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
            {hasValue(book.status) && (
              <p>
                <strong>สถานะ:</strong> {book.status}
              </p>
            )}
            {position.length > 0 && (
              <p>
                <strong>ตำแหน่ง:</strong> {position.join(" · ")}
              </p>
            )}
            {book.status === "Borrowed" && hasValue(book.expected_return_date) && (
              <p>
                <strong>วันที่คาดว่าจะคืน:</strong> {book.expected_return_date}
              </p>
            )}
          </>
        )}
      </section>
    </main>
  );
}
