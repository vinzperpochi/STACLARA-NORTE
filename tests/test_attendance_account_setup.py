"""New logins keep one personnel identity and see old and new RFID attendance."""
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.extensions import db
from app.models import User, Role, Official, PersonnelProfile, AttendanceSession, RFIDCard
from app.attendance.service import MANILA
from test_system_integrity import system, login
from test_attendance_operations import roster, scan_at
from test_attendance_lists import rendered
from test_rfid_registration import FIRST_SCHEDULE, start


DAY = date(2026, 11, 5)
PASSWORD = "Temporary-Test-Password-123!"


@pytest.fixture
def mail(monkeypatch):
    sender = Mock()
    monkeypatch.setattr("app.admin.send_official_credentials", sender)
    monkeypatch.setattr("app.admin.secrets", SimpleNamespace(token_urlsafe=lambda size: PASSWORD))
    return sender


def create_official(client, **overrides):
    data = dict(email="new-official@example.com", full_name="New Official",
                position="Barangay Kagawad", birth_date="1990-01-01", term_start="2026-01-01")
    data.update(overrides)
    return client.post("/admin/official-accounts", data=data)


def activate_test_login(email="new-official@example.com"):
    account = db.session.scalar(db.select(User).where(User.email == email))
    assert account.must_change_password  # Real users still complete first-login password change.
    account.must_change_password = False
    account.email_verified_at = datetime.now(timezone.utc)
    db.session.commit()
    return account


def official_login(application, username):
    client = application.test_client()
    response = client.post("/auth/login", data={"identifier": username, "password": PASSWORD})
    assert response.status_code == 302
    return client


def history(person, schedule):
    record = AttendanceSession(personnel_id=person.id, schedule_id=schedule.id, work_date=DAY,
        time_in=datetime.combine(DAY, time(8), MANILA), time_out=datetime.combine(DAY, time(8, 10), MANILA))
    db.session.add(record)
    db.session.commit()
    return record


def test_explicit_existing_record_link_shows_historical_attendance_and_reports(system, roster, mail):
    person, schedule, *_ = roster
    person.user = None
    record = history(person, schedule)
    saved = (person.id, person.cards[0].id, schedule.id, record.id, record.time_in, record.time_out)
    admin = login(system, "admin-test")
    response = create_official(admin, full_name=person.full_name, attendance_personnel_id=person.id)
    assert response.status_code == 302
    account = activate_test_login()
    db.session.refresh(person)
    assert person.user_id == account.id
    assert saved == (person.id, person.cards[0].id, schedule.id, record.id, record.time_in, record.time_out)
    assert db.session.scalar(db.select(db.func.count(PersonnelProfile.id))) == 1
    staff = official_login(system, account.username)
    with rendered(system) as contexts:
        page = staff.get(f"/attendance/?date={DAY}")
    assert page.status_code == 200 and page.cache_control.no_store
    assert contexts[-1]["stats"]["Present"] == 1
    assert [(row["person"].id, row["status"]) for row in contexts[-1]["rows"]] == [(person.id, "Present")]
    with rendered(system) as contexts:
        page = staff.get(f"/attendance/reports?start_date={DAY}&end_date={DAY}")
    assert page.status_code == 200 and contexts[-1]["rows"][0]["status"] == "Present"
    assert staff.get(f"/attendance/reports?start_date={DAY}&end_date={DAY}&format=csv").data.count(b"Present") == 1
    assert [role.name for role in account.roles] == ["Barangay Official"]


def test_new_account_reuses_auto_linked_profile_on_enrollment_and_updates_only_own_view(system, roster, mail):
    # Keep live scan events inside the offline window; the history test above
    # separately fixes the November 5, 2026 regression date.
    scan_day = datetime.now(MANILA).date() - timedelta(days=1)
    admin = login(system, "admin-test")
    assert create_official(admin).status_code == 302
    account = activate_test_login()
    person = db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.user_id == account.id))
    person_id = person.id
    assert person.full_name == "New Official" and not person.cards and not person.schedules
    staff = official_login(system, account.username)
    with rendered(system) as contexts:
        staff.get(f"/attendance/?date={scan_day}")
    assert contexts[-1]["stats"]["Present"] == 0
    assert {row["person"].id for row in contexts[-1]["rows"]} == {person_id}
    token = start(admin, roster[2])
    assert system.test_client().post("/attendance/api/registration-tap", headers=roster[3],
        json={"capture_id": token, "uid": "11223344"}).json["success"]
    response = admin.post("/attendance/devices", data={**FIRST_SCHEDULE,
        "action": "register_card", "account_mode": "existing", "user_id": account.id,
        "capture_id": token, "first_name": "New", "last_name": "Official",
        "barangay_role": "Barangay Kagawad", "start_time": "08:00", "end_time": "17:00",
        "effective_from": str(scan_day), "weekdays": ["0", "1", "2", "3", "4", "5", "6"]})
    assert response.status_code == 302
    db.session.expire_all()
    person = db.session.get(PersonnelProfile, person_id)
    assert person.user_id == account.id and len(person.cards) == len(person.schedules) == 1
    assert db.session.scalar(db.select(db.func.count(PersonnelProfile.id))) == 2
    assert scan_at(system, roster, datetime.combine(scan_day, time(8), MANILA), "new-account-in", uid="11223344").json["action"] == "IN"
    assert scan_at(system, roster, datetime.combine(scan_day, time(8, 10), MANILA), "new-account-out", uid="11223344").json["action"] == "OUT"
    with rendered(system) as contexts:
        staff.get(f"/attendance/?date={scan_day}")
    assert contexts[-1]["stats"]["Present"] == 1
    assert [(row["person"].id, row["status"]) for row in contexts[-1]["rows"]] == [(person_id, "Present")]
    with rendered(system) as contexts:
        login(system, "staff-test").get(f"/attendance/?date={scan_day}")
    assert contexts[-1]["stats"]["Present"] == 0
    assert {row["person"].id for row in contexts[-1]["rows"]} == {roster[0].id}


