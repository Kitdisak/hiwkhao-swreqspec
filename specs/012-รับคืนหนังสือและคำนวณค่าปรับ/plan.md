# แผนงาน: รับคืนหนังสือและคำนวณค่าปรับ

อ้างอิง [spec.md](./spec.md) (SPEC-รับคืนหนังสือและคำนวณค่าปรับ-012, Draft v3) และข้อยุติจากทีม

## 1. สรุปแนวทาง
- บรรณารักษ์สแกนรหัสประจำเล่มเพื่อค้นหารายการยืมที่ยังไม่คืนตาม FR-01
- ระบบตรวจวันคืนและคำนวณค่าปรับราย Loan ด้วยวันปฏิทิน Asia/Bangkok และอัตราจากค่ากำหนดตาม FR-02, FR-03 และ ASM-07 ถึง ASM-10
- เมื่อยืนยัน ระบบบันทึกการคืน ค่าปรับที่เกิดขึ้น และสถานะ Copy ใน transaction เดียวตาม FR-04 และ ASM-11 ถึง ASM-14
- ใช้ store การจองและฐานข้อมูล SQLite เดิมร่วมกัน ไม่สร้าง reservation store หรือ fine store แยกตาม ASM-11 ถึง ASM-14
- ปรับ API/หน้าจอรับคืนและทดสอบ AC-01 ถึง AC-03 รวมถึง regression ของ SPEC-007 และ SPEC-011

## 2. เทคโนโลยีที่ใช้

| สิ่งที่เลือก | มาจาก | หมายเหตุ |
|---|---|---|
| React (Vite) สำหรับหน้าบ้าน | ทีมเลือกเอง ไม่ได้มาจาก spec | ค่าเริ่มต้นของรายวิชา; spec ไม่ระบุเทคโนโลยีหน้าบ้าน |
| Python FastAPI สำหรับหลังบ้าน | ทีมเลือกเอง ไม่ได้มาจาก spec | ค่าเริ่มต้นของรายวิชา; spec ไม่ระบุเทคโนโลยีหลังบ้าน |
| SQLite ฐานข้อมูลเดียวกับ Loan/Copy/Reservation | ทีมเลือกเอง ไม่ได้มาจาก spec | ใช้ transaction ของ reservation store เดิม; เพิ่มตาราง FineItem ในฐานข้อมูลเดิม ไม่สร้าง store ใหม่ |
| การคำนวณวันบน server ด้วย Asia/Bangkok | ASM-09 | วันคืนและวันรับคืนเป็นวันปฏิทิน ไม่ใช้เวลาในเครื่องผู้ใช้ |
| `Decimal` และ `ROUND_HALF_UP` | ASM-10 | ปัดยอดเป็นทศนิยมสองตำแหน่ง; ไม่ใช้ floating point |

## 3. โมเดลข้อมูล

| Entity / store | ฟิลด์หลัก | รองรับ |
|---|---|---|
| LoanItem (`loan_items` เดิม) | Loan, member, Copy identifier, due date, returned date, status `Borrowed`/`Returned` | FR-01 ถึง FR-05, AC-01 ถึง AC-03, ASM-03, ASM-04, ASM-12, ASM-15 |
| Copy (`loan_copy_status` เดิม) | Copy identifier, title, status `Borrowed`/`Available`/`Reserved` | FR-01, FR-04, ASM-13, ASM-14 |
| FineItem (ตารางใน SQLite เดิม) | Fine ID, member ID, book title, due/returned date, overdue days, amount, status; เพิ่ม metadata ของ store เป็น `loan_id` และ applied rate | FR-02, FR-03, NFR-ACC-01, ASM-07 ถึง ASM-12 |
| FineItem compatibility interface | คง model `FineItem` และชื่อ/สัญญาที่ SPEC-007 ใช้ เช่น `FINE_ITEMS`, `STORE_LOCK` และ `reset_store`; ให้การอ่าน/แก้สถานะสะท้อน SQLite โดยไม่แก้โค้ดหรือ test ของ SPEC-007 | ASM-11 |
| Reservation (ตาราง `reservations` เดิม) | reservation ID, member/title, status, reserved Copy, pickup deadline | FR-04, ASM-12, ASM-14 |
| Fine rate configuration | อัตราต่อวันเดียวทุกประเภท; ค่าชั่วคราว 5.00 บาท/วัน/เล่ม จนกว่าจะทราบค่าจริง | FR-03, ASM-07, Q-01 |

