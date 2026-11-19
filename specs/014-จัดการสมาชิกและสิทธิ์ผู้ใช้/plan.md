# แผนงาน: จัดการสมาชิกและสิทธิ์ผู้ใช้

อ้างอิง: SPEC-จัดการสมาชิกและสิทธิ์ผู้ใช้-014 (Draft v2)

## 1. สรุปแนวทาง

ผู้ดูแลระบบที่มี Permission `manage_users` จะค้นหาและเลือกบัญชีผู้ใช้ในหน้า `/manage/users` จากนั้นแก้ไขข้อมูลทั่วไป เปลี่ยน Role/Permission และระงับหรือเปิดใช้งานบัญชี แผนสร้างผ่าน React (Vite) และ Python FastAPI โดยใช้ session และ SQLite ที่โปรเจกต์มีอยู่ การบันทึกบัญชีและ Audit Log ที่สำเร็จก็จะถูกจัดการใน transaction เดียวกันแบบ all-or-nothing ไม่แก้รหัสนักศึกษา เลขบัตรประชาชน ประเภทผู้ใช้ รหัสผ่าน หรือเปลี่ยนการเก็บบัญชีไปยังที่เก็บแยก

## 2. เทคโนโลยีที่ใช้

| สิ่งที่เลือก | มาจาก | หมายเหตุ |
|---|---|---|
| React (Vite) สำหรับหน้าบ้าน | ทีมเลือกเอง ไม่ได้มาจาก spec | ค่าเริ่มต้นรายวิชาตาม prompt /plan |
| Python FastAPI สำหรับหลังบ้าน | ทีมเลือกเอง ไม่ได้มาจาก spec | ค่าเริ่มต้นรายวิชาตาม prompt /plan |
| SQLite เดิมของระบบ | Constraint: ใช้ฐานข้อมูล SQLite เดิม ห้ามสร้างที่เก็บบัญชีใหม่ | ใช้ store account/session/Audit ที่มีอยู่ร่วมกับโปรเจกต์ |
| Session cookie ของระบบ | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05, ASM-11 และ SPEC-002 | ตัวตน Admin ต้องมาจาก session ไม่รับจากคำขอ |

## 3. โมเดลข้อมูล

| Entity | ฟิลด์หลักที่เสนอ | รองรับ |
|---|---|---|
| User/Account ที่มีอยู่ | account_id/username, first_name, last_name, email, phone, student_id, user_type, role, permissions, account_status | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-01 ถึง FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-04 |
| Role | role_id/name, permissions ที่ Role มีอยู่ | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02, FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05, ASM-01 |
| Permission | permission_id/name; relationship กับ Role/UserAccount | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02, FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05, NFR-SEC-01 |
| AccountStatus | Active/Suspended | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-03, FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-04, ASM-03 |
| AuthSession ที่มีอยู่ | account_id/username, session token, last activity | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05, ASM-11 |
| AuditLog | audit_id, actor_account_id, target_account_id, timestamp_bangkok, field, old_value, new_value | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-06, NFR-AUDIT-01, ASM-12 |

ไม่เพิ่มฟิลด์หรือ API สำหรับแก้รหัสนักศึกษา เลขบัตรประชาชน ประเภทผู้ใช้ หรือรหัสผ่านในฟีเจอร์นี้ ตาม FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02 และ ASM-08

## 4. API / หน้าจอ

| รายการ | Method / path หรือหน้าจอ | Input/Output หลัก | รองรับ |
|---|---|---|---|
| ค้นหาและเลือกบัญชี | `GET /admin/users?q=...` และหน้า `/manage/users` | q ว่างคืนข้อความให้กรอก; ค้นชื่อ/นามสกุล อีเมลแบบ substring หรือรหัสนักศึกษาแบบตรงทั้งหมดไม่สนตัวพิมพ์; output สูงสุด 50 รายการพร้อมชื่อ อีเมล ประเภทผู้ใช้ Role และสถานะ; ไม่พบ “ไม่พบบัญชีผู้ใช้” | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-01, ASM-10 |
| ดูรายละเอียดบัญชีที่เลือก | `GET /admin/users/{accountId}` และหน้า `/manage/users` | ข้อมูลที่อนุญาตให้แสดงและรายการ Role/Permission ที่ actor มอบได้; ไม่แสดงเลขบัตรประชาชน | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-01, FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02, ASM-08 |
| บันทึกการจัดการบัญชี | `PATCH /admin/users/{accountId}` และหน้าแก้ไขบัญชี | ชื่อ นามสกุล อีเมล เบอร์โทร Role/Permission และสถานะที่ต้องการ; output สำเร็จหรือ 401/403 | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02 ถึง FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-06 |
| ระงับบัญชี | `POST /admin/users/{accountId}/suspend` | ไม่มี actor identity จาก input; เปลี่ยนสถานะ Suspended หรือคืน 403 | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-03 ถึง FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-06 |
| เปิดใช้งานบัญชี | `POST /admin/users/{accountId}/activate` | ไม่มี actor identity จาก input; เปลี่ยนสถานะ Active หรือคืน 403 | FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-03, FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05, FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-06 |

