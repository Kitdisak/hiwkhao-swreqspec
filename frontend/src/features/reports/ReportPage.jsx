import { useEffect, useState } from "react";

const REPORT_TYPES = [
  { value: "loans", label: "รายงานการยืม" },
  { value: "popular_books", label: "หนังสือยอดนิยม" },
  { value: "fines", label: "รายงานค่าปรับ" },
  { value: "room_usage", label: "รายงานการใช้ห้อง" },
];

function todayLocal() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Bangkok",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export default function ReportPage() {
  const [session, setSession] = useState(null);
  const [reportType, setReportType] = useState("loans");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState(todayLocal());
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/auth/session", { credentials: "same-origin" })
      .then((response) => response.json())
      .then((data) => {
        if (!data.authenticated) {
          window.location.href = "/login";
          return;
        }
        setSession(data);
      })
      .catch(() => setSession({ authenticated: false }));
  }, []);

  async function generateReport(event) {
    event?.preventDefault();
    setError("");
    setResult(null);
    setLoading(true);
    const params = new URLSearchParams({
      type: reportType,
      startDate,
      endDate,
    });
    try {
      const response = await fetch(`/api/reports?${params}`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      const data = await response.json();
      if (response.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!response.ok) {
        setError(data.message || "ช่วงวันที่ไม่ถูกต้อง");
        return;
      }
      setResult(data);
    } catch {
      setError("ไม่สามารถสร้างรายงานได้");
    } finally {
      setLoading(false);
    }
  }

  async function exportCsv() {
    if (!result?.has_data) return;
    const params = new URLSearchParams({
      type: reportType,
      startDate,
      endDate,
    });
    const response = await fetch(`/api/reports/export?${params}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!response.ok) {
      const data = await response.json();
      setError(data.message || "ไม่สามารถส่งออกรายงานได้");
      return;
    }
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await response.json();
      setError(data.message || "ไม่พบข้อมูลในช่วงเวลาที่เลือก");
      setResult((current) => ({ ...current, has_data: false }));
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    link.download = match?.[1] || `report-${reportType}-${startDate}-${endDate}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  const canView =
    session?.authenticated &&
    (session.role === "admin" ||
      session.role === "librarian" ||
      session.permissions?.includes("view_reports"));

  return (
    <main className="page-shell report-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>รายงานและสถิติ</h1>
        <p>เลือกช่วงเวลาและประเภทรายงาน</p>
        <a className="feature-link" href="/">ค้นหาหนังสือ</a>
      </header>

      {session && !canView ? (
        <section className="search-panel">
          <p className="error-message">
            {session.authenticated ? "คุณไม่มีสิทธิ์ดูรายงาน" : "กรุณาเข้าสู่ระบบ"}
          </p>
        </section>
      ) : (
        session && (
          <section className="search-panel report-panel">
            <form className="report-form" onSubmit={generateReport}>
              <label>
                ประเภทรายงาน
                <select value={reportType} onChange={(event) => setReportType(event.target.value)}>
                  {REPORT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </label>
              <label>
                วันเริ่มต้น
                <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
              </label>
              <label>
                วันสิ้นสุด
                <input type="date" value={endDate} max={todayLocal()} onChange={(event) => setEndDate(event.target.value)} />
              </label>
              <button type="submit" disabled={loading}>
                {loading ? "กำลังประมวลผล..." : "สร้างรายงาน"}
              </button>
            </form>

            {error && <p className="error-message">{error}</p>}
            {result && (
              <section className="report-result">
                {!result.has_data ? (
                  <p className="report-empty">{result.message || "ไม่พบข้อมูลในช่วงเวลาที่เลือก"}</p>
                ) : (
                  <ReportData reportType={reportType} data={result.data} />
                )}
                <button type="button" className="export-button" onClick={exportCsv} disabled={!result.has_data}>
                  ส่งออก CSV
                </button>
              </section>
            )}
          </section>
        )
      )}
    </main>
  );
}

function ReportData({ reportType, data }) {
  if (reportType === "loans") {
    return (
      <article className="report-card">
        <h2>จำนวนรายการยืม</h2>
        <strong className="report-metric">{data.count}</strong>
      </article>
    );
  }
  if (reportType === "popular_books") {
    return (
      <article className="report-card">
        <h2>หนังสือยอดนิยม 10 อันดับ</h2>
        <ol className="report-list">
          {data.rows.map((row) => (
            <li key={row.title_id}>
              <span>{row.title_name}</span>
              <strong>{row.borrow_count}</strong>
            </li>
          ))}
        </ol>
      </article>
    );
  }
  if (reportType === "fines") {
    return (
      <article className="report-card report-fine-grid">
        <div><span>ค่าปรับที่เกิดขึ้นทั้งหมด</span><strong>{data.total_all} บาท</strong></div>
        <div><span>ชำระแล้ว</span><strong>{data.total_paid} บาท</strong></div>
        <div><span>ยังไม่ชำระ</span><strong>{data.total_outstanding} บาท</strong></div>
      </article>
    );
  }
  return (
    <article className="report-card">
      <h2>รายงานการใช้ห้อง</h2>
      <div className="report-table-wrap">
        <table className="report-table">
          <thead><tr><th>รหัสห้อง</th><th>จำนวนรายการจอง</th><th>จำนวนชั่วโมงที่ถูกจอง</th></tr></thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.room_id}><td>{row.room_id}</td><td>{row.booking_count}</td><td>{row.booked_hours}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}