FineItem ที่สร้างใหม่ต้องผูกกับ Loan และสมาชิก ใช้อัตรา ณ เวลารับคืน และสร้างเฉพาะยอดมากกว่า 0; สถานะคงใช้สถานะค่าปรับค้าง/ยังไม่ชำระที่ SPEC-007 ใช้อยู่ตาม ASM-08 และ ASM-11. ย้ายรายการตัวอย่าง FINE-001/FINE-002 จาก store ปัจจุบันเป็น seed โดยคงข้อมูลที่ SPEC-007 ใช้.

## 4. API / หน้าจอ

| รายการ | Method / path และ input/output หลัก | รองรับ |
|---|---|---|
| ค้นหารายการยืมจาก Copy | `GET /api/returns/lookup?item_identifier={...}`; input รหัสประจำเล่ม; output รายการ Loan ที่ยังไม่คืน, วันกำหนดคืน, วันเกินกำหนด และยอดค่าปรับประมาณการ | FR-01, FR-02, FR-03, FR-05, ASM-15 |
| ยืนยันรับคืน | `POST /api/returns`; input รหัสประจำเล่ม; output วันรับคืน, ค่าปรับที่คำนวณใหม่ ณ เวลายืนยัน (ถ้ามี) และสถานะ Copy/Reservation หลังบันทึก | FR-04, ASM-08, ASM-11 ถึง ASM-14 |
| หน้าจอรับคืน | สแกน Copy, ตรวจ Loan/วันคืน/ยอดค่าปรับ, ยืนยัน และแสดงผลสำเร็จหรือแจ้งให้ตรวจสอบข้อมูล | FR-01 ถึง FR-06, AC-01 ถึง AC-03 |

## 5. ตารางตรวจ Constraints

| Constraint ID | ถูกนำไปใช้ที่ไหนใน plan | สถานะ |
|---|---|---|
| Constraint: ค่าปรับคำนวณตามจำนวนวันที่เกินกำหนดและอัตราที่ห้องสมุดกำหนด | คำนวณวันเกินกำหนดและคูณอัตราจาก configuration ตาม FR-02/FR-03 และ ASM-07 ถึง ASM-10; ค่าจริงยังรอ Q-01 | ใช้แล้ว |
| Constraint: ต้องมีรายการยืมของหนังสือที่นำมาคืน | lookup จากรหัส Copy; ปฏิเสธเมื่อไม่พบหรือพบ active Loan ซ้ำตาม FR-01/FR-05 และ ASM-03/ASM-04/ASM-15 | ใช้แล้ว |

## 6. แผนทดสอบจาก Acceptance Criteria

| AC ID | ชื่อ test | ทดสอบอย่างไร |
|---|---|---|
| AC-รับคืนหนังสือและคำนวณค่าปรับ-01 | `test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_overdue_return` | คืน Loan ที่เกินกำหนดด้วยอัตราชั่วคราว 5.00 บาท/วัน; ตัวอย่าง due 2 ธ.ค. และคืน 5 ธ.ค. ต้องได้ 15.00 บาท, บันทึกวันคืนและ FineItem ที่เชื่อม Loan/member, เปลี่ยน Copy ตามสถานะคิว และยืนยัน rollback ทั้งชุดเมื่อการบันทึกส่วนใดล้มเหลว |
| AC-รับคืนหนังสือและคำนวณค่าปรับ-01 | `test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_round_half_up` | ตั้งอัตราทดสอบที่ทำให้ยอดก่อนปัดเป็น 2.125 แล้วตรวจว่าได้ 2.13 และแสดงสองตำแหน่งตาม ASM-10 |
| AC-รับคืนหนังสือและคำนวณค่าปรับ-02 | `test_AC_รับคืนหนังสือและคำนวณค่าปรับ_02_on_time_return` | คืนตรงวันกำหนด; ต้องไม่มี FineItem, บันทึกการคืน และเมื่อไม่มี Waiting reservation ให้ Copy เป็น Available |
| AC-รับคืนหนังสือและคำนวณค่าปรับ-03 | `test_AC_รับคืนหนังสือและคำนวณค่าปรับ_03_missing_active_loan` | สแกน Copy ที่ไม่มี Loan ค้าง; ต้องแจ้งให้ตรวจสอบและไม่เปลี่ยน Loan, Copy, Fine หรือ Reservation |
| AC-รับคืนหนังสือและคำนวณค่าปรับ-01/02 | `test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_02_ready_reservation` | ทดสอบกรณีมี Waiting reservation ว่าคิวแรกเป็น Ready, ผูก Copy ที่คืน, สถานะ Copy เป็น Reserved และ pickup deadline ใช้ค่า provisional ตาม ASM-14 |

