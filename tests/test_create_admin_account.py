import pytest

from app import create_app
from app.extensions import db
from app.models import Role, User
from create_admin_account import create_admin_user


def test_create_admin_user_hashes_password_and_rejects_duplicates():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        try:
            user = create_admin_user("local_admin", "local-admin@example.com", "Strong-Passphrase-123")

            assert user.is_active is True
            assert user.status == "active"
            assert user.must_change_password is True
            assert user.check_password("Strong-Passphrase-123")
            assert user.password_hash != "Strong-Passphrase-123"
            assert {role.name for role in user.roles} == {"System Administrator"}
            assert db.session.scalar(
                db.select(Role).where(Role.name == "System Administrator")
            ) is not None

            with app.test_client() as client:
                response = client.post(
                    "/auth/login",
                    data={"identifier": "local_admin", "password": "Strong-Passphrase-123"},
                )
                assert response.status_code == 302
                assert response.headers["Location"].endswith("/auth/change-password")

            with pytest.raises(ValueError, match="May account na"):
                create_admin_user("local_admin", "another@example.com", "Another-Strong-Password-123")
        finally:
            db.session.rollback()
            db.drop_all()
