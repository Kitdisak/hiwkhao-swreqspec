import { useState } from "react";

const AVAILABILITY_ENDPOINT = "/api/rooms/availability";
const ROOM_TYPES = ["ห้องอ่านหนังสือ", "ห้องประชุม"];

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

function isAvailabilityResponse(data) {
  return (
    data &&
    Array.isArray(data.rooms) &&
    (data.message === null || typeof data.message === "string") &&
    data.rooms.every(
      (room) =>
        room &&
        typeof room.room_id === "string" &&
        typeof room.room_type === "string" &&
        (Number.isInteger(room.capacity) || room.capacity === null) &&
        Array.isArray(room.available_slots) &&
        room.available_slots.every(
          (slot) =>
            slot &&
            typeof slot.start_time === "string" &&
            typeof slot.end_time === "string",
        ),
    )
  );
}

export default function AvailabilityPage() {
  const [selectedDate, setSelectedDate] = useState("");
  const [roomType, setRoomType] = useState("");
  const [userCount, setUserCount] = useState("");
  const [rooms, setRooms] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const today = getBangkokToday();

  async function submitSearch(event) {
    // FR-ตรวจสอบห้องว่าง-01 ถึง FR-ตรวจสอบห้องว่าง-04
    event.preventDefault();
    setError("");
    setMessage("");
    setRooms([]);
    setHasSearched(false);

    if (!selectedDate || selectedDate < today) {
      setError("เลือกวันที่ตั้งแต่วันนี้เป็นต้นไป");
      return;
    }

    if (!roomType) {
      setError("กรุณาเลือกประเภทห้อง");
      return;
    }

    if (userCount && (!/^\d+$/.test(userCount) || Number(userCount) < 1)) {
      setError("กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป");
      return;
    }

    setIsLoading(true);
    const params = new URLSearchParams({
      date: selectedDate,
      room_type: roomType,
    });
    if (userCount) {
      params.set("user_count", userCount);
    }

    try {
      const response = await fetch(`${AVAILABILITY_ENDPOINT}?${params}`);
      const data = await response.json();

      if (!response.ok) {
        setError(
          typeof data.message === "string"
            ? data.message
            : "ไม่สามารถค้นหาห้องว่างได้ กรุณาลองใหม่",
        );
        return;
      }

      if (!isAvailabilityResponse(data)) {
        throw new Error("Availability response has an invalid shape");
      }

      setRooms(data.rooms);
      setMessage(data.message ?? "");
      setHasSearched(true);
    } catch (requestError) {
      console.error("Room availability search failed", requestError);
      setError("ไม่สามารถค้นหาห้องว่างได้ กรุณาลองใหม่");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>ตรวจสอบห้องว่าง</h1>
        <p>เลือกวันที่และประเภทห้องเพื่อดูช่วงเวลาที่ยังว่าง</p>
        <a className="feature-link" href="/">
          ค้นหาหนังสือ
        </a>
      </header>

      <p className="feedback demo-notice" role="note">
        ข้อมูลห้องและรายการจองที่แสดงเป็นข้อมูลตัวอย่าง ไม่ใช่ข้อมูลจริงของห้องสมุด
      </p>

      <form className="search-panel availability-form" onSubmit={submitSearch}>
        <div className="availability-fields">
          <div className="availability-field">
            <label htmlFor="availability-date">วันที่</label>
            <input
              id="availability-date"
              type="date"
              min={today}
              value={selectedDate}
              onChange={(event) => setSelectedDate(event.target.value)}
              required
            />
          </div>

          <div className="availability-field">
            <label htmlFor="availability-room-type">ประเภทห้อง</label>
            <select
              id="availability-room-type"
              value={roomType}
              onChange={(event) => setRoomType(event.target.value)}
              required
            >
              <option value="">เลือกประเภทห้อง</option>
              {ROOM_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          <div className="availability-field">
            <label htmlFor="availability-user-count">
              จำนวนผู้ใช้งาน <span>(ไม่บังคับ)</span>
            </label>
            <input
              id="availability-user-count"
              type="text"
              inputMode="numeric"
              value={userCount}
              onChange={(event) => setUserCount(event.target.value)}
              aria-describedby="availability-user-count-hint"
            />
            <small id="availability-user-count-hint">
              ระบุจำนวนเต็มตั้งแต่ 1 คนขึ้นไป
            </small>
          </div>
        </div>

        <button type="submit" disabled={isLoading}>
          {isLoading ? "กำลังค้นหา..." : "ค้นหาห้องว่าง"}
        </button>
      </form>

      <section
        className="results availability-results"
        aria-live="polite"
        aria-busy={isLoading}
      >
        {error && (
          <p className="feedback error-message" role="alert">
            {error}
          </p>
        )}
        {!error && message && (
          <p className="feedback empty-message" role="status">
            {message}
          </p>
        )}
        {hasSearched && rooms.length > 0 && (
          <>
            <h2>ห้องที่ว่างในวันที่ {selectedDate}</h2>
            {rooms.map((room) => (
              <article className="book-card availability-room" key={room.room_id}>
                <h3>{room.room_id}</h3>
                <p>
                  <strong>ประเภทห้อง:</strong> {room.room_type}
                </p>
                {room.capacity !== null && (
                  <p>
                    <strong>ความจุ:</strong> {room.capacity} คน
                  </p>
                )}
                <div className="availability-slots">
                  <h4>ช่วงเวลาว่าง</h4>
                  <ul>
                    {room.available_slots.map((slot) => (
                      <li key={`${slot.start_time}-${slot.end_time}`}>
                        {slot.start_time.slice(0, 5)}–{slot.end_time.slice(0, 5)}
                      </li>
                    ))}
                  </ul>
                </div>
              </article>
            ))}
          </>
        )}
      </section>
    </main>
  );
}