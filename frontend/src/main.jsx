import React from "react";
import { createRoot } from "react-dom/client";

import FinePaymentPage from "./features/fine_payment/FinePaymentPage.jsx";
import BookDetailPage from "./features/book_details/BookDetailPage.jsx";
import SearchPage from "./features/book_search/SearchPage.jsx";
import LoginPage from "./features/auth/LoginPage.jsx";
import AvailabilityPage from "./features/rooms/AvailabilityPage.jsx";
import ReservationPage from "./features/rooms/ReservationPage.jsx";
import MyReservationsPage from "./features/reservations/MyReservationsPage.jsx";
import RoomReservationsPage from "./features/rooms/RoomReservationsPage.jsx";
import BorrowingPage from "./features/loans/BorrowingPage.jsx";
import ReturnPage from "./features/returns/ReturnPage.jsx";
import BookManagementPage from "./features/book_management/BookManagementPage.jsx";
import UserManagementPage from "./features/user_management/UserManagementPage.jsx";
import "./style.css";

const bookPathPrefix = "/books/";
const currentPath = window.location.pathname;
const isBookDetail = currentPath.startsWith(bookPathPrefix);
const isFinePayment = currentPath === "/fines";
const isRoomAvailability = currentPath === "/rooms/availability";
const isRoomReservation = currentPath === "/rooms/reservations/new";
const isMyReservations = currentPath === "/my-reservations";
const isRoomReservations = currentPath === "/rooms/reservations";
const isLoanRecording = currentPath === "/loans/new";
const isReturnRecording = currentPath === "/returns";
const isLogin = currentPath === "/login";
const isBookManagement = currentPath === "/manage/books";
const isUserManagement = currentPath === "/manage/users";
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
} else if (isRoomReservations) {
  document.title = "การจองห้องของฉัน";
} else if (isLoanRecording) {
  document.title = "บันทึกการยืมหนังสือ";
} else if (isReturnRecording) {
  document.title = "รับคืนหนังสือและคำนวณค่าปรับ";
} else if (isLogin) {
  document.title = "เข้าสู่ระบบ";
} else if (isBookManagement) {
  document.title = "จัดการข้อมูลหนังสือ";
} else if (isUserManagement) {
  document.title = "จัดการสมาชิกและสิทธิ์ผู้ใช้";
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
    ) : isRoomReservations ? (
      <RoomReservationsPage />
    ) : isLoanRecording ? (
      <BorrowingPage />
    ) : isReturnRecording ? (
      <ReturnPage />
    ) : isBookManagement ? (
      <BookManagementPage />
    ) : isUserManagement ? (
      <UserManagementPage />
    ) : isBookDetail ? (
      <BookDetailPage bookId={bookId} />
    ) : (
      <SearchPage />
    )}
  </React.StrictMode>,
);