ทุก endpoint ต้องใช้ actor จาก session และตรวจ Permission `manage_users` สำหรับ Role Admin เท่านั้น ผล 401 และ 403 ใช้ข้อความและเงื่อนไขตาม FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05 และ ASM-11

## 5. ตารางตรวจ Constraints

| Constraint ID | ถูกนำไปใช้ที่ไหนใน plan | สถานะ |
|---|---|---|
| Admin ต้องเข้าสู่ระบบและมีสิทธิ์จัดการผู้ใช้ | Session guard และ Permission `manage_users` ที่ backend ก่อนค้นหา ดูรายละเอียด แก้ไข และเปลี่ยนสถานะ | ใช้แล้ว |
| ต้องป้องกันการเข้าถึงข้อมูลโดยไม่ได้รับอนุญาต | Backend ตรวจ actor/Permission/self-management/active-admin และส่ง 401 หรือ 403; หน้าจอไม่เปิดฟิลด์ห้ามแก้ | ใช้แล้ว |
| การเปลี่ยน Permission ต้องบันทึกใน Audit Log | PATCH/สถานะและ Role/Permission ทำใน transaction เดียวกับ append AuditLog; ตรวจ rollback เมื่อ Audit ล้มเหลว | ใช้แล้ว |
| ใช้ฐานข้อมูล SQLite เดิม ห้ามสร้างที่เก็บบัญชีใหม่ | ใช้ User/Account, session และ AuditLog บน SQLite เดิมร่วมกับโปรเจกต์ ไม่สร้าง database/store แยก | ใช้แล้ว |

## 6. แผนทดสอบจาก Acceptance Criteria

| AC ID | ชื่อ test | ทดสอบอย่างไร |
|---|---|---|
| AC-จัดการสมาชิกและสิทธิ์ผู้ใช้-01 | `test_AC_จัดการสมาชิกและสิทธิ์ผู้ใช้_01_all_or_nothing_update_and_audit` | Admin ที่มีสิทธิ์ยืนยันการเปลี่ยนข้อมูลทั่วไป/Role/สถานะในครั้งเดียว ตรวจ data/audit สำเร็จแบบ atomic และตรวจ rollback เมื่อข้อมูลหรือ Audit ล้มเหลว รวม timestamp Asia/Bangkok, actor, target, field, old/new |
| AC-จัดการสมาชิกและสิทธิ์ผู้ใช้-02 | `test_AC_จัดการสมาชิกและสิทธิ์ผู้ใช้_02_unauthorized_and_state_unchanged` | ตรวจไม่มี session ได้ 401; Member/Librarian หรือ Admin ที่ทำผิดกฎได้ 403 พร้อมข้อความกำหนด; ตรวจบัญชีและจำนวน Audit ก่อน/หลังต้องเหมือนเดิม |
| AC-จัดการสมาชิกและสิทธิ์ผู้ใช้-03 | `test_AC_จัดการสมาชิกและสิทธิ์ผู้ใช้_03_suspend_and_audit` | Admin ระงับบัญชีอื่นที่ไม่ใช่ Admin Active คนสุดท้าย ยืนยันแล้วตรวจสถานะ Suspended และ Audit append-only ใน transaction เดียวกัน |

## 7. ลำดับงาน

1. ผูก service จัดการสมาชิกกับ session และ Permission `manage_users` ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05, NFR-SEC-01
2. เพิ่มตัวค้นหาและผลลัพธ์ชื่อ/นามสกุล อีเมล และรหัสนักศึกษาตามเงื่อนไข รวม limit 50 ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-01, ASM-10
3. เพิ่ม validation ฟิลด์ทั่วไปและอีเมลซ้ำ/ว่างสำหรับบุคคลภายนอกโดยไม่เปิดฟิลด์ห้ามแก้ ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02, ASM-08
4. เพิ่มกฎ Role/Permission ของ actor, ห้ามแก้บัญชีตนเอง และ Admin Active ต้องเหลืออย่างน้อย 1 ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02, FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-03, ASM-01, ASM-06, ASM-07
5. เพิ่ม transaction เปลี่ยน account/role/status และ append Audit Log แบบ atomic ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-06, NFR-AUDIT-01, ASM-04, ASM-12
6. เพิ่ม endpoint/response 401 และ 403 พร้อมข้อความตาม spec ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-05, ASM-11
7. เพิ่มหน้า `/manage/users` สำหรับค้นหา เลือก แก้ไข และระงับ/เปิดใช้งาน ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-01 ถึง FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-04
8. เพิ่ม automated tests ตาม AC-01 ถึง AC-03 และ regression กับ SPEC-002/SPEC-004/SPEC-011 สำหรับผลการระงับ ตรวจ ASM-09
9. ตรวจว่าผล Audit append-only และไม่มี endpoint แก้หรือลบ Audit ผ่านฟีเจอร์นี้ ตรวจ ASM-12
10. รัน build/tests และตรวจว่า API/UI ไม่เปิดฟิลด์ห้ามแก้ ตรวจ FR-จัดการสมาชิกและสิทธิ์ผู้ใช้-02

## 8. สิ่งที่ยังไม่ทำ

ไม่มี Open Questions คงค้างใน spec ปัจจุบัน จึงไม่มีส่วนที่ต้องหยุดสร้างเนื่องจากคำตอบที่ยังไม่มี
