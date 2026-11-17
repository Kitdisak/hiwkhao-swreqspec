import { useState } from "react";

const CHECK_ENDPOINT = "/api/room-reservations/check";
const CREATE_ENDPOINT = "/api/room-reservations";
const OPENING_MINUTES = 8 * 60;
const CLOSING_MINUTES = 20 * 60;
const SLOT_MINUTES = 30;
const MIN_DURATION_MINUTES = 30;
const MAX_DURATION_MINUTES = 4 * 60;
const ROOM_SLOT_OPTIONS = Array.from(
  { length: (CLOSING_MINUTES - OPENING_MINUTES) / SLOT_MINUTES + 1 },
  (_, index) => {
    const totalMinutes = OPENING_MINUTES + index * SLOT_MINUTES;
    return `${String(Math.floor(totalMinutes / 60)).padStart(2, "0")}:${String(
      totalMinutes % 60,
    ).padStart(2, "0")}`;
  },
);

function getBangkokToday() {
  const dateParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Bangkok",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const parts = Object.fromEntries(
    dateParts
      .filter((part) => part.type !== "literal")
      .map(({ type, value }) => [type, value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function getReservationContext() {
  const params = new URLSearchParams(window.location.search);
  return {
    roomId: params.get("room_id") ?? "",
    roomType: params.get("room_type") ?? "",
    bookingDate: params.get("booking_date") ?? "",
    capacity: Number(params.get("capacity")),
    userCount: params.get("user_count") ?? "",
    afterLogin: params.get("after_login") === "1",
  };
}

function getReturnToAvailability(context) {
  const params = new URLSearchParams({
    date: context.bookingDate,
    room_type: context.roomType,
  });
  if (context.userCount) {
    params.set("user_count", context.userCount);
  }
  return `/rooms/availability?${params.toString()}`;
}

function timeToMinutes(value) {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

function getBangkokCurrentMinutes() {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Bangkok",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date());
  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== "literal")
      .map(({ type, value }) => [type, value]),
  );
  return (
    Number(values.hour) * 60 +
    Number(values.minute) +
    Number(values.second) / 60
  );
}

function getBookingValidationError(context, startTime, endTime, userCount) {
  const today = getBangkokToday();
  if (!context.roomId || !context.bookingDate || !context.roomType) {
    return "กรุณาเลือกห้องและวันที่จากหน้าตรวจสอบห้องว่าง";
  }
  if (context.bookingDate < today) {
    return "กรุณาเลือกวันที่ตั้งแต่วันนี้เป็นต้นไป";
  }
  if (!Number.isInteger(context.capacity) || context.capacity < 1) {
    return "ห้องนี้ไม่สามารถจองได้เนื่องจากไม่มีข้อมูลความจุ";
  }
  if (!startTime || !endTime) {
    return "กรุณาเลือกเวลาเริ่มและเวลาสิ้นสุด";
  }
  if (!/^[1-9]\d*$/.test(userCount)) {
    return "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป";
  }
  if (Number(userCount) > context.capacity) {
    return `ห้องนี้รองรับได้สูงสุด ${context.capacity} คน`;
  }

  const startMinutes = timeToMinutes(startTime);
  const endMinutes = timeToMinutes(endTime);
  if (
    startMinutes < OPENING_MINUTES ||
    startMinutes >= CLOSING_MINUTES ||
    endMinutes <= OPENING_MINUTES ||
    endMinutes > CLOSING_MINUTES ||
    startMinutes % SLOT_MINUTES !== 0 ||
    endMinutes % SLOT_MINUTES !== 0
  ) {
    return "เลือกเวลาได้ช่วงละ 30 นาที ระหว่าง 08:00–20:00";
  }
  if (startMinutes >= endMinutes) {
    return "เวลาเริ่มต้องก่อนเวลาสิ้นสุด";
  }
  const durationMinutes = endMinutes - startMinutes;
  if (durationMinutes < MIN_DURATION_MINUTES) {
    return "จองได้อย่างน้อย 30 นาที";
  }
  if (durationMinutes > MAX_DURATION_MINUTES) {
    return "จองได้ไม่เกิน 4 ชั่วโมง";
  }
  if (
    context.bookingDate === today &&
    startMinutes < getBangkokCurrentMinutes()
  ) {
    return "ไม่สามารถจองช่วงเวลาที่ผ่านไปแล้ว";
  }
  return "";
}

function isCheckResponse(data) {
  if (!data || typeof data.available !== "boolean") {
    return false;
  }
  if (data.available) {
    return Boolean(
      data.summary &&
        typeof data.summary.room_id === "string" &&
        typeof data.summary.booking_date === "string" &&
        typeof data.summary.start_time === "string" &&
        typeof data.summary.end_time === "string" &&
        Number.isInteger(data.summary.user_count),
    );
  }
  return (
    typeof data.message === "string" &&
    Array.isArray(data.available_slots) &&
    data.available_slots.every(
      (slot) =>
        slot &&
        typeof slot.start_time === "string" &&
        typeof slot.end_time === "string",
    )
  );
}

function isBookingResponse(data) {
  return Boolean(
    data &&
      data.success === true &&
      data.booking &&
      typeof data.booking.booking_id === "string" &&
      typeof data.booking.room_id === "string" &&
      typeof data.booking.booking_date === "string" &&
      typeof data.booking.start_time === "string" &&
      typeof data.booking.end_time === "string",
  );
}

// หน้าจองครอบคลุมการเลือกและตรวจเวลา การยืนยัน และทางเลือกเมื่อไม่ว่าง (FR-01 ถึง FR-05, AC-01, AC-03).
export default function ReservationPage() {
  const context = getReservationContext();
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [userCount, setUserCount] = useState(context.userCount);
  const [summary, setSummary] = useState(null);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [message, setMessage] = useState(
    context.afterLogin
      ? "เข้าสู่ระบบแล้ว กรุณาเลือกเวลาและตรวจสอบความว่างอีกครั้ง"
      : "",
  );
  const [error, setError] = useState("");
  const [booking, setBooking] = useState(null);
  const [requestId, setRequestId] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  function clearCheckResult() {
    setSummary(null);
    setMessage("");
    setError("");
    setRequestId("");
  }

  // Return to the same room and date after login, but omit the selected times (ASM-06, AC-01).
  function goToLogin() {
    const params = new URLSearchParams({
      room_id: context.roomId,
      room_type: context.roomType,
      booking_date: context.bookingDate,
      capacity: Number.isInteger(context.capacity)
        ? String(context.capacity)
        : "",
      after_login: "1",
    });
    if (userCount) {
      params.set("user_count", userCount);
    }
    const returnTo = `/rooms/reservations/new?${params.toString()}`;
    window.location.assign(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  function getPayload() {
    return {
      room_id: context.roomId,
      booking_date: context.bookingDate,
      start_time: startTime,
      end_time: endTime,
      user_count: Number(userCount),
    };
  }

  async function submitCheck(event) {
    // Validate before the availability request and never create a booking here (FR-01, FR-04, ASM-05).
    event.preventDefault();
    clearCheckResult();
    const validationMessage = getBookingValidationError(
      context,
      startTime,
      endTime,
      userCount,
    );
    if (validationMessage) {
      setError(validationMessage);
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(CHECK_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(getPayload()),
      });
      const data = await response.json();

      if (response.status === 401) {
        goToLogin();
        return;
      }
      if (!response.ok) {
        setError(data.message || "ไม่สามารถตรวจสอบช่วงเวลาได้ กรุณาลองใหม่");
        return;
      }
      if (!isCheckResponse(data)) {
        throw new Error("Room reservation check response has an invalid shape");
      }
      if (data.available) {
        setSummary(data.summary);
        setAvailableSlots([]);
        setMessage("");
      } else {
        setAvailableSlots(data.available_slots);
        setMessage(data.message);
      }
    } catch (requestError) {
      console.error("Room reservation check failed", requestError);
      setError("ไม่สามารถตรวจสอบช่วงเวลาได้ กรุณาลองใหม่");
    } finally {
      setIsLoading(false);
    }
  }

  async function confirmBooking() {
    // The server rechecks and saves atomically; the request ID remains stable for retries (FR-02, FR-03, ASM-03, ASM-04).
    if (!summary || isLoading) {
      return;
    }
    setError("");
    setMessage("");
    setIsLoading(true);

    try {
      const activeRequestId = requestId || crypto.randomUUID();
      setRequestId(activeRequestId);
      const response = await fetch(CREATE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          ...getPayload(),
          request_id: activeRequestId,
        }),
      });
      const data = await response.json();

      if (response.status === 401) {
        goToLogin();
        return;
      }
      if (response.status === 409 && Array.isArray(data.available_slots)) {
        setSummary(null);
        setAvailableSlots(data.available_slots);
        setMessage(data.message || "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่");
        return;
      }
      if (!response.ok) {
        setError(data.message || "ไม่สามารถยืนยันการจองได้ กรุณาลองใหม่");
        return;
      }
      if (!isBookingResponse(data)) {
        throw new Error("Room reservation response has an invalid shape");
      }
      setBooking(data.booking);
      setSummary(null);
    } catch (requestError) {
      console.error("Room reservation failed", requestError);
      setError("ไม่สามารถยืนยันการจองได้ กรุณาลองใหม่");
    } finally {
      setIsLoading(false);
    }
  }

  function selectAvailableSlot(slot) {
    clearCheckResult();
    setStartTime(slot.start_time.slice(0, 5));
    setEndTime(slot.end_time.slice(0, 5));
  }

  // Render the validation, confirmation, success, and same-room/day alternatives (FR-01, FR-04, FR-05, AC-01, AC-03).
  const returnToAvailability = getReturnToAvailability(context);

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>จองห้อง</h1>
        <p>ระบุเวลาและจำนวนผู้ใช้ ตรวจสอบความว่าง แล้วจึงยืนยันการจอง</p>
        <a className="feature-link" href={returnToAvailability}>
          กลับไปตรวจสอบห้องว่าง
        </a>
      </header>

      {booking ? (
        <section className="results reservation-result" aria-live="polite">
          <h2>จองห้องสำเร็จ</h2>
          <article className="book-card">
            <p><strong>รหัสการจอง:</strong> {booking.booking_id}</p>
            <p><strong>ห้อง:</strong> {booking.room_id}</p>
            <p><strong>วันที่:</strong> {booking.booking_date}</p>
            <p>
              <strong>เวลา:</strong> {booking.start_time.slice(0, 5)}–
              {booking.end_time.slice(0, 5)}
            </p>
            <p><strong>จำนวนผู้ใช้:</strong> {booking.user_count} คน</p>
          </article>
          <a className="button-link" href={returnToAvailability}>
            กลับไปตรวจสอบห้องว่าง
          </a>
        </section>
      ) : (
        <>
          <section className="search-panel reservation-context">
            <h2>รายละเอียดห้อง</h2>
            <p><strong>ห้อง:</strong> {context.roomId || "ไม่ได้เลือก"}</p>
            <p><strong>ประเภท:</strong> {context.roomType || "ไม่ได้เลือก"}</p>
            <p><strong>วันที่:</strong> {context.bookingDate || "ไม่ได้เลือก"}</p>
            {Number.isInteger(context.capacity) && context.capacity > 0 && (
              <p><strong>ความจุ:</strong> {context.capacity} คน</p>
            )}
          </section>

          {message && (
            <p className="feedback empty-message" role="status">
              {message}
            </p>
          )}
          {error && (
            <p className="feedback error-message" role="alert">
              {error}
            </p>
          )}

          <form
            className="search-panel reservation-form"
            onSubmit={submitCheck}
            aria-busy={isLoading}
          >
            <div className="reservation-fields">
              <div className="availability-field">
                <label htmlFor="reservation-start">เวลาเริ่ม</label>
                <select
                  id="reservation-start"
                  value={startTime}
                  onChange={(event) => {
                    clearCheckResult();
                    setStartTime(event.target.value);
                  }}
                  required
                >
                  <option value="">เลือกเวลาเริ่ม</option>
                  {ROOM_SLOT_OPTIONS.slice(0, -1).map((slot) => (
                    <option key={slot} value={slot}>{slot}</option>
                  ))}
                </select>
              </div>
              <div className="availability-field">
                <label htmlFor="reservation-end">เวลาสิ้นสุด</label>
                <select
                  id="reservation-end"
                  value={endTime}
                  onChange={(event) => {
                    clearCheckResult();
                    setEndTime(event.target.value);
                  }}
                  required
                >
                  <option value="">เลือกเวลาสิ้นสุด</option>
                  {ROOM_SLOT_OPTIONS.slice(1).map((slot) => (
                    <option key={slot} value={slot}>{slot}</option>
                  ))}
                </select>
              </div>
              <div className="availability-field">
                <label htmlFor="reservation-user-count">จำนวนผู้ใช้</label>
                <input
                  id="reservation-user-count"
                  type="text"
                  inputMode="numeric"
                  value={userCount}
                  onChange={(event) => {
                    clearCheckResult();
                    setUserCount(event.target.value);
                  }}
                  required
                />
              </div>
            </div>
            <div className="reservation-actions">
              <button type="submit" disabled={isLoading}>
                {isLoading ? "กำลังตรวจสอบ..." : "ตรวจสอบเวลาใหม่"}
              </button>
              {!summary && (
                <a className="button-link secondary-link" href={returnToAvailability}>
                  ยกเลิก
                </a>
              )}
            </div>
          </form>

          {availableSlots.length > 0 && (
            <section className="results reservation-available-slots">
              <h2>ช่วงเวลาว่างของห้องนี้ในวันที่เลือก</h2>
              <p>เลือกช่วงเวลาเพื่อกรอกเวลาเริ่มและสิ้นสุด</p>
              <ul>
                {availableSlots.map((slot) => (
                  <li key={`${slot.start_time}-${slot.end_time}`}>
                    <button
                      type="button"
                      className="slot-button"
                      onClick={() => selectAvailableSlot(slot)}
                    >
                      {slot.start_time.slice(0, 5)}–{slot.end_time.slice(0, 5)}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {summary && (
            <section className="results reservation-summary" aria-live="polite">
              <h2>สรุปการจอง</h2>
              <article className="book-card">
                <p><strong>ห้อง:</strong> {summary.room_id}</p>
                <p><strong>วันที่:</strong> {summary.booking_date}</p>
                <p>
                  <strong>เวลา:</strong> {summary.start_time.slice(0, 5)}–
                  {summary.end_time.slice(0, 5)}
                </p>
                <p><strong>จำนวนผู้ใช้:</strong> {summary.user_count} คน</p>
              </article>
              <div className="reservation-actions">
                <button type="button" onClick={confirmBooking} disabled={isLoading}>
                  {isLoading ? "กำลังยืนยัน..." : "ยืนยันการจอง"}
                </button>
                <a className="button-link secondary-link" href={returnToAvailability}>
                  ยกเลิก
                </a>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}