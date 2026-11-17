import React from "react";
import { createRoot } from "react-dom/client";

import FinePaymentPage from "./features/fine_payment/FinePaymentPage.jsx";
import BookDetailPage from "./features/book_details/BookDetailPage.jsx";
import SearchPage from "./features/book_search/SearchPage.jsx";
import LoginPage from "./features/auth/LoginPage.jsx";
import AvailabilityPage from "./features/rooms/AvailabilityPage.jsx";
import ReservationPage from "./features/rooms/ReservationPage.jsx";
import MyReservationsPage from "./features/reservations/MyReservationsPage.jsx";
import "./style.css";

const bookPathPrefix = "/books/";
const currentPath = window.location.pathname;
const isBookDetail = currentPath.startsWith(bookPathPrefix);
const isFinePayment = currentPath === "/fines";
const isRoomAvailability = currentPath === "/rooms/availability";
const isRoomReservation = currentPath === "/rooms/reservations/new";
const isMyReservations = currentPath === "/my-reservations";
const isLogin = currentPath === "/login";
const bookId = isBookDetail
  ? decodeURIComponent(currentPath.slice(bookPathPrefix.length))
  : "";

if (isFinePayment) {
  document.title = "ชำระค่าปรับออนไลน์";
} else if (isRoomAvailability) {
  document.title = "ตรวจสอบห้องว่าง";
} else if (isRoomReservation) {
  document.title = "จองห้อง";
} else if (isMyReservations) {
  document.title = "รายการจองของฉัน";
} else if (isLogin) {
  document.title = "เข้าสู่ระบบ";
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {isFinePayment ? (
      <FinePaymentPage />
    ) : isLogin ? (
      <LoginPage />
    ) : isRoomAvailability ? (
      <AvailabilityPage />
    ) : isRoomReservation ? (
      <ReservationPage />
    ) : isMyReservations ? (
      <MyReservationsPage />
    ) : isBookDetail ? (
      <BookDetailPage bookId={bookId} />
    ) : (
      <SearchPage />
    )}
  </React.StrictMode>,
);
