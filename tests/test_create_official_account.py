from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import Role, User
from create_official_account import create_official_user


def test_create_official_user_creates_profile_role_and_password_hash():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        try:
            user = create_official_user(
                "test_official",
                "official-test@example.com",
                "Strong-Official-Password-123",
                "Juan Dela Cruz",
                "Barangay Kagawad",
                date(2026, 1, 1),
                "09171234567",
            )

            assert user.is_active is True
            assert user.status == "active"
            assert user.check_password("Strong-Official-Password-123")
            assert user.password_hash != "Strong-Official-Password-123"
            assert {role.name for role in user.roles} == {"Barangay Official"}
            assert user.official is not None
            assert user.official.full_name == "Juan Dela Cruz"
            assert user.official.position == "Barangay Kagawad"
            assert user.official.term_start == date(2026, 1, 1)
            assert user.official.contact_number == "09171234567"
            assert db.session.scalar(
                db.select(Role).where(Role.name == "Barangay Official")
            ) is not None

            with pytest.raises(ValueError, match="May account na"):
                create_official_user(
                    "test_official", "other@example.com", "Another-Official-Password-123",
                    "Someone Else", "Kagawad", date(2026, 1, 1)
                )
        finally:
            db.session.rollback()
            db.drop_all()
