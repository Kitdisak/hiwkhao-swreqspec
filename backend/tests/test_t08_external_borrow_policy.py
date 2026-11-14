import pytest

from app.auth.models import User
from app.auth.policy import is_borrowing_prohibited_by_user_type


@pytest.mark.parametrize(
    ("user_type", "prohibited"),
    [
        ("student", False),
        ("staff", False),
        ("external", True),
    ],
)
def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_01_borrowing_prohibition_by_user_type(user_type, prohibited):
    user = User(
        username="test-user",
        email="test@example.com",
        student_id=None,
        password_hash="",
        user_type=user_type,
    )

    assert is_borrowing_prohibited_by_user_type(user) is prohibited
