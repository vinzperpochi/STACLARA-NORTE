from datetime import date, datetime, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import Resident, Role, User
from seed_default_accounts import ensure_default_accounts


def _resident_user(email="maria@example.com", verified=True):
    resident_role = db.session.scalar(db.select(Role).where(Role.name == "Resident"))
    if resident_role is None:
        resident_role = Role(name="Resident", description="Resident access")
        db.session.add(resident_role)
    resident = Resident(
        first_name="Maria",
        last_name="Santos",
        email=email,
        birth_date=date(1990, 5, 6),
        status="pending",
        is_verified=False,
    )
    user = User(
        username="PENDING-test",
        email=email,
        status="pending",
        is_active=False,
        resident=resident,
        email_verified_at=datetime.now(timezone.utc) if verified else None,
    )
    user.set_password("random-unusable-pending-password")
    user.roles.append(resident_role)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, identifier, password):
    return client.post(
        "/auth/login",
        data={"role": {"admin": "captain", "official": "staff"}.get(identifier, "resident"), "identifier": identifier, "password": password},
        follow_redirects=False,
    )


def test_registration_is_pending_and_public_activation_link_is_inert(monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_verification_email", lambda **kwargs: None)
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            response = client.post(
                "/auth/register",
                data={
                    "first_name": "Maria",
                    "last_name": "Santos",
                    "birth_date": "1990-05-06",
                    "email": "maria@example.com",
                    "privacy_consent": "y",
                    "terms_consent": "y",
                    # These submitted fields must be ignored; residents cannot pick credentials.
                    "username": "chosen_username",
                    "password": "Resident@123456",
                    "password_confirmation": "Resident@123456",
                },
            )
            assert response.status_code == 200
            assert b"pending" in response.data.lower()
            assert b"maria@example.com" in response.data

            user = db.session.scalar(db.select(User).where(User.email == "maria@example.com"))
            assert user is not None
            assert user.status == "pending"
            assert user.is_active is False
            assert user.username.startswith("PENDING-")
            assert user.check_password("Resident@123456") is False
            user.set_password("KnownPendingPass@123")
            db.session.commit()

            blocked_login = _login(client, "maria@example.com", "KnownPendingPass@123")
            assert blocked_login.status_code == 403
            legacy_link = client.get("/auth/activate/legacy-token", follow_redirects=False)
            assert legacy_link.status_code == 302
            db.session.refresh(user)
            assert user.status == "pending"
            assert user.is_active is False


def test_official_can_approve_verified_resident_with_random_credentials(monkeypatch):
    app = create_app("testing")
    calls = []
    monkeypatch.setattr("app.official.send_resident_credentials", lambda **kw: calls.append(kw))
    with app.app_context():
        db.create_all()
        ensure_default_accounts()
        user = _resident_user()
        with app.test_client() as client:
            assert _login(client, "official", "Official@123456").status_code == 302
            assert client.post(f"/official/account-approvals/{user.id}/approve").status_code == 302
        db.session.refresh(user)
        assert user.is_active and user.status == "active"
        assert user.must_change_password and user.resident.is_verified
        assert len(calls) == 1 and calls[0]['recipient'] == user.email
        password = calls[0]['temporary_password']
        assert len(password) >= 18 and password != '19900506'
        assert user.check_password(password)
        assert not user.check_password('19900506')
        with app.test_client() as client:
            response = _login(client, user.username, password)
            assert response.status_code == 302
            assert response.headers['Location'].endswith('/auth/change-password')


def test_non_staff_cannot_open_approval_queue_or_activate_accounts():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        resident_user = _resident_user("blocked@example.com")
        resident_user.is_active = True
        resident_user.status = "active"
        resident_user.set_password("Resident@123456")
        db.session.commit()
        with app.test_client() as client:
            _login(client, resident_user.username, "Resident@123456")
            response = client.get("/official/account-approvals")
            assert response.status_code == 403
            response = client.post(f"/official/account-approvals/{resident_user.id}/approve")
            assert response.status_code == 403
        db.session.refresh(resident_user)
        assert resident_user.status == "active"
        assert resident_user.username.startswith("PENDING-")
        assert resident_user.must_change_password is False


def test_admin_generic_user_toggle_cannot_bypass_resident_approval(monkeypatch):
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        ensure_default_accounts()
        user = _resident_user("admin-toggle@example.com")
        with app.test_client() as client:
            assert _login(client, "admin", "Admin@123456").status_code == 302
            users_page = client.get("/admin/users")
            assert users_page.status_code == 200
            assert b"Review registration" in users_page.data
            response = client.post(f"/admin/users/{user.id}/toggle")
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/official/account-approvals")
        db.session.refresh(user)
        assert user.status == "pending"
        assert user.is_active is False
        assert user.username.startswith("PENDING-")


def test_email_failure_rolls_back_activation(monkeypatch):
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        ensure_default_accounts()
        user = _resident_user("mailfail@example.com")

        def fail_send(**kwargs):
            raise RuntimeError("SMTP unavailable")

        monkeypatch.setattr("app.official.send_resident_credentials", fail_send)
        with app.test_client() as client:
            _login(client, "official", "Official@123456")
            client.post(f"/official/account-approvals/{user.id}/approve")
        db.session.refresh(user)
        assert user.is_active is False
        assert user.status == "pending"  # Rolled back to pending
        assert user.username.startswith("PENDING-")
        assert user.must_change_password is False


def test_smtp_helper_builds_email_for_registered_address(monkeypatch):
    from app.email_service import send_resident_credentials, send_smtp_test

    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            assert host == "smtp.test.local"
            assert port == 587

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("app.email_service.smtplib.SMTP", FakeSMTP)
    app = create_app("testing")
    app.config.update(
        SMTP_HOST="smtp.test.local",
        SMTP_PORT=587,
        SMTP_FROM_EMAIL="no-reply@example.com",
        SMTP_FROM_NAME="Test Barangay",
        SMTP_USERNAME="",
        SMTP_PASSWORD="",
        SMTP_STARTTLS=False,
        SMTP_USE_SSL=False,
    )
    with app.app_context():
        send_resident_credentials(
            recipient="resident@example.com",
            full_name="Maria Santos",
            resident_id="SCN-RES-000001",
            temporary_password="19900506",
        )
        send_smtp_test(recipient="operator@example.com")

    assert len(sent_messages) == 2
    assert sent_messages[0]["To"] == "resident@example.com"
    body = sent_messages[0].get_content()
    assert "SCN-RES-000001" in body
    assert "19900506" in body
    assert sent_messages[1]["To"] == "operator@example.com"
    assert "SMTP test successful" in sent_messages[1].get_content()
    assert "SCN-RES-000001" not in sent_messages[1].get_content()
    assert "19900506" not in sent_messages[1].get_content()


def test_gmail_requires_account_and_app_password_before_connecting():
    from app.email_service import send_smtp_test

    app = create_app("testing")
    app.config.update(
        SMTP_HOST="smtp.gmail.com",
        SMTP_PORT=587,
        SMTP_USERNAME="operator@gmail.com",
        SMTP_PASSWORD="",
        SMTP_FROM_EMAIL="operator@gmail.com",
        SMTP_STARTTLS=True,
        SMTP_USE_SSL=False,
    )
    with app.app_context(), pytest.raises(RuntimeError, match="Google App Password"):
        send_smtp_test(recipient="operator@gmail.com")


def _register(client, email="maria@example.com"):
    return client.post(
        "/auth/register",
        data={
            "first_name": "Maria",
            "last_name": "Santos",
            "birth_date": "1990-05-06",
            "email": email,
            "privacy_consent": "y",
                    "terms_consent": "y",
        },
    )


def test_registration_sends_verification_link_and_verifying_does_not_activate(monkeypatch):
    sent = []
    monkeypatch.setattr("app.auth.routes.send_verification_email", lambda **kw: sent.append(kw))
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            assert _register(client).status_code == 200
            assert len(sent) == 1
            assert sent[0]["recipient"] == "maria@example.com"
            url = sent[0]["verification_url"]
            assert "/auth/verify-email/" in url

            user = db.session.scalar(db.select(User).where(User.email == "maria@example.com"))
            assert user.email_verified_at is None

            path = "/auth/verify-email/" + url.rsplit("/", 1)[1]
            assert client.get(path).status_code == 200
            db.session.refresh(user)
            assert user.email_verified_at is not None
            assert user.status == "pending"
            assert user.is_active is False

            # Link is single-use.
            assert client.get(path).status_code == 400


def test_registration_survives_smtp_failure_and_offers_resend(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr("app.auth.routes.send_verification_email", fail)
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            response = _register(client)
            assert response.status_code == 200
            assert b"hindi naipadala ang verification email" in response.data.lower()
            assert db.session.scalar(db.select(User).where(User.email == "maria@example.com")) is not None


def test_resend_respects_cooldown_and_hides_unknown_emails(monkeypatch):
    sent = []
    monkeypatch.setattr("app.auth.routes.send_verification_email", lambda **kw: sent.append(kw))
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            _register(client)
            assert len(sent) == 1
            client.post("/auth/resend-verification", data={"email": "maria@example.com"})
            assert len(sent) == 1  # inside the cooldown window
            app.config["EMAIL_VERIFICATION_RESEND_SECONDS"] = 0
            client.post("/auth/resend-verification", data={"email": "maria@example.com"})
            assert len(sent) == 2
            response = client.post("/auth/resend-verification", data={"email": "nobody@example.com"})
            assert response.status_code == 200
            assert len(sent) == 2


def test_approval_requires_email_verification_and_never_manufactures_it(monkeypatch):
    app = create_app("testing")
    calls = []
    monkeypatch.setattr("app.official.send_resident_credentials", lambda **kw: calls.append(kw))
    with app.app_context():
        db.create_all()
        ensure_default_accounts()
        user = _resident_user("unverified@example.com", verified=False)
        with app.test_client() as client:
            _login(client, "official", "Official@123456")
            assert client.post(f"/official/account-approvals/{user.id}/approve").status_code == 302
        db.session.refresh(user)
        assert user.status == "pending" and not user.is_active
        assert user.email_verified_at is None
        assert not calls


def test_verification_email_helper_contains_link(monkeypatch):
    from app.email_service import send_verification_email

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            return None

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("app.email_service.smtplib.SMTP", FakeSMTP)
    app = create_app("testing")
    app.config.update(SMTP_HOST="smtp.test.local", SMTP_PORT=587, SMTP_FROM_EMAIL="no-reply@example.com",
                      SMTP_USERNAME="", SMTP_PASSWORD="", SMTP_STARTTLS=False, SMTP_USE_SSL=False)
    with app.app_context():
        send_verification_email(recipient="r@example.com", full_name="Maria Santos",
                                verification_url="http://x/auth/verify-email/abc", valid_hours=24)
    assert sent[0]["To"] == "r@example.com"
    assert "http://x/auth/verify-email/abc" in sent[0].get_content()