def test_matching_name_requires_explicit_record_selection_before_sending_credentials(system, roster, mail):
    person = roster[0]
    person.user = None
    db.session.commit()
    response = create_official(login(system, "admin-test"), full_name=person.full_name)
    assert response.status_code == 200 and b"Select it under Attendance personnel record" in response.data
    assert db.session.scalar(db.select(User).where(User.email == "new-official@example.com")) is None
    assert db.session.scalar(db.select(db.func.count(Official.id))) == 0
    db.session.refresh(person)
    assert person.user_id is None and len(person.cards) == 1
    mail.assert_not_called()


def test_account_email_failure_rolls_back_personnel_link_and_preserves_history(system, roster, mail):
    person, schedule, *_ = roster
    person.user = None
    record = history(person, schedule)
    mail.side_effect = RuntimeError("SMTP unavailable")
    response = create_official(login(system, "admin-test"), full_name=person.full_name,
                               attendance_personnel_id=person.id)
    assert response.status_code == 200
    db.session.refresh(person)
    assert person.user_id is None and len(person.cards) == 1
    assert db.session.get(AttendanceSession, record.id) is not None
    assert db.session.scalar(db.select(User).where(User.email == "new-official@example.com")) is None


def test_existing_account_owner_cannot_be_reassigned_by_a_forged_creation_form(system, roster, mail):
    person = roster[0]
    owner = person.user_id
    response = create_official(login(system, "admin-test"), attendance_personnel_id=person.id)
    assert response.status_code == 200
    db.session.refresh(person)
    assert person.user_id == owner
    assert db.session.scalar(db.select(User).where(User.email == "new-official@example.com")) is None
    mail.assert_not_called()


@pytest.mark.parametrize("role_name", ["System Administrator", "Resident"])
def test_generic_new_admin_is_prelinked_but_resident_has_no_attendance_profile(system, mail, role_name):
    role = db.session.scalar(db.select(Role).where(Role.name == role_name))
    response = login(system, "admin-test").post("/admin/users", data={
        "username": "new-account", "email": "new-account@example.com", "password": PASSWORD,
        "confirm_password": PASSWORD, "role_id": role.id, "is_active": "y"})
    assert response.status_code == 302
    account = db.session.scalar(db.select(User).where(User.username == "new-account"))
    person = db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.user_id == account.id))
    assert bool(person) == (role_name == "System Administrator")
    assert [r.name for r in account.roles] == [role_name]
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id))) == 0


def test_deleting_login_keeps_linked_rfid_and_attendance_history(system, roster, mail):
    person, schedule, *_ = roster
    person.user = None
    record = history(person, schedule)
    admin = login(system, "admin-test")
    assert create_official(admin, full_name=person.full_name, attendance_personnel_id=person.id).status_code == 302
    account = db.session.scalar(db.select(User).where(User.email == "new-official@example.com"))
    card_id = person.cards[0].id
    assert admin.post(f"/admin/official-accounts/{account.id}/delete").status_code == 302
    db.session.refresh(person)
    assert person.user_id is None
    assert db.session.get(RFIDCard, card_id).personnel_id == person.id
    assert db.session.get(AttendanceSession, record.id).personnel_id == person.id


def test_resident_creation_cannot_claim_an_existing_attendance_record(system, roster):
    person = roster[0]
    person.user = None
    db.session.commit()
    role = db.session.scalar(db.select(Role).where(Role.name == "Resident"))
    response = login(system, "admin-test").post("/admin/users", data={
        "username": "forged-resident", "email": "forged-resident@example.com", "password": PASSWORD,
        "confirm_password": PASSWORD, "role_id": role.id, "is_active": "y", "attendance_personnel_id": person.id})
    assert response.status_code == 200
    assert b"Only admin/official accounts" in response.data
    assert db.session.scalar(db.select(User).where(User.username == "forged-resident")) is None
    db.session.refresh(person)
    assert person.user_id is None


def test_existing_unlinked_official_gets_actionable_notice_instead_of_silent_empty_view(system):
    page = login(system, "staff-test").get(f"/attendance/?date={DAY}")
    assert page.status_code == 200
    assert b"Attendance account setup needed" in page.data
    assert b"Ask the Super Admin to link your existing record" in page.data
