# แผนงาน: สมัครสมาชิก / เข้าสู่ระบบ

อ้างอิง: [spec.md](./spec.md) — SPEC-สมัครสมาชิก-เข้าสู่ระบบ-002 (Draft v2)

## 1. สรุปแนวทาง

- รองรับการสมัครสมาชิกสำหรับผู้ที่ยังไม่มีบัญชีและกำหนดรหัสผ่านใหม่ก่อนเข้าสู่ระบบ (AC-สมัครสมาชิก-/-เข้าสู่ระบบ-01, ASM-01, ASM-15)
- ตรวจสอบนักศึกษาและบุคลากรผ่าน registry adapter จุดเดียว ใช้ทะเบียนจำลองระหว่างพัฒนา และจำแนกผู้ไม่พบข้อมูลระหว่างสมัครเป็นบุคคลภายนอก (ASM-23 ถึง ASM-29)
- รองรับการเข้าสู่ระบบและลืมรหัสผ่านตามประเภทผู้ใช้ พร้อมบังคับรหัสผ่านและ idle timeout ตาม NFR-SEC-01/NFR-SEC-02
- ควบคุมสิทธิ์ให้ทุกบทบาทเท่ากัน ยกเว้นบุคคลภายนอกห้ามยืมหนังสือ (FR-สมัครสมาชิก-/-เข้าสู่ระบบ-04, ASM-14)

## 2. เทคโนโลยีที่ใช้

| สิ่งที่เลือก | มาจาก | หมายเหตุ |
|---|---|---|
| React (Vite) สำหรับหน้าบ้าน | **ทีมเลือกเอง ไม่ได้มาจาก spec** | ค่าเริ่มต้นของรายวิชา ไม่มี Constraint ระบุเทคโนโลยีหน้าบ้าน |
| Python FastAPI สำหรับหลังบ้าน | **ทีมเลือกเอง ไม่ได้มาจาก spec** | ค่าเริ่มต้นของรายวิชา ไม่มี Constraint ระบุเทคโนโลยีหลังบ้าน |
| ฐานข้อมูลที่มีอยู่ของโปรเจกต์สำหรับบัญชี | **ทีมเลือกเอง ไม่ได้มาจาก spec** | Spec ไม่ระบุชนิดฐานข้อมูล และระบุเฉพาะจัดเก็บรหัสผ่านในรูป hash |

## 3. โมเดลข้อมูล

| Entity | ฟิลด์หลักที่วางแผน | รองรับ |
|---|---|---|
| Account | account_id, user_type, identifier, display_name, email, password_hash, role | FR-01, FR-02, FR-04, NFR-SEC-01, ASM-07, ASM-11, ASM-12 |
| IdentityProfile | account_id, ชื่อ, นามสกุล, วัน/เดือน/ปีเกิด, เลขบัตรประชาชน, เบอร์โทรศัพท์, student_id | FR-03, ASM-05, ASM-09, ASM-10, ASM-27 |
| AuthSession | session_id, account_id, last_activity_at, expires_at | FR-01, FR-04, NFR-SEC-02, ASM-16 |
| RegistryAdapterResult | lookup_type, found, student_status, profile | ASM-23, ASM-24, ASM-26, ASM-28 |
| RolePermissionPolicy | role, allowed_permissions, denies_external_borrow | FR-04, ASM-14 |

ไม่มีฟิลด์รหัสผ่านแบบ plain text ใน entity ใด; password ต้องเก็บเป็น password_hash ตาม NFR-SEC-01

## 4. API / หน้าจอ

| รายการ | Method / path หรือ input/output หลัก | รองรับ |
|---|---|---|
| สมัครสมาชิก | `POST /api/auth/register`; input: ชื่อ, นามสกุล, วัน/เดือน/ปีเกิด, เลขบัตรประชาชน, เบอร์โทรศัพท์, อีเมลตามประเภท, รหัสนักศึกษาถ้ามี, รหัสผ่าน; output: created/external หรือ registry unavailable | AC-01, ASM-05, ASM-06, ASM-15, ASM-18, ASM-19 |
| เข้าสู่ระบบ | `POST /api/auth/login`; input: identifier ตามประเภทและรหัสผ่าน; output: session หรือข้อความผิดพลาด | FR-01, FR-02, AC-02, AC-03, ASM-07 |
| ลืมรหัสผ่าน | `POST /api/auth/password-reset`; input: ข้อมูลยืนยันตามประเภทและรหัสผ่านใหม่เมื่อยืนยันแล้ว; output: can_reset หรือ mismatch/timeout | FR-03, AC-04, ASM-09, ASM-10, ASM-17 |
| หน้าสมัครสมาชิก | ฟอร์มข้อมูลสมัครและรหัสผ่านพร้อม validation | AC-01, NFR-SEC-01 |
| หน้าลงชื่อเข้าใช้ | ฟอร์ม identifier และรหัสผ่านพร้อมข้อความกรณีผิด | AC-02, AC-03 |
| หน้าลืมรหัสผ่าน | ฟอร์มข้อมูลยืนยันและรหัสผ่านใหม่ | AC-04 |
| Protected endpoint | Middleware ตรวจ session และสิทธิ์; idle เกิน 10 นาทีตอบ 401 | NFR-SEC-02, AC-02 |

