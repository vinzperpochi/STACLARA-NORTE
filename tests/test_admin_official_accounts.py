import pytest

from app import create_app
from app.extensions import db
from app.models import Role, User
from seed_default_accounts import ensure_default_accounts


@pytest.fixture(autouse=True)
def fake_official_email(monkeypatch):
    monkeypatch.setattr("app.admin.send_official_credentials", lambda **kwargs: None)
    from types import SimpleNamespace
    monkeypatch.setattr("app.admin.secrets", SimpleNamespace(token_urlsafe=lambda size: "Test-random-temporary-credential!"))


def _login(client, identifier, password):
    return client.post(
        "/auth/login",
        data={"identifier": identifier, "password": password},
        follow_redirects=False,
    )


def _create_official(client, email="kagawad@example.com"):
    return client.post(
        "/admin/official-accounts",
        data={
            "email": email,
            "full_name": "Juan Dela Cruz",
            "position": "Barangay Kagawad",
            "birth_date": "1992-03-04",
            "term_start": "2026-01-01",
            "term_end": "2029-12-31",
            "contact_number": "09171234567",
        },
        follow_redirects=False,
    )


def test_superadmin_creates_official_with_generated_id_random_password_and_first_login_change():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        try:
            ensure_default_accounts()
            with app.test_client() as client:
                assert _login(client, "admin", "Admin@123456").status_code == 302
                dashboard = client.get("/admin/")
                assert dashboard.status_code == 200
                assert b"Officials Workspace" not in dashboard.data
                assert b"Official Account Center" not in dashboard.data
                assert b"Backend connected." not in dashboard.data
                assert b'name="birth_date"' not in dashboard.data
                page = client.get("/admin/official-accounts")
                assert page.status_code == 200
                assert b"Account setup" in page.data
                assert b"Email credentials" in page.data
                assert b"SCN-OFF-000001" in page.data
                assert b'name="birth_date"' in page.data
                assert b'Gumawa ng official account' in page.data
                assert b"official@barangay.gov" in page.data
                assert b"Official profile not linked" in page.data
                assert b"SCN-OFF-000001" in page.data
                response = _create_official(client)
                assert response.status_code == 302

            user = db.session.scalar(db.select(User).where(User.email == "kagawad@example.com"))
            assert user is not None
            assert user.username == "SCN-OFF-000001"
            assert user.is_active is True and user.status == "active"
            assert user.must_change_password is True
            assert user.check_password("Test-random-temporary-credential!")
            assert {role.name for role in user.roles} == {"Barangay Official"}
            assert user.official is not None
            assert user.official.user is user
            assert user.official.full_name == "Juan Dela Cruz"
            assert user.official.position == "Barangay Kagawad"
            assert user.official.term_end.isoformat() == "2029-12-31"

            with app.test_client() as official_client:
                login_response = _login(official_client, "  scn-off-000001  ", "Test-random-temporary-credential!")
                assert login_response.status_code == 302
                assert login_response.headers["Location"].endswith("/auth/change-password")
        finally:
            db.session.rollback()
            db.drop_all()


def test_generated_official_id_uses_unique_suffix_on_legacy_username_collision():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        try:
            ensure_default_accounts()
            collision = User(
                username="SCN-OFF-000001",
                email="legacy-id@example.com",
                status="active",
                is_active=True,
            )
            collision.set_password("Legacy-Password-123")
            db.session.add(collision)
            db.session.commit()

            with app.test_client() as client:
                assert _login(client, "admin", "Admin@123456").status_code == 302
                response = _create_official(client)
                assert response.status_code == 302

            created = db.session.scalar(db.select(User).where(User.email == "kagawad@example.com"))
            assert created is not None
            assert created.username == "SCN-OFF-000001-1"
        finally:
            db.session.rollback()
            db.drop_all()


