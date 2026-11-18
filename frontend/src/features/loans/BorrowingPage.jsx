import { useRef, useState } from "react";

const LOOKUP_ENDPOINT = "/api/members/lookup";
const COPY_CHECK_ENDPOINT = "/api/loans/check";
const LOANS_ENDPOINT = "/api/loans";

function loginForBorrowing() {
  window.location.assign(
    `/login?returnTo=${encodeURIComponent("/loans/new")}`,
  );
}

async function readResponse(response) {
  const data = await response.json();
  if (response.status === 401) {
    loginForBorrowing();
    return null;
  }
  if (!response.ok) {
    throw new Error(data.message || `Request failed with status ${response.status}`);
  }
  return data;
}

// SPEC-011: บันทึกการยืมและแสดงผลรายเล่มตาม FR-01 ถึง FR-06.
export default function BorrowingPage() {
  const [memberIdentifier, setMemberIdentifier] = useState("");
  const [member, setMember] = useState(null);
  const [itemIdentifier, setItemIdentifier] = useState("");
  const [items, setItems] = useState([]);
  const [lookupError, setLookupError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const requestId = useRef("");

  async function lookupMember(event) {
    event.preventDefault();
    setLookupError("");
    setError("");
    setFeedback("");
    setMember(null);
    setItems([]);
    setConfirmed(false);
    requestId.current = "";
    setIsLookingUp(true);

    try {
      const params = new URLSearchParams({ identifier: memberIdentifier.trim() });
      const response = await fetch(`${LOOKUP_ENDPOINT}?${params}`, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await readResponse(response);
      if (!data) return;
      if (!data.member || typeof data.member.member_id !== "string") {
        throw new Error("Member lookup response has an invalid shape");
      }
      setMember(data.member);
    } catch (requestError) {
      console.error("Member lookup failed", requestError);
      setLookupError(
        requestError.message === "ไม่พบข้อมูลสมาชิก"
          ? requestError.message
          : "ไม่สามารถค้นหาสมาชิกได้ กรุณาลองใหม่",
      );
    } finally {
      setIsLookingUp(false);
    }
  }

  async function scanCopy(event) {
    event.preventDefault();
    const scannedIdentifier = itemIdentifier.trim();
    if (!member || !scannedIdentifier) return;

    setError("");
    setFeedback("");
    if (items.some((item) => item.item_identifier === scannedIdentifier)) {
      setFeedback("รหัสนี้อยู่ในรายการแล้ว");
      setItemIdentifier("");
      return;
    }

    setIsChecking(true);
    try {
      const response = await fetch(COPY_CHECK_ENDPOINT, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          member_identifier: memberIdentifier.trim(),
          item_identifier: scannedIdentifier,
          pending_item_identifiers: items
            .filter((item) => item.success)
            .map((item) => item.item_identifier),
        }),
      });
      const result = await readResponse(response);
      if (!result) return;
      setItems((current) => [...current, result]);
      setFeedback(result.success ? "" : result.message);
      setItemIdentifier("");
      setConfirmed(false);
      requestId.current = "";
    } catch (requestError) {
      console.error("Copy check failed", requestError);
      setError("ไม่สามารถตรวจสอบหนังสือได้ กรุณาลองใหม่");
    } finally {
      setIsChecking(false);
    }
  }

  async function confirmLoan() {
    if (!member || items.length === 0 || isConfirming) return;
    if (!requestId.current) {
      requestId.current = crypto.randomUUID();
    }
    setError("");
    setFeedback("");
    setIsConfirming(true);

    try {
      const response = await fetch(LOANS_ENDPOINT, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          member_identifier: memberIdentifier.trim(),
          item_identifiers: items.map((item) => item.item_identifier),
          request_id: requestId.current,
        }),
      });
      const result = await readResponse(response);
      if (!result) return;
      if (!Array.isArray(result.items)) {
        throw new Error("Loan response has an invalid shape");
      }
      setItems(result.items);
      setFeedback(result.message || "");
      setConfirmed(true);
    } catch (requestError) {
      console.error("Loan confirmation failed", requestError);
      setError("ไม่สามารถบันทึกการยืมได้ กรุณาลองส่งคำขอเดิมอีกครั้ง");
    } finally {
      setIsConfirming(false);
    }
  }

  function startNewLoan() {
    setMember(null);
    setMemberIdentifier("");
    setItemIdentifier("");
    setItems([]);
    setLookupError("");
    setFeedback("");
    setError("");
    setConfirmed(false);
    requestId.current = "";
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>บันทึกการยืมหนังสือ</h1>
        <p>ค้นหาสมาชิก สแกนหนังสือ และยืนยันรายการยืม</p>
        <a className="feature-link" href="/">
          กลับไปหน้าหลัก
        </a>
      </header>

      <form className="search-panel loan-form" onSubmit={lookupMember}>
        <label htmlFor="loan-member-identifier">
          รหัสนักศึกษา/บัตรนักศึกษา หรืออีเมลบุคลากร
        </label>
        <div className="search-entry">
          <input
            id="loan-member-identifier"
            autoComplete="off"
            value={memberIdentifier}
            onChange={(event) => setMemberIdentifier(event.target.value)}
            required
          />
          <button type="submit" disabled={isLookingUp}>
            {isLookingUp ? "กำลังค้นหา..." : "ค้นหาสมาชิก"}
          </button>
        </div>
        {lookupError && (
          <p className="feedback error-message" role="alert">
            {lookupError}
          </p>
        )}
      </form>

      {member && (
        <section className="search-panel loan-panel" aria-label="ข้อมูลสมาชิก">
          <h2>ข้อมูลสมาชิก</h2>
          <p>
            <strong>ชื่อ:</strong> {member.display_name}
          </p>
          <p>
            <strong>รหัสสมาชิก:</strong> {member.student_id || member.member_id}
          </p>
          <p>
            <strong>ประเภท:</strong>{" "}
            {member.member_type === "student" ? "นักศึกษา" : "บุคลากร"}
          </p>

          {!confirmed && (
            <form className="loan-scan-form" onSubmit={scanCopy}>
              <label htmlFor="loan-copy-identifier">รหัสประจำเล่ม</label>
              <div className="search-entry">
                <input
                  id="loan-copy-identifier"
                  autoComplete="off"
                  value={itemIdentifier}
                  onChange={(event) => setItemIdentifier(event.target.value)}
                  disabled={isChecking || isConfirming}
                />
                <button type="submit" disabled={isChecking || isConfirming}>
                  {isChecking ? "กำลังตรวจ..." : "สแกนหนังสือ"}
                </button>
              </div>
            </form>
          )}

          {feedback && (
            <p className="feedback" role="status">
              {feedback}
            </p>
          )}
          {error && (
            <p className="feedback error-message" role="alert">
              {error}
            </p>
          )}

          {items.length > 0 && (
            <section className="loan-items" aria-label="รายการหนังสือ">
              <h3>{confirmed ? "ผลการยืนยัน" : "หนังสือที่สแกน"}</h3>
              <ol>
                {items.map((item, index) => (
                  <li key={`${item.item_identifier}-${index}`}>
                    <strong>{item.item_identifier}</strong>
                    <span>{item.message}</span>
                    {item.due_date && <span>วันคืน: {item.due_date}</span>}
                  </li>
                ))}
              </ol>
            </section>
          )}

          {!confirmed && items.length > 0 && (
            <button
              type="button"
              onClick={confirmLoan}
              disabled={isConfirming || isChecking}
            >
              {isConfirming ? "กำลังบันทึก..." : "ยืนยันการยืม"}
            </button>
          )}
          {confirmed && (
            <button type="button" onClick={startNewLoan}>
              เริ่มรายการใหม่
            </button>
          )}
        </section>
      )}
    </main>
  );
}
