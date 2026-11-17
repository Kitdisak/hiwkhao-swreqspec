# backend
Python FastAPI จะถูกสร้างสัปดาห์หน้า โค้ดของแต่ละฟีเจอร์อยู่ที่ app/<ชื่อฟีเจอร์>/ และ test อยู่ที่ tests/test_ac_<prefix>.py ตั้งชื่อ test ตาม AC ID

UC-03 อ่านรายละเอียดหนังสือผ่าน `GET /api/books/{book_id}`; ฟิลด์ที่ไม่มีจะไม่ถูกรวมในผลลัพธ์ และวันคาดว่าจะคืนจะแสดงเมื่อสถานะเป็น `Borrowed` และมีวันที่

## ชำระค่าปรับออนไลน์ (SPEC-ชำระค่าปรับออนไลน์-007)

- `GET /api/me/fines` แสดงรายการค่าปรับค้าง รายละเอียดต่อรายการ และยอดรวม
- `POST /api/payments` เริ่มคำขอด้วย `{ "channel": "..." }`
- `POST /api/payments/{payment_ref}/status-check` ตรวจผลด้วย ref เดิม
- `POST /api/payments/result` รับ callback ผ่าน adapter ที่ต้องตรวจสอบผลจาก Gateway ก่อน
- คำขอที่ยังรอผลถูกตรวจโดย worker ทุก 5 นาที และหมดอายุเมื่อครบ 30 นาที (FR-ชำระค่าปรับออนไลน์-04)

ข้อมูลค่าปรับตัวอย่างและสถานะคำขอใน implementation ปัจจุบันเก็บในหน่วยความจำของ process; ไม่ใช่ข้อมูล production ที่คงอยู่หลัง restart. ยังไม่ได้ตั้งค่า Payment Gateway จริง เนื่องจาก spec ไม่ระบุผู้ให้บริการหรือรูปแบบ callback; API จะตอบ `503` และไม่สร้างคำขอหากยังไม่มี adapter ที่ตรวจสอบผลได้. Tests ใช้ fake adapter เพื่อทดสอบ flow โดยไม่ส่งเงินจริง (FR-ชำระค่าปรับออนไลน์-02, NFR-SEC-01, NFR-REL-01).

## วัดประสิทธิภาพการค้นหา (NFR-PERF-01)

เริ่ม API ที่ `http://127.0.0.1:8000` แล้วเรียกจากโฟลเดอร์ `backend/`:

```bash
PYTHONPATH=. python tests/perf_search.py
```

สคริปต์ใช้ข้อมูล seed 4 ชื่อเรื่องและวัดเวลาตอบกลับ API ที่ 50 และ 200 requests พร้อมกัน โดย 3 วินาทีเป็นเป้าหมาย ไม่ใช่เกณฑ์ผ่าน/ตก ทั้งนี้การวัดนี้ไม่รวมเวลาแสดงผลใน browser. ระบุ `--users 50` หรือ `--users 200` เพื่อวัดเฉพาะระดับเดียว.

## วัดประสิทธิภาพการตรวจสอบห้องว่าง (NFR-PERF-01)

เรียกจากโฟลเดอร์ `backend/`:

```bash
PYTHONPATH=. python tests/perf_room_availability.py
```

สคริปต์สร้าง API server ชั่วคราวและใช้ข้อมูลทดสอบ 50 ห้องกับ 36,000 รายการจองใน 60 วัน; ยิงคำขอพร้อมกัน 50 และ 200 ครั้งทั้งแบบไม่ใช้ตัวกรองและใช้ตัวกรอง 12 คนขึ้นไป. รายงานเปอร์เซ็นต์คำขอไม่เกิน 3 วินาที, p95, เวลาเฉลี่ย และเวลาสูงสุด; การวัดสิ้นสุดเมื่อรับและตรวจสอบ JSON response ครบ และไม่รวม browser rendering ตามวิธีวัด API ของ SPEC-001 ASM-06. ค่า 3 วินาทีเป็นเป้าหมาย ไม่ใช่เกณฑ์ผ่าน/ตก.

หากต้องการเปิดหน้าเว็บกับ fixture นี้เพื่อวัด browser rendering แยกจาก API ให้เริ่ม `PYTHONPATH=. python tests/perf_room_availability.py --serve-only` แล้วเปิด frontend; อีก terminal ใช้ `PYTHONPATH=. python tests/perf_room_availability.py --base-url http://127.0.0.1:8000` เพื่อยิงโหลดพร้อมกัน. หยุด fixture server ด้วย Ctrl+C.
