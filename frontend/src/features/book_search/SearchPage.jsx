import { useState } from "react";

const SEARCH_ENDPOINT = "/api/books/search";

function FilterValues({ label, value, onChange, values, onAdd, onRemove }) {
  // FR-ค้นหาหนังสือ-03: รวบรวมค่าตัวกรองหลายค่า
  const fieldId = `filter-${label}`;

  return (
    <fieldset className="filter-group">
      <legend>{label}</legend>
      <div className="filter-entry">
        <label className="visually-hidden" htmlFor={fieldId}>
          เพิ่ม{label}
        </label>
        <input
          id={fieldId}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onAdd();
            }
          }}
          placeholder={`พิมพ์${label}`}
        />
        <button type="button" className="secondary-button" onClick={onAdd}>
          เพิ่ม
        </button>
      </div>
      {values.length > 0 && (
        <ul className="filter-values" aria-label={`${label}ที่เลือก`}>
          {values.map((item) => (
            <li key={item}>
              <span>{item}</span>
              <button
                type="button"
                className="remove-button"
                onClick={() => onRemove(item)}
                aria-label={`นำ${item}ออกจากตัวกรอง${label}`}
              >
                ลบ
              </button>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [categoryDraft, setCategoryDraft] = useState("");
  const [authorDraft, setAuthorDraft] = useState("");
  const [categories, setCategories] = useState([]);
  const [authors, setAuthors] = useState([]);
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // FR-ค้นหาหนังสือ-03: เก็บค่าตัวกรองที่ผู้ใช้เลือกแต่ละค่า
  function addFilterValue(value, selectedValues, setValue, setValues) {
    const filterValue = value.trim();
    if (
      filterValue &&
      !selectedValues.some(
        (existing) => existing.toLocaleLowerCase() === filterValue.toLocaleLowerCase(),
      )
    ) {
      setValues((current) => [...current, filterValue]);
    }
    setValue("");
  }

  async function submitSearch(event) {
    // FR-ค้นหาหนังสือ-01/03: ส่งคำค้นเดียวและค่าตัวกรองทั้งหมด
    event.preventDefault();
    setIsLoading(true);
    setError("");
    setMessage("");

    const params = new URLSearchParams();
    const normalizedQuery = query.trim();
    if (normalizedQuery) {
      params.set("query", normalizedQuery);
    }
    categories.forEach((value) => params.append("category", value));
    authors.forEach((value) => params.append("author", value));

    try {
      const response = await fetch(`${SEARCH_ENDPOINT}?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`Search request failed with status ${response.status}`);
      }

      const data = await response.json();
      if (!Array.isArray(data.results)) {
        throw new Error("Search response has no results list");
      }

      setResults(data.results);
      setMessage(data.results.length === 0 ? data.message : "");
    } catch (requestError) {
      console.error("Book search failed", requestError);
      setResults([]);
      setError("ไม่สามารถค้นหาหนังสือได้ กรุณาลองใหม่");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>ค้นหาหนังสือ</h1>
        <p>ค้นหาด้วยชื่อหนังสือ ผู้แต่ง ISBN หรือคำสำคัญ</p>
        <a className="feature-link" href="/fines">ชำระค่าปรับ</a>
        <a className="feature-link" href="/rooms/availability">
          ตรวจสอบห้องว่าง
        </a>
        <a className="feature-link" href="/my-reservations">
          รายการจองของฉัน
        </a>
        <a className="feature-link" href="/loans/new">
          บันทึกการยืมหนังสือ
        </a>
        <a className="feature-link" href="/returns">
          รับคืนหนังสือ
        </a>
        <a className="feature-link" href="/manage/books">
          จัดการข้อมูลหนังสือ
        </a>
      </header>

      <form className="search-panel" onSubmit={submitSearch}>
        <label htmlFor="book-query">คำค้น</label>
        <div className="search-entry">
          <input
            id="book-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="พิมพ์คำค้น"
          />
          <button type="submit" disabled={isLoading}>
            {isLoading ? "กำลังค้นหา..." : "ค้นหา"}
          </button>
        </div>

        <div className="filters">
          <FilterValues
            label="หมวดหมู่"
            value={categoryDraft}
            onChange={setCategoryDraft}
            values={categories}
            onAdd={() =>
              addFilterValue(
                categoryDraft,
                categories,
                setCategoryDraft,
                setCategories,
              )
            }
            onRemove={(value) =>
              setCategories((current) => current.filter((item) => item !== value))
            }
          />
          <FilterValues
            label="ผู้แต่ง"
            value={authorDraft}
            onChange={setAuthorDraft}
            values={authors}
            onAdd={() =>
              addFilterValue(authorDraft, authors, setAuthorDraft, setAuthors)
            }
            onRemove={(value) =>
              setAuthors((current) => current.filter((item) => item !== value))
            }
          />
        </div>
      </form>

      <section className="results" aria-live="polite" aria-busy={isLoading}>
        <h2>ผลการค้นหา</h2>
        {error && <p className="feedback error-message" role="alert">{error}</p>}
        {!error && message && <p className="feedback empty-message">{message}</p>}
        {!error &&
          results.map((book) => (
            <article className="book-card" key={book.book_id}>
              <h3>
                <a href={`/books/${encodeURIComponent(book.book_id)}`}>
                  {book.title}
                </a>
              </h3>
              <p>
                <strong>ผู้แต่ง:</strong> {book.authors.join(", ")}
              </p>
              <p>
                <strong>ISBN:</strong> {book.isbn}
              </p>
              <p>
                <strong>รหัสประจำเล่ม:</strong>{" "}
                {book.item_identifiers.join(", ")}
              </p>
            </article>
          ))}
      </section>
    </main>
  );
}