registry adapter เป็นจุดเชื่อมทะเบียนเดี่ยว ใช้ mock registry ระหว่างพัฒนาและทดสอบ timeout ผ่านโหมดจำลองตาม ASM-25/ASM-26

## 5. ตารางตรวจ Constraints

| Constraint ID | ถูกนำไปใช้ที่ไหนใน plan | สถานะ |
|---|---|---|
| Constraint ข้อ 1: ผู้ใช้ต้องมีบัญชีที่ถูกต้องหรือข้อมูลในทะเบียน; ผู้ไม่พบข้อมูลเป็นบุคคลภายนอก | `POST /api/auth/register` และ registry adapter ตรวจบัญชี/ทะเบียนก่อนสร้างบัญชี; timeout 5 วินาทีไม่สร้างบัญชีและแจ้งให้ลองใหม่ | ใช้แล้ว |
| Constraint ข้อ 2: ควบคุมสิทธิ์การเข้าถึงข้อมูลตามบทบาท | AuthSession และ RolePermissionPolicy บังคับ protected endpoints; บุคคลภายนอกห้ามยืมหนังสือ | ใช้แล้ว |

## 6. แผนทดสอบจาก Acceptance Criteria

| AC ID | ชื่อ test | ทดสอบอย่างไร |
|---|---|---|
| AC-สมัครสมาชิก-/-เข้าสู่ระบบ-01 | `test_AC_สมัครสมาชิก_เข้าสู่ระบบ_01` | ทดสอบฟิลด์บังคับ, email ตามประเภท, การพบ/ไม่พบในทะเบียน, registry timeout, password policy, ชื่อแสดงผล และห้ามบุคคลภายนอกยืม |
| AC-สมัครสมาชิก-/-เข้าสู่ระบบ-02 | `test_AC_สมัครสมาชิก_เข้าสู่ระบบ_02` | ทดสอบ identifier ตามประเภทและเข้าสู่ระบบสำเร็จ; รวมกรณี idle timeout ด้วย 401 และต้องเข้าสู่ระบบใหม่ |
| AC-สมัครสมาชิก-/-เข้าสู่ระบบ-03 | `test_AC_สมัครสมาชิก_เข้าสู่ระบบ_03` | ทดสอบ identifier/rหัสผ่านผิด แสดงข้อความที่กำหนด ปฏิเสธการเข้าสู่ระบบ และ retry ได้ |
| AC-สมัครสมาชิก-/-เข้าสู่ระบบ-04 | `test_AC_สมัครสมาชิก_เข้าสู่ระบบ_04_password_reset` | ทดสอบชุดข้อมูลยืนยันนักศึกษา/บุคลากร/บุคคลภายนอก, ข้อมูลตรง/ไม่ตรง และ registry timeout |

## 7. ลำดับงาน

1. สร้าง Account, IdentityProfile, AuthSession และ RolePermissionPolicy
2. สร้าง registry adapter และ mock registry สำหรับ found/not_found/timeout
3. เพิ่ม `POST /api/auth/register` และหน้าสมัครสมาชิก
4. เพิ่ม/ปรับ login, session และ idle timeout
5. เพิ่ม policy ห้ามบุคคลภายนอกยืมหนังสือ
6. เพิ่มกระบวนการลืมรหัสผ่านและตั้งรหัสผ่านใหม่
7. เชื่อมหน้าบ้าน login/register/forgot password
8. รัน test ครบ AC และ build frontend

## 8. สิ่งที่ยังไม่ทำ

- Spec ไม่มี Open Questions ค้าง จึงไม่มีส่วนที่ต้องหยุดรอคำตอบ
