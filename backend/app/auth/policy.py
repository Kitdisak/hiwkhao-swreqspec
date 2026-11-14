from __future__ import annotations

from .models import User


def is_borrowing_prohibited_by_user_type(user: User) -> bool:
    """ตรวจข้อห้ามบุคคลภายนอกตาม FR-สมัครสมาชิก-/-เข้าสู่ระบบ-04, AC-สมัครสมาชิก-/-เข้าสู่ระบบ-01 และ ASM-08."""
    return user.user_type == "external"