def test_barangay_official_cannot_create_official_accounts():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        try:
            ensure_default_accounts()
            with app.test_client() as client:
                assert _login(client, "official", "Official@123456").status_code == 302
                response = client.get("/admin/official-accounts")
                assert response.status_code == 403
                post_response = client.post(
                    "/admin/official-accounts",
                    data={"email": "blocked@example.com", "birth_date": "1980-01-01"},
                )
                assert post_response.status_code == 403
            assert db.session.scalar(db.select(User).where(User.email == "blocked@example.com")) is None
        finally:
            db.session.rollback()
            db.drop_all()


def test_generic_role_assignment_cannot_grant_barangay_official_role():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        try:
            ensure_default_accounts()
            resident_role = db.session.scalar(db.select(Role).where(Role.name == "Resident"))
            official_role = db.session.scalar(db.select(Role).where(Role.name == "Barangay Official"))
            target = User(username="target_user", email="target@example.com", status="active", is_active=True)
            target.set_password("Target-User-Password-123")
            target.roles.append(resident_role)
            db.session.add(target)
            db.session.commit()

            with app.test_client() as client:
                assert _login(client, "admin", "Admin@123456").status_code == 302
                response = client.post(
                    f"/admin/users/{target.id}/roles",
                    data={"role_id": official_role.id},
                    follow_redirects=False,
                )
                assert response.status_code == 302

            db.session.refresh(target)
            assert "Barangay Official" not in {role.name for role in target.roles}
        finally:
            db.session.rollback()
            db.drop_all()


def test_official_accounts_have_pagination_credentials_status_and_delete():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        try:
            ensure_default_accounts()
            with app.test_client() as client:
                assert _login(client, "admin", "Admin@123456").status_code == 302
                for index in range(11):
                    response = _create_official(client, email=f"official-{index}@example.com")
                    assert response.status_code == 302

                first_page = client.get("/admin/official-accounts")
                assert first_page.status_code == 200
                assert b"Page 1 of 3" in first_page.data
                assert b"Login ID" in first_page.data
                assert b"Temporary password: sent by email" in first_page.data
                assert b"Next" in first_page.data

                second_page = client.get("/admin/official-accounts?page=2")
                assert b"Page 2 of 3" in second_page.data
                created = db.session.scalar(db.select(User).where(User.email == "official-0@example.com"))
                delete_response = client.post(
                    f"/admin/official-accounts/{created.id}/delete",
                    follow_redirects=False,
                )
                assert delete_response.status_code == 302

            assert db.session.get(User, created.id) is None
            assert db.session.scalar(db.select(User).where(User.email == "official-0@example.com")) is None
        finally:
            db.session.rollback()
            db.drop_all()


def test_official_credentials_email_contains_login_id_email_and_temporary_password(monkeypatch):
    app = create_app("testing")
    sent = {}

    def fake_send(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr("app.admin.send_official_credentials", fake_send)
    with app.app_context():
        db.create_all()
        try:
            ensure_default_accounts()
            with app.test_client() as client:
                assert _login(client, "admin", "Admin@123456").status_code == 302
                assert _create_official(client, email="email-check@example.com").status_code == 302
            assert sent == {
                "recipient": "email-check@example.com",
                "full_name": "Juan Dela Cruz",
                "official_id": "SCN-OFF-000001",
                "temporary_password": "Test-random-temporary-credential!",
            }
        finally:
            db.session.rollback()
            db.drop_all()


def test_official_account_is_rolled_back_when_credentials_email_fails(monkeypatch):
    app = create_app("testing")

    def fail_send(**kwargs):
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr("app.admin.send_official_credentials", fail_send)
    with app.app_context():
        db.create_all()
        try:
            ensure_default_accounts()
            with app.test_client() as client:
                assert _login(client, "admin", "Admin@123456").status_code == 302
                response = _create_official(client, email="mail-fail@example.com")
                assert response.status_code == 200
                assert b"SMTP configuration" in response.data
            assert db.session.scalar(db.select(User).where(User.email == "mail-fail@example.com")) is None
        finally:
            db.session.rollback()
            db.drop_all()
