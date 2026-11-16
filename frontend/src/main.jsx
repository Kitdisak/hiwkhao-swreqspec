import React from "react";
import { createRoot } from "react-dom/client";

import FinePaymentPage from "./features/fine_payment/FinePaymentPage.jsx";
import BookDetailPage from "./features/book_details/BookDetailPage.jsx";
import SearchPage from "./features/book_search/SearchPage.jsx";
import "./style.css";

const bookPathPrefix = "/books/";
const currentPath = window.location.pathname;
const isBookDetail = currentPath.startsWith(bookPathPrefix);
const isFinePayment = currentPath === "/fines";
const bookId = isBookDetail
  ? decodeURIComponent(currentPath.slice(bookPathPrefix.length))
  : "";

if (isFinePayment) {
  document.title = "ชำระค่าปรับออนไลน์";
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {isFinePayment ? (
      <FinePaymentPage />
    ) : isBookDetail ? (
      <BookDetailPage bookId={bookId} />
    ) : (
      <SearchPage />
    )}
  </React.StrictMode>,
);
