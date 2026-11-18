import { useEffect, useState } from "react";

const LIST_ENDPOINT = "/api/me/room-reservations";

function isBookingList(data) {
  return Boolean(data && Array.isArray(data.bookings));
}

export default function RoomReservationsPage() {
  const params = new URLSearchParams(window.location.search);
  const selectedId = params.get("id");
  const [bookings, setBookings] = useState([]);
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await fetch(
          selectedId
            ? `${LIST_ENDPOINT}/${encodeURIComponent(selectedId)}`
            : LIST_ENDPOINT,
          { credentials: "same-origin" },
        );
        const data = await response.json();
        if (response.status === 401) {
          window.location.assign(
            `/login?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`,
          );
          return;
        }
        if (!response.ok) {
          if (active) setError(data.message || "ไม่พบรายการจอง");
          return;
        }
        if (selectedId) {
          if (!data.booking) throw new Error("Invalid room reservation detail");
          if (active) setSelected(data.booking);
        } else {
          if (!isBookingList(data)) throw new Error("Invalid room reservation list");
          if (active) setBookings(data.bookings);
        }
      } catch (requestError) {
        console.error("Room reservations load failed", requestError);
        if (active) setError("ไม่สามารถโหลดรายการจองได้");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [selectedId]);

  async function cancelBooking(booking) {
    setError("");
    setMessage("");
    try {
      const response = await fetch(
        `${LIST_ENDPOINT}/${encodeURIComponent(booking.booking_id)}/cancel`,
        {
          method: "POST",
          credentials: "same-origin",
        },
      );
      const data = await response.json();
      if (response.status === 401) {
        window.location.assign(
          `/login?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`,
        );
        return;
      }
      if (data.message) setMessage(data.message);
      if (!response.ok) return;

      setSelected(data.booking);
      setBookings((items) =>
        items.map((item) =>
          item.booking_id === data.booking.booking_id ? data.booking : item,
        ),
      );
    } catch (requestError) {
      console.error("Room reservation cancellation failed", requestError);
      setError("ไม่สามารถยกเลิกการจองได้");
    }
  }

  function renderBooking(booking) {
    const cancelled = booking.status === "ยกเลิกแล้ว";
    return (
      <article className="book-card" key={booking.booking_id}>
        <p><strong>รหัสการจอง:</strong> {booking.booking_id}</p>
        <p><strong>ห้อง:</strong> {booking.room_id}</p>
        <p><strong>วันที่:</strong> {booking.booking_date}</p>
        <p>
          <strong>เวลา:</strong> {booking.start_time.slice(0, 5)}–
          {booking.end_time.slice(0, 5)}
        </p>
        <p><strong>สถานะ:</strong> {booking.status}</p>
        {!selectedId && (
          <a className="feature-link" href={`/rooms/reservations?id=${encodeURIComponent(booking.booking_id)}`}>
            ดูรายละเอียด
          </a>
        )}
        {!cancelled && (
          <button type="button" onClick={() => cancelBooking(booking)}>
            ยกเลิกการจอง
          </button>
        )}
      </article>
    );
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>{selectedId ? "รายละเอียดการจองห้อง" : "การจองห้องของฉัน"}</h1>
      </header>
      {loading && <p className="feedback" role="status">กำลังโหลด...</p>}
      {message && <p className="feedback" role="status">{message}</p>}
      {error && <p className="feedback error-message" role="alert">{error}</p>}
      {!loading && selected && (
        <section className="results">
          {renderBooking(selected)}
          <a className="feature-link" href="/rooms/reservations">รายการของฉัน</a>
        </section>
      )}
      {!loading && !selectedId && (
        <section className="results">
          {bookings.length === 0 ? (
            <p className="feedback empty-message">ไม่มีรายการจอง</p>
          ) : (
            bookings.map(renderBooking)
          )}
        </section>
      )}
    </main>
  );
}