นอกเหนือจาก AC ให้ทดสอบกรณีพบ active Loan มากกว่าหนึ่งรายการของ Copy เดียวตาม ASM-15 โดยปฏิเสธและไม่เปลี่ยนข้อมูลใด.

เพิ่ม regression checks โดยไม่แก้ test/code ของ SPEC-007 และ SPEC-011; ตรวจรายการตัวอย่าง FineItem, การชำระ/สถานะ Fine เดิม, การยืมและ reservation เดิม และสุดท้ายรัน `pytest -q` ทั้งชุด.

## 7. ลำดับงาน
1. ขยาย schema/migration ของ LoanItem ให้บันทึกวันคืนและสถานะ Returned โดยคง unique active Loan ต่อ Copy ตาม FR-01, FR-04, FR-05
2. เพิ่ม configuration อัตราค่าปรับแบบไม่ hardcode และ calculation service ใช้วัน Asia/Bangkok, Decimal, ROUND_HALF_UP ตาม FR-02, FR-03, NFR-ACC-01, ASM-07 ถึง ASM-10
3. ย้าย backing store ของ FineItem ไป SQLite เดียวกับ Reservation/Loan/Copy; คง model, ชื่อและสัญญาที่ SPEC-007 ใช้ และย้าย FineItem ตัวอย่างเป็น seed ตาม ASM-11/ASM-12
4. เพิ่ม lookup ด้วยรหัส Copy และจัดการกรณีไม่พบ Loan หรือมี active Loan มากกว่าหนึ่งรายการตาม FR-01, FR-05, ASM-03/ASM-04/ASM-15
5. ทำการคืน, FineItem, Copy และ Reservation ใน transaction เดียว; เลือก Available หรือ Waiting → Ready/Reserved ตาม ASM-12 ถึง ASM-14
6. เชื่อม API สำหรับค้นหารายการยืมและยืนยันคืน พร้อมผลลัพธ์ตาม FR-01 ถึง FR-06
7. สร้าง/ปรับหน้าจอสแกน ตรวจยอด และยืนยันรับคืนตาม FR-01 ถึง FR-06
8. เพิ่ม/ปรับ test ให้ครอบคลุม AC-01 ถึง AC-03 และ ASM-07 ถึง ASM-15 โดยคง test ของ SPEC-007/011
9. รัน test ที่เกี่ยวข้อง แล้วรัน `pytest -q` ทั้งชุด; แก้ regression ที่เกิดจากการเปลี่ยน store/migration ก่อนจบ

## 8. สิ่งที่ยังไม่ทำ

- **Q-01** อัตราค่าปรับจริงต่อวันของห้องสมุดยังไม่ทราบ (สัมพันธ์กับ SPEC-007 Q-07); ส่วนที่ใช้ค่าจริงจะยังไม่สร้างจนกว่าจะได้คำตอบ; ระหว่างนี้ใช้ 5.00 บาท/วัน/เล่มเป็นค่า provisional ตาม ASM-07
- **Q-02** จำนวนวันรับหนังสือจริงหลัง Reservation เป็น Ready ยังไม่ทราบ; ส่วนที่ต้องใช้ค่าจริงจะยังไม่สร้างจนกว่าจะได้คำตอบ; ระหว่างนี้ใช้ 3 วันเป็นค่า provisional ตาม ASM-14
- **Q-03** เมื่อผู้จองไม่มารับหนังสือภายใน pickup deadline ต้องเปลี่ยนสถานะ Reservation และ Copy อย่างไรยังไม่ทราบ; ส่วนจัดการกรณีไม่มารับจะยังไม่สร้างจนกว่าจะได้คำตอบ
- **Q-04** ต้องแจ้งเตือนผู้จองเมื่อ Reservation เปลี่ยนเป็น Ready หรือไม่ และใช้ช่องทางใดยังไม่ทราบ; การแจ้งเตือนจะยังไม่สร้างจนกว่าจะได้คำตอบ
