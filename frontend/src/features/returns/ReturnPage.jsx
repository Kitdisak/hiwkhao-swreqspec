import { useState } from "react";

const LOOKUP_ENDPOINT = "/api/returns/lookup";
const RETURN_ENDPOINT = "/api/returns";

function loginForReturn() {
  window.location.assign(
    `/login?returnTo=${encodeURIComponent("/returns")}`,
  );
}

async function readResponse(response) {
  const data = await response.json();
  if (response.status === 401) {
    loginForReturn();
    return null;
  }
  if (!response.ok) {
    throw new Error(data.message || `Request failed with status ${response.status}`);
  }
  return data;
}

// SPEC-012: ค้นหาและยืนยันการคืนตาม FR-01 ถึง FR-06.
export default function ReturnPage() {
  const [itemIdentifier, setItemIdentifier] = useState("");
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  async function lookupReturn(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setPreview(null);
    setResult(null);
    setIsLookingUp(true);

    try {
      const params = new URLSearchParams({
        item_identifier: itemIdentifier.trim(),
      });
      const response = await fetch(`${LOOKUP_ENDPOINT}?${params}`, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await readResponse(response);
      if (!data) return;
      if (!data.success || typeof data.fine_amount !== "string") {
        throw new Error("Return lookup response has an invalid shape");
      }
      setPreview(data);
    } catch (requestError) {
      console.error("Return lookup failed", requestError);
      setError(requestError.message || "ไม่พบรายการยืม กรุณาตรวจสอบข้อมูล");
    } finally {
      setIsLookingUp(false);
    }
  }

  async function confirmReturn() {
    if (!preview || isConfirming) return;
    setError("");
    setNotice("");
    setIsConfirming(true);

    try {
      const response = await fetch(RETURN_ENDPOINT, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_identifier: preview.item_identifier }),
      });
      const data = await readResponse(response);
      if (!data) return;
      if (!data.success || typeof data.fine_amount !== "string") {
        throw new Error("Return confirmation response has an invalid shape");
      }
      setResult(data);
      setPreview(null);
      setNotice("บันทึกการคืนสำเร็จ");
    } catch (requestError) {
      console.error("Return confirmation failed", requestError);
      setError(requestError.message || "ไม่สามารถบันทึกการคืนได้ กรุณาลองใหม่");
    } finally {
      setIsConfirming(false);
    }
  }

  function startNextReturn() {
    setItemIdentifier("");
    setPreview(null);
    setResult(null);
    setError("");
    setNotice("");
  }

  const record = preview || result;

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>รับคืนหนังสือและคำนวณค่าปรับ</h1>
        <p>สแกนรหัสประจำเล่ม ตรวจสอบวันกำหนดคืน และยืนยันการรับคืน</p>
        <a className="feature-link" href="/">
          กลับไปหน้าหลัก
        </a>
      </header>

      <form className="search-panel loan-scan-form" onSubmit={lookupReturn}>
        <label htmlFor="return-copy-identifier">รหัสประจำเล่ม</label>
        <div className="search-entry">
          <input
            id="return-copy-identifier"
            autoComplete="off"
            value={itemIdentifier}
            onChange={(event) => setItemIdentifier(event.target.value)}
            required
            disabled={isLookingUp || isConfirming}
          />
          <button type="submit" disabled={isLookingUp || isConfirming}>
            {isLookingUp ? "กำลังค้นหา..." : "ค้นหารายการยืม"}
          </button>
        </div>
      </form>

      {error && (
        <p className="feedback error-message" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="feedback" role="status">
          {notice}
        </p>
      )}

      {record && (
        <section className="search-panel loan-panel" aria-label="ผลการรับคืน">
          <h2>{record.book_title}</h2>
          <p>
            <strong>รหัสประจำเล่ม:</strong> {record.item_identifier}
          </p>
          <p>
            <strong>วันกำหนดคืน:</strong> {record.due_date || record.returned_date}
          </p>
          <p>
            <strong>วันที่รับคืน:</strong> {record.returned_date}
          </p>
          <p>
            <strong>จำนวนวันที่เกิน:</strong> {record.overdue_days} วัน
          </p>
          <p>
            <strong>ค่าปรับ:</strong> {record.fine_amount} บาท
          </p>
          {result?.reservation && (
            <p>
              <strong>รายการจอง:</strong> พร้อมรับถึง {result.reservation.pickup_deadline}
            </p>
          )}

          {preview && (
            <button type="button" onClick={confirmReturn} disabled={isConfirming}>
              {isConfirming ? "กำลังบันทึก..." : "ยืนยันรับคืน"}
            </button>
          )}
          {result && (
            <button type="button" onClick={startNextReturn}>
              สแกนเล่มถัดไป
            </button>
          )}
        </section>
      )}
    </main>
  );
}
