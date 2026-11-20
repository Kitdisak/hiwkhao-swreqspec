import { useState } from "react";

// จำกัด return path ให้กลับสู่ขั้นตอนจองเดิมหลังเข้าสู่ระบบ (ASM-06, AC-จองห้องอ่านหนังสือ-/-ห้องประชุม-01).
function getReturnTo() {
  const candidate = new URLSearchParams(window.location.search).get("returnTo");
  const isRoomReservation =
    candidate === "/rooms/reservations/new" ||
    candidate?.startsWith("/rooms/reservations/new?");
  const isMyReservations = candidate === "/my-reservations";
  const isLoanRecording = candidate === "/loans/new";
  if (
    !candidate ||
    candidate.startsWith("//") ||
    (!isRoomReservation && !isMyReservations && !isLoanRecording)
  ) {
    return "/";
  }

  const destination = new URL(candidate, window.location.origin);
  if (
    destination.origin !== window.location.origin ||
    (isRoomReservation &&
      destination.pathname !== "/rooms/reservations/new") ||
    (isMyReservations && destination.pathname !== "/my-reservations") ||
    (isLoanRecording && destination.pathname !== "/loans/new")
  ) {
    return "/";
  }

  return `${destination.pathname}${destination.search}`;
}

export default function LoginPage() {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const returnTo = getReturnTo();
  const bookingLogin = returnTo.startsWith("/rooms/reservations/new");
  const reservationTrackingLogin = returnTo === "/my-reservations";
  const loanRecordingLogin = returnTo === "/loans/new";

  async function submitLogin(event) {
    event.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ username: identifier, password }),
      });
      const result = await response.json();

      if (!response.ok || !result.success) {
        setError(result.message || "ไม่สามารถเข้าสู่ระบบได้ กรุณาลองใหม่");
        return;
      }

      window.location.assign(returnTo);
    } catch (requestError) {
      console.error("Login request failed", requestError);
      setError("ไม่สามารถเข้าสู่ระบบได้ กรุณาลองใหม่");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell login-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>เข้าสู่ระบบ</h1>
      </header>

      {bookingLogin && (
        <p className="feedback" role="status">
          กรุณาเข้าสู่ระบบก่อนจองห้อง
        </p>
      )}
      {reservationTrackingLogin && (
        <p className="feedback" role="status">
          กรุณาเข้าสู่ระบบก่อนดูรายการจอง
        </p>
      )}
      {loanRecordingLogin && (
        <p className="feedback" role="status">
          กรุณาเข้าสู่ระบบด้วยบัญชีบุคลากรก่อนบันทึกการยืม
        </p>
      )}

      <form className="search-panel login-form" onSubmit={submitLogin}>
        <label htmlFor="login-identifier">
          ชื่อผู้ใช้ / อีเมล / รหัสนักศึกษา
        </label>
        <input
          id="login-identifier"
          autoComplete="username"
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          required
        />
        <label htmlFor="login-password">รหัสผ่าน</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        {error && (
          <p className="feedback error-message" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={isLoading}>
          {isLoading ? "กำลังเข้าสู่ระบบ..." : "เข้าสู่ระบบ"}
        </button>
        <p>
          <a href="/register">สมัครสมาชิก</a>
          {" | "}
          <a href="/forgot-password">ลืมรหัสผ่าน</a>
        </p>
      </form>
    </main>
  );
}