import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import EmergencyAlert, Household, Purok, Resident, Role, User
from seed_default_accounts import ensure_default_accounts


def test_default_admin_and_official_accounts_are_seeded():
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        ensure_default_accounts()

        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        official = db.session.scalar(db.select(User).where(User.username == "official"))

        assert admin is not None
        assert official is not None
        assert admin.is_active is True
        assert official.is_active is True
        assert {role.name for role in admin.roles} == {"System Administrator"}
        assert {role.name for role in official.roles} >= {"Barangay Official"}
        assert db.session.scalar(db.select(Role).where(Role.name == "System Administrator")) is not None
        assert db.session.scalar(db.select(Role).where(Role.name == "Barangay Official")) is not None


def test_new_emergency_alert_archives_previous_published_alert():
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        ensure_default_accounts()

        previous = EmergencyAlert(
            title="Old alert",
            message="Previous message",
            alert_level="ADVISORY",
            issued_at=datetime.now(timezone.utc),
            status="PUBLISHED",
        )
        db.session.add(previous)
        db.session.commit()

        official = db.session.scalar(db.select(User).where(User.username == "official"))
        assert official is not None

        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"role": "staff", "identifier": "official", "password": "Official@123456"},
                follow_redirects=False,
            )
            response = client.post(
                "/official/drrm/alerts",
                data={
                    "title": "New alert",
                    "message": "Latest message",
                    "alert_level": "CRITICAL",
                    "expires_at": "",
                },
                follow_redirects=False,
            )
            assert response.status_code == 302

        published = db.session.scalars(db.select(EmergencyAlert).where(EmergencyAlert.status == "PUBLISHED")).all()
        archived = db.session.scalars(db.select(EmergencyAlert).where(EmergencyAlert.status == "ARCHIVED")).all()

        assert len(published) == 1
        assert published[0].title == "New alert"
        assert any(alert.title == "Old alert" for alert in archived)


def test_resident_emergency_alerts_are_paginated():
    app = create_app("testing")

    with app.app_context():
        db.create_all()

        resident_role = db.session.scalar(db.select(Role).where(Role.name == "Resident"))
        if resident_role is None:
            resident_role = Role(name="Resident", description="Resident access")
            db.session.add(resident_role)

        purok = Purok(name="Purok 1", description="Test purok", status="ACTIVE")
        db.session.add(purok)
        db.session.flush()

        household = Household(household_number="H-001", address_line="Test address", purok_id=purok.id, status="ACTIVE")
        db.session.add(household)
        db.session.flush()

        resident = Resident(
            first_name="Maria",
            last_name="Dela Cruz",
            household_id=household.id,
            purok_id=purok.id,
            sex="F",
            birth_date=datetime(2000, 1, 1).date(),
            civil_status="Single",
            status="active",
            is_verified=True,
        )
        db.session.add(resident)
        db.session.flush()

        user = User(username="resident_paged", email="resident_paged@example.com", status="active", is_active=True)
        user.set_password("Resident@123456")
        user.roles.append(resident_role)
        user.resident_id = resident.id
        db.session.add(user)

        for idx in range(13):
            db.session.add(
                EmergencyAlert(
                    title=f"Alert {idx}",
                    message=f"Message {idx}",
                    alert_level="ADVISORY",
                    issued_at=datetime.now(timezone.utc),
                    status="PUBLISHED",
                )
            )

        db.session.commit()

        with app.test_client() as client:
            login = client.post(
                "/auth/login",
                data={"role": "resident", "identifier": "resident_paged", "password": "Resident@123456"},
                follow_redirects=False,
            )
            assert login.status_code == 302

            page_one = client.get("/resident/emergency-alerts?page=1")
            page_two = client.get("/resident/emergency-alerts?page=2")

            assert page_one.status_code == 200
            assert page_two.status_code == 200
            assert b"Page 1 of 3" in page_one.data
            assert b"Page 2 of 3" in page_two.data
            assert b"Previous" in page_two.data
            assert b"Next" in page_two.data
