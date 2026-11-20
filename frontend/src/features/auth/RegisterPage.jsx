import { useState } from "react";

export default function RegisterPage() {
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    date_of_birth: "",
    national_id: "",
    phone: "",
    email: "",
    student_id: "",
    password: "",
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  function updateField(event) {
    setForm((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }));
  }

  async function submitRegistration(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setIsLoading(true);
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(form),
      });
      const result = await response.json();
      if (!response.ok || !result.success) {
        setError(result.message || "ไม่สามารถสมัครสมาชิกได้");
        return;
      }
      setMessage(result.message);
    } catch (requestError) {
      console.error("Registration request failed", requestError);
      setError("ไม่สามารถสมัครสมาชิกได้ กรุณาลองใหม่");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell login-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>สมัครสมาชิก</h1>
      </header>
      <form className="search-panel login-form" onSubmit={submitRegistration}>
        <label htmlFor="register-first-name">ชื่อ</label>
        <input id="register-first-name" name="first_name" value={form.first_name} onChange={updateField} required />
        <label htmlFor="register-last-name">นามสกุล</label>
        <input id="register-last-name" name="last_name" value={form.last_name} onChange={updateField} required />
        <label htmlFor="register-birth-date">วัน/เดือน/ปีเกิด</label>
        <input id="register-birth-date" name="date_of_birth" type="date" value={form.date_of_birth} onChange={updateField} required />
        <label htmlFor="register-national-id">เลขบัตรประชาชน</label>
        <input id="register-national-id" name="national_id" value={form.national_id} onChange={updateField} required />
        <label htmlFor="register-phone">เบอร์โทรศัพท์</label>
        <input id="register-phone" name="phone" value={form.phone} onChange={updateField} required />
        <label htmlFor="register-email">อีเมล</label>
        <input id="register-email" name="email" type="email" value={form.email} onChange={updateField} />
        <label htmlFor="register-student-id">รหัสนักศึกษา (ถ้ามี)</label>
        <input id="register-student-id" name="student_id" value={form.student_id} onChange={updateField} />
        <label htmlFor="register-password">รหัสผ่าน</label>
        <input id="register-password" name="password" type="password" value={form.password} onChange={updateField} minLength={5} required />
        {error && <p className="feedback error-message" role="alert">{error}</p>}
        {message && <p className="feedback" role="status">{message}</p>}
        <button type="submit" disabled={isLoading}>
          {isLoading ? "กำลังสมัครสมาชิก..." : "สมัครสมาชิก"}
        </button>
      </form>
    </main>
  );
}
