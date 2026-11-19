import { useEffect, useState } from "react";

const COPY_STATUSES = [
  "Available",
  "Lost",
  "Damaged",
  "อยู่ระหว่างซ่อม",
];

function emptyForm() {
  return {
    title: "",
    authors: "",
    isbn: "",
    publisher: "",
    publication_year: "",
    keywords: [],
    categories: [],
    call_number: "",
    shelf: "",
    zone: "",
    copy_count: 1,
  };
}

function responseMessage(data, fallback) {
  return typeof data?.message === "string" ? data.message : fallback;
}

export default function BookManagementPage() {
  const [query, setQuery] = useState("");
  const [books, setBooks] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState("");
  const [existingCopies, setExistingCopies] = useState([]);
  const [copyIdentifiers, setCopyIdentifiers] = useState([""]);
  const [statusDrafts, setStatusDrafts] = useState({});
  const [fieldErrors, setFieldErrors] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [lookupMessage, setLookupMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function loadBooks(search = query) {
    const params = new URLSearchParams();
    if (search.trim()) params.set("query", search.trim());
    const response = await fetch(`/api/manage/books?${params.toString()}`, {
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(responseMessage(data, "ไม่สามารถค้นหาข้อมูลหนังสือได้"));
    }
    setBooks(data.results);
  }

  useEffect(() => {
    loadBooks().catch((requestError) => {
      console.error("Book management list failed", requestError);
      setError(requestError.message);
    });
  }, []);

  function setValue(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => ({ ...current, [field]: "" }));
    if (field === "isbn") setLookupMessage("");
  }

  async function selectBook(bookId) {
    setIsLoading(true);
    setError("");
    setMessage("");
    setFieldErrors({});
    try {
      const response = await fetch(
        `/api/manage/books/${encodeURIComponent(bookId)}`,
        { cache: "no-store" },
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(responseMessage(data, "ไม่สามารถเปิดข้อมูลหนังสือได้"));
      }
      setEditingId(data.book_id);
      setExistingCopies(data.copies);
      setCopyIdentifiers([]);
      setStatusDrafts({});
      setForm({
        title: data.title,
        authors: data.authors.join("\n"),
        isbn: data.isbn,
        publisher: data.publisher || "",
        publication_year: data.publication_year ?? "",
        keywords: data.keywords || [],
        categories: data.categories,
        call_number: data.call_number,
        shelf: data.shelf,
        zone: data.zone,
        copy_count: data.copy_count,
      });
    } catch (requestError) {
      console.error("Book management detail failed", requestError);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }

  function startNewBook() {
    setEditingId("");
    setExistingCopies([]);
    setCopyIdentifiers([""]);
    setStatusDrafts({});
    setForm(emptyForm());
    setFieldErrors({});
    setMessage("");
    setError("");
  }

  async function submitSearch(event) {
    event.preventDefault();
    setIsLoading(true);
    setError("");
    try {
      await loadBooks(query);
    } catch (requestError) {
      console.error("Book management search failed", requestError);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }

  async function lookupISBN() {
    setLookupMessage("");
    setError("");
    try {
      const params = new URLSearchParams({ isbn: form.isbn });
      const response = await fetch(`/api/manage/isbn-metadata?${params}`);
      const data = await response.json();
      if (!response.ok) {
        setLookupMessage(responseMessage(data, "ไม่พบข้อมูล กรุณากรอกข้อมูลเอง"));
        return;
      }
      setForm((current) => ({
        ...current,
        title: data.title,
        authors: data.authors.join("\n"),
      }));
      setFieldErrors((current) => ({ ...current, title: "", authors: "" }));
      setLookupMessage("เติมชื่อหนังสือและผู้แต่งแล้ว โปรดตรวจสอบก่อนบันทึก");
    } catch (requestError) {
      console.error("ISBN lookup failed", requestError);
      setLookupMessage("ไม่สามารถค้นข้อมูล ISBN ได้ กรุณากรอกข้อมูลเอง");
    }
  }

  function adjustCopyCount(value) {
    const count = value === "" ? "" : Number(value);
    setForm((current) => ({ ...current, copy_count: count }));
    setFieldErrors((current) => ({ ...current, copy_count: "" }));
    const additionalCount =
      count === "" ? 0 : Math.max(0, count - (editingId ? existingCopies.length : 0));
    setCopyIdentifiers((current) =>
      Array.from({ length: additionalCount }, (_, index) => current[index] || ""),
    );
  }

  function updateCopyIdentifier(index, value) {
    setCopyIdentifiers((current) =>
      current.map((identifier, itemIndex) =>
        itemIndex === index ? value : identifier,
      ),
    );
    setFieldErrors((current) => ({
      ...current,
      [`copies.${index}`]: "",
      copies: "",
    }));
  }

  function updateCategory(index, field, value) {
    setForm((current) => ({
      ...current,
      categories: current.categories.map((category, itemIndex) =>
        itemIndex === index ? { ...category, [field]: value } : category,
      ),
    }));
    setFieldErrors((current) => ({
      ...current,
      [`categories.${index}`]: "",
    }));
  }

  async function saveBook(event) {
    event.preventDefault();
    setIsLoading(true);
    setError("");
    setMessage("");
    setFieldErrors({});
    const payload = {
      ...form,
      authors: form.authors.split("\n").map((author) => author.trim()),
      publication_year: form.publication_year === "" ? null : Number(form.publication_year),
      copy_count: form.copy_count === "" ? null : Number(form.copy_count),
      copies: copyIdentifiers,
    };
    try {
      const response = await fetch(
        editingId
          ? `/api/manage/books/${encodeURIComponent(editingId)}`
          : "/api/manage/books",
        {
          method: editingId ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      const data = await response.json();
      if (!response.ok) {
        setFieldErrors(data.field_errors || {});
        setError(responseMessage(data, "บันทึกข้อมูลไม่สำเร็จ"));
        return;
      }
      setMessage(data.message);
      setEditingId(data.book.book_id);
      setExistingCopies(data.book.copies);
      setCopyIdentifiers([]);
      setForm((current) => ({
        ...current,
        copy_count: data.book.copy_count,
      }));
      await loadBooks();
    } catch (requestError) {
      console.error("Book management save failed", requestError);
      setError("ไม่สามารถบันทึกข้อมูลหนังสือได้ กรุณาลองใหม่");
    } finally {
      setIsLoading(false);
    }
  }

  async function changeCopyStatus(itemIdentifier, status) {
    setError("");
    setMessage("");
    try {
      const response = await fetch(
        `/api/manage/copies/${encodeURIComponent(itemIdentifier)}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        },
      );
      const data = await response.json();
      if (!response.ok) {
        setStatusDrafts((current) => ({ ...current, [itemIdentifier]: "" }));
        setError(responseMessage(data, "ไม่สามารถเปลี่ยนสถานะ Copy ได้"));
        return;
      }
      if (editingId) await selectBook(editingId);
      setMessage("เปลี่ยนสถานะ Copy แล้ว");
    } catch (requestError) {
      console.error("Copy status update failed", requestError);
      setStatusDrafts((current) => ({ ...current, [itemIdentifier]: "" }));
      setError("ไม่สามารถเปลี่ยนสถานะ Copy ได้ กรุณาลองใหม่");
    }
  }

  const additionalCopies = Math.max(
    0,
    Number(form.copy_count || 0) - (editingId ? existingCopies.length : 0),
  );

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">จัดการ Catalog และ Copy (FR-จัดการข้อมูลหนังสือ-01 ถึง FR-จัดการข้อมูลหนังสือ-06)</p>
        <h1>จัดการข้อมูลหนังสือ</h1>
        <a className="feature-link" href="/">กลับไปหน้าค้นหาหนังสือ</a>
        <a className="feature-link" href="/login">เข้าสู่ระบบ</a>
      </header>

      <section className="book-management-layout">
        <aside className="search-panel book-management-list">
          <h2>ค้นหาหนังสือเดิม</h2>
          <form onSubmit={submitSearch}>
            <label htmlFor="manage-book-query">คำค้น</label>
            <div className="search-entry">
              <input
                id="manage-book-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <button type="submit" disabled={isLoading}>ค้นหา</button>
            </div>
          </form>
          <button type="button" className="secondary-button" onClick={startNewBook}>
            เพิ่มหนังสือใหม่
          </button>
          <ul className="book-management-results">
            {books.map((book) => (
              <li key={book.book_id}>
                <button
                  type="button"
                  className="book-management-result"
                  onClick={() => selectBook(book.book_id)}
                >
                  <strong>{book.title}</strong>
                  <span>{book.authors.join(", ")}</span>
                  <small>ISBN {book.isbn}</small>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="search-panel book-management-editor">
          <h2>{editingId ? "แก้ไขข้อมูลหนังสือ" : "เพิ่มข้อมูลหนังสือ"}</h2>
          {error && <p className="form-error" role="alert">{error}</p>}
          {message && <p className="form-success" role="status">{message}</p>}
          <form className="book-management-form" onSubmit={saveBook}>
            <label htmlFor="book-title">ชื่อหนังสือ <span>(บังคับ)</span></label>
            <input id="book-title" value={form.title} onChange={(event) => setValue("title", event.target.value)} required aria-describedby="error-title" />
            {fieldErrors.title && <small id="error-title" className="field-error">{fieldErrors.title}</small>}

            <label htmlFor="book-authors">ผู้แต่ง <span>(บังคับ; หนึ่งคนต่อหนึ่งบรรทัด)</span></label>
            <textarea id="book-authors" value={form.authors} onChange={(event) => setValue("authors", event.target.value)} required aria-describedby="error-authors" />
            {fieldErrors.authors && <small id="error-authors" className="field-error">{fieldErrors.authors}</small>}

            <label htmlFor="book-isbn">ISBN <span>(บังคับ)</span></label>
            <div className="search-entry">
              <input id="book-isbn" value={form.isbn} onChange={(event) => setValue("isbn", event.target.value)} required aria-describedby="error-isbn" />
              <button type="button" className="secondary-button" onClick={lookupISBN} disabled={!form.isbn.trim()}>ค้นข้อมูล ISBN</button>
            </div>
            {fieldErrors.isbn && <small id="error-isbn" className="field-error">{fieldErrors.isbn}</small>}
            {lookupMessage && <small className="form-hint" role="status">{lookupMessage}</small>}

            <label htmlFor="book-publisher">สำนักพิมพ์</label>
            <input id="book-publisher" value={form.publisher} onChange={(event) => setValue("publisher", event.target.value)} />

            <label htmlFor="book-year">ปีพิมพ์</label>
            <input id="book-year" type="number" value={form.publication_year} onChange={(event) => setValue("publication_year", event.target.value)} />

            <fieldset className="book-management-categories">
              <legend>หมวดหมู่</legend>
              {form.categories.map((category, index) => (
                <div className="category-editor-row" key={`category-${index}`}>
                  <label htmlFor={`category-code-${index}`}>รหัสหมวดหมู่ {index + 1}</label>
                  <input id={`category-code-${index}`} value={category.code} onChange={(event) => updateCategory(index, "code", event.target.value)} />
                  <label htmlFor={`category-label-${index}`}>ชื่อหมวดหมู่ {index + 1}</label>
                  <input id={`category-label-${index}`} value={category.label} onChange={(event) => updateCategory(index, "label", event.target.value)} />
                  {fieldErrors[`categories.${index}`] && <small className="field-error">{fieldErrors[`categories.${index}`]}</small>}
                  <button type="button" className="remove-button" onClick={() => setForm((current) => ({ ...current, categories: current.categories.filter((_, itemIndex) => itemIndex !== index) }))}>ลบหมวดหมู่</button>
                </div>
              ))}
              <button type="button" className="secondary-button" onClick={() => setForm((current) => ({ ...current, categories: [...current.categories, { code: "", label: "" }] }))}>เพิ่มหมวดหมู่</button>
            </fieldset>

            <label htmlFor="book-call-number">เลขเรียกหนังสือ <span>(บังคับ)</span></label>
            <input id="book-call-number" value={form.call_number} onChange={(event) => setValue("call_number", event.target.value)} required aria-describedby="error-call-number" />
            {fieldErrors.call_number && <small id="error-call-number" className="field-error">{fieldErrors.call_number}</small>}

            <label htmlFor="book-shelf">ชั้น</label>
            <input id="book-shelf" value={form.shelf} onChange={(event) => setValue("shelf", event.target.value)} />
            <label htmlFor="book-zone">โซน</label>
            <input id="book-zone" value={form.zone} onChange={(event) => setValue("zone", event.target.value)} />

            <label htmlFor="book-copy-count">จำนวน Copy <span>(เพิ่มได้เท่านั้น)</span></label>
            <input id="book-copy-count" type="number" min="0" value={form.copy_count} onChange={(event) => adjustCopyCount(event.target.value)} aria-describedby="error-copy-count" />
            {fieldErrors.copy_count && <small id="error-copy-count" className="field-error">{fieldErrors.copy_count}</small>}

            {editingId && existingCopies.length > 0 && (
              <div className="existing-copies">
                <h3>Copy เดิม (แก้ไขหรือลบไม่ได้)</h3>
                <ul>
                  {existingCopies.map((copy) => {
                    const permittedStatuses =
                      copy.status === "Available"
                        ? COPY_STATUSES.slice(1)
                        : ["Lost", "Damaged", "อยู่ระหว่างซ่อม"].includes(copy.status)
                          ? ["Available", ...COPY_STATUSES.slice(1).filter((status) => status !== copy.status)]
                          : [];
                    return (
                      <li key={copy.item_identifier}>
                        <span>{copy.item_identifier} — {copy.status}</span>
                        {permittedStatuses.length > 0 && (
                          <select
                            aria-label={`สถานะใหม่ของ ${copy.item_identifier}`}
                            value={statusDrafts[copy.item_identifier] || ""}
                            onChange={(event) => {
                              const status = event.target.value;
                              setStatusDrafts((current) => ({ ...current, [copy.item_identifier]: status }));
                              if (status) changeCopyStatus(copy.item_identifier, status);
                            }}
                          >
                            <option value="">เปลี่ยนสถานะ</option>
                            {permittedStatuses.map((status) => <option key={status} value={status}>{status}</option>)}
                          </select>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {Array.from({ length: additionalCopies }, (_, index) => (
              <div className="book-copy-field" key={`copy-${index}`}>
                <label htmlFor={`copy-id-${index}`}>รหัสประจำเล่ม {index + 1} <span>(บังคับ)</span></label>
                <input
                  id={`copy-id-${index}`}
                  value={copyIdentifiers[index] || ""}
                  onChange={(event) => updateCopyIdentifier(index, event.target.value)}
                  required
                  aria-describedby={`error-copy-${index}`}
                />
                {(fieldErrors[`copies.${index}`] || fieldErrors.copies) && (
                  <small id={`error-copy-${index}`} className="field-error">
                    {fieldErrors[`copies.${index}`] || fieldErrors.copies}
                  </small>
                )}
              </div>
            ))}

            <button type="submit" disabled={isLoading}>
              {isLoading ? "กำลังบันทึก..." : "บันทึกข้อมูลหนังสือ"}
            </button>
          </form>

          {message && editingId && existingCopies.length > 0 && (
            <section className="book-readback" aria-label="ข้อมูลหนังสือที่บันทึกแล้ว">
              <h3>ข้อมูลที่อ่านกลับจากระบบ</h3>
              <p><strong>{form.title}</strong></p>
              <p>{form.authors.split("\n").filter(Boolean).join(", ")} · ISBN {form.isbn}</p>
              <p>หมวดหมู่: {form.categories.map((category) => `${category.code} ${category.label}`).join(", ") || "—"}</p>
              <p>เลขเรียก: {form.call_number} · ตำแหน่ง: {form.shelf} / {form.zone}</p>
              <ul>{existingCopies.map((copy) => <li key={copy.item_identifier}>{copy.item_identifier} — {copy.status}</li>)}</ul>
              <a className="feature-link" href={`/books/${encodeURIComponent(editingId)}`}>เปิดหน้ารายละเอียดหนังสือ</a>
            </section>
          )}
        </section>
      </section>
    </main>
  );
}
