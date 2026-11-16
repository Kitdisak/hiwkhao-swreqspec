import { useEffect, useState } from "react";

const FINES_ENDPOINT = "/api/me/fines";
const PAYMENT_ENDPOINT = "/api/payments";

function formatAmount(amount) {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
  }).format(Number(amount));
}

async function readJson(response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "ไม่สามารถดำเนินการได้");
  }
  return data;
}

export default function FinePaymentPage() {
  const [fines, setFines] = useState([]);
  const [total, setTotal] = useState("0.00");
  const [channel, setChannel] = useState("");
  const [paymentRequest, setPaymentRequest] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function loadFines() {
    setIsLoading(true);
    setError("");
    try {
      const data = await readJson(await fetch(FINES_ENDPOINT));
      setFines(data.fines);
      setTotal(data.total_amount);
      setPaymentRequest(data.pending_payment_request);
    } catch (requestError) {
      console.error("Fine list request failed", requestError);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadFines();
  }, []);

  async function startPayment(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setIsSubmitting(true);
    try {
      const data = await readJson(
        await fetch(PAYMENT_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channel }),
        }),
      );
      setPaymentRequest(data.payment_request);
      setNotice(data.message);
    } catch (requestError) {
      console.error("Payment request failed", requestError);
      setError(requestError.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function checkStatus() {
    if (!paymentRequest?.payment_ref) return;
    setError("");
    setNotice("");
    try {
      const data = await readJson(
        await fetch(
          `${PAYMENT_ENDPOINT}/${encodeURIComponent(paymentRequest.payment_ref)}/status-check`,
          { method: "POST" },
        ),
      );
      setPaymentRequest(data.payment_request);
      setNotice(`สถานะคำขอ: ${data.payment_request.status}`);
      if (data.payment_request.status === "succeeded") {
        await loadFines();
      }
    } catch (requestError) {
      console.error("Payment status check failed", requestError);
      setError(requestError.message);
    }
  }

  const canStartPayment =
    fines.length > 0 &&
    channel.trim().length > 0 &&
    !isSubmitting &&
    paymentRequest?.status !== "pending";

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">สมาชิก</p>
        <h1>ชำระค่าปรับออนไลน์</h1>
        <p>ตรวจสอบรายการค่าปรับและยอดรวมก่อนยืนยันชำระ</p>
        <a className="back-link" href="/">กลับไปค้นหาหนังสือ</a>
      </header>

      <section className="search-panel" aria-busy={isLoading}>
        <h2>รายการค่าปรับค้างชำระ</h2>
        {isLoading && <p role="status">กำลังโหลดรายการค่าปรับ...</p>}
        {!isLoading && error && fines.length === 0 && (
          <p className="feedback error-message" role="alert">{error}</p>
        )}
        {!isLoading && !error && fines.length === 0 && (
          <p className="feedback">ไม่มีค่าปรับค้างชำระ</p>
        )}

        {!error && fines.length > 0 && (
          <>
            <div className="fine-list">
              {fines.map((fine) => (
                <article className="fine-card" key={fine.fine_id}>
                  <h3>{fine.book_title}</h3>
                  <p><strong>วันครบกำหนด:</strong> {fine.due_date}</p>
                  <p><strong>วันที่คืน:</strong> {fine.returned_date}</p>
                  <p><strong>จำนวนวันที่เกิน:</strong> {fine.overdue_days} วัน</p>
                  <p><strong>ค่าปรับ:</strong> {formatAmount(fine.amount)}</p>
                </article>
              ))}
            </div>

            <p className="fine-total">
              <strong>ยอดรวมที่ต้องชำระ:</strong> {formatAmount(total)}
            </p>

            <form className="payment-form" onSubmit={startPayment}>
              <label htmlFor="payment-channel">ช่องทางชำระเงิน</label>
              <input
                id="payment-channel"
                value={channel}
                onChange={(event) => setChannel(event.target.value)}
                placeholder="ระบุช่องทางที่ Payment Gateway รองรับ"
                required
                disabled={paymentRequest?.status === "pending"}
              />
              <button type="submit" disabled={!canStartPayment}>
                {isSubmitting ? "กำลังส่งคำขอ..." : "ยืนยันชำระค่าปรับทั้งหมด"}
              </button>
            </form>
          </>
        )}

        {error && fines.length > 0 && (
          <p className="feedback error-message" role="alert">{error}</p>
        )}
        {notice && <p className="feedback" role="status">{notice}</p>}
        {paymentRequest?.status === "pending" && (
          <section className="payment-status" aria-label="สถานะคำขอชำระ">
            <p>คำขอ {paymentRequest.payment_ref} กำลังรอยืนยันผล</p>
            <button type="button" className="secondary-button" onClick={checkStatus}>
              ตรวจสอบสถานะ
            </button>
          </section>
        )}
      </section>
    </main>
  );
}
