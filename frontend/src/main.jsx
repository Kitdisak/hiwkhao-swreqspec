import React from "react";
import { createRoot } from "react-dom/client";

import BookDetailPage from "./features/book_details/BookDetailPage.jsx";
import SearchPage from "./features/book_search/SearchPage.jsx";
import "./style.css";

const bookPathPrefix = "/books/";
const currentPath = window.location.pathname;
const isBookDetail = currentPath.startsWith(bookPathPrefix);
const bookId = isBookDetail
  ? decodeURIComponent(currentPath.slice(bookPathPrefix.length))
  : "";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {isBookDetail ? <BookDetailPage bookId={bookId} /> : <SearchPage />}
  </React.StrictMode>,
);
