import { useEffect, useState } from "react";

const RESERVATIONS_ENDPOINT = "/api/me/reservations";
const RESERVATION_STATUSES = new Set(["Waiting", "Ready", "Completed"]);
const THAI_DATE_FORMAT = new Intl.DateTimeFormat("th-TH", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "Asia/Bangkok",
});

function isValidDate(value) {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function isReservationListResponse(data) {
  return Boolean(
    data &&
      Array.isArray(data.reservations) &&
      data.reservations.every(
        (reservation) =>
          reservation &&
          typeof reservation.reservation_id === "string" &&
          typeof reservation.title === "string" &&
          Array.isArray(reservation.authors) &&
          reservation.authors.every((author) => typeof author === "string") &&
          isValidDate(reservation.recorded_at) &&
          RESERVATION_STATUSES.has(reservation.status) &&
          (reservation.status === "Waiting"
            ? Number.isInteger(reservation.queue_position) &&
              reservation.queue_position > 0
            : reservation.queue_position === null) &&
          (reservation.pickup_deadline === null ||
            isValidDate(reservation.pickup_deadline)),
      ),
  );
}

function formatThaiDate(value) {
  return THAI_DATE_FORMAT.format(new Date(value));
}

// SPEC-005: แสดงข้อมูลตาม FR-ติดตามสถานะการจองหนังสือ-01 ถึง
// FR-ติดตามสถานะการจองหนังสือ-04 และ AC-ติดตามสถานะการจองหนังสือ-01 ถึง AC-ติดตามสถานะการจองหนังสือ-03.
export default function MyReservationsPage() {
  const [reservations, setReservations] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isActive = true;

    async function loadReservations() {
      try {
        const response = await fetch(RESERVATIONS_ENDPOINT, {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });

        if (response.status === 401) {
          window.location.assign(
            `/login?returnTo=${encodeURIComponent("/my-reservations")}`,
          );
          return;
        }
        if (!response.ok) {
          throw new Error(
            `Reservations request failed with status ${response.status}`,
          );
        }

        const data = await response.json();
        if (!isReservationListResponse(data)) {
          throw new Error("Reservations response has an invalid shape");
        }
        if (isActive) {
          setReservations(data.reservations);
        }
      } catch (requestError) {
        console.error("Reservations request failed", requestError);
        if (isActive) {
          setError("ไม่สามารถโหลดรายการจองได้ กรุณาลองใหม่");
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    loadReservations();
    return () => {
      isActive = false;
    };
  }, []);

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ห้องสมุด</p>
        <h1>รายการจองของฉัน</h1>
        <p>ตรวจสอบสถานะและลำดับคิวของรายการจอง</p>
        <a className="feature-link" href="/">
          กลับไปหน้าหลัก
        </a>
      </header>

      {isLoading ? (
        <p className="feedback" role="status">
          กำลังโหลดรายการจอง...
        </p>
      ) : error ? (
        <p className="feedback error-message" role="alert">
          {error}
        </p>
      ) : reservations.length === 0 ? (
        <p className="feedback empty-message" role="status">
          ไม่มีรายการ
        </p>
      ) : (
        <section className="results reservation-list" aria-label="รายการจอง">
          {reservations.map((reservation) => (
            <article className="book-card" key={reservation.reservation_id}>
              <h2>{reservation.title}</h2>
              <p>
                <strong>ผู้แต่ง:</strong> {reservation.authors.join(", ")}
              </p>
              <p>
                <strong>วันที่จอง:</strong>{" "}
                {formatThaiDate(reservation.recorded_at)}
              </p>
              <p>
                <strong>สถานะ:</strong> {reservation.status}
              </p>
              {reservation.status === "Waiting" && (
                <p>
                  <strong>ลำดับคิวที่</strong> {reservation.queue_position}
                </p>
              )}
              {reservation.status === "Ready" &&
                reservation.pickup_deadline && (
                  <p>
                    <strong>วันหมดเขตรับ:</strong>{" "}
                    {formatThaiDate(reservation.pickup_deadline)}
                  </p>
                )}
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
