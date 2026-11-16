# frontend

หน้าค้นหาหนังสืออยู่ใน `src/features/book_search/` และใช้ React + Vite

หน้ารายละเอียดหนังสืออยู่ใน `src/features/book_details/` และเปิดจากรายการค้นหาที่ `/books/{bookId}`; ข้อมูลชื่อเรื่องและตำแหน่งแสดงครั้งเดียว ส่วนรหัสประจำเล่ม สถานะ และวันคาดว่าจะคืน (เมื่อ Copy เป็น Borrowed และมีวันที่) แสดงแยกตาม Copy

## เริ่มใช้งาน

1. เริ่ม backend จาก root ของ repo ด้วย `uvicorn app.main:app --app-dir backend --reload` (เลือกโดยทีม ไม่ได้มาจาก spec)
2. ในโฟลเดอร์ `frontend` ติดตั้ง dependencies ด้วย `npm install`
3. เริ่มหน้าบ้านด้วย `npm run dev`

Vite proxy ส่งคำขอ `/api` ไปยัง backend ที่ `http://127.0.0.1:8000` เพื่อให้หน้าค้นหาและหน้ารายละเอียดเรียก API ได้ระหว่างพัฒนา
