import { useState } from "react";

export default function ForgotPasswordPage() {
  const [payload, setPayload] = useState({
    student_id: "",
    national_id: "",
    phone: "",
    date_of_birth: "",
  });
  const [newPassword, setNewPassword] = useState("");
  const [verified, setVerified] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function updateField(event) {
    setPayload((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function verifyIdentity(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    const response = await fetch("/api/auth/password-reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok || !result.success || !result.can_reset) {
      setError(result.message || "ข้อมูลยืนยันตัวตนไม่ถูกต้อง");
      return;
    }
    setVerified(true);
  }

  async function submitReset(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    const response = await fetch("/api/auth/password-reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, new_password: newPassword }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      setError(result.message || "ไม่สามารถตั้งรหัสผ่านใหม่ได้");
      return;
    }
    setMessage(result.message);
  }

  return (
    <main className="page-shell login-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>ลืมรหัสผ่าน</h1>
      </header>
      {!verified ? (
        <form className="search-panel login-form" onSubmit={verifyIdentity}>
          <label htmlFor="reset-student-id">รหัสนักศึกษา (กรณีนักศึกษา)</label>
          <input id="reset-student-id" name="student_id" value={payload.student_id} onChange={updateField} />
          <label htmlFor="reset-national-id">เลขบัตรประชาชน</label>
          <input id="reset-national-id" name="national_id" value={payload.national_id} onChange={updateField} required />
          <label htmlFor="reset-phone">เบอร์โทรศัพท์</label>
          <input id="reset-phone" name="phone" value={payload.phone} onChange={updateField} required />
          <label htmlFor="reset-birth-date">วัน/เดือน/ปีเกิด</label>
          <input id="reset-birth-date" name="date_of_birth" type="date" value={payload.date_of_birth} onChange={updateField} required />
          {error && <p className="feedback error-message" role="alert">{error}</p>}
          <button type="submit">ยืนยันตัวตน</button>
        </form>
      ) : (
        <form className="search-panel login-form" onSubmit={submitReset}>
          <label htmlFor="reset-password">รหัสผ่านใหม่</label>
          <input id="reset-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={5} required />
          {error && <p className="feedback error-message" role="alert">{error}</p>}
          {message && <p className="feedback" role="status">{message}</p>}
          <button type="submit">ตั้งรหัสผ่านใหม่</button>
        </form>
      )}
    </main>
  );
}
