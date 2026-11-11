"""Explicit account/personnel links shared by account creation and maintenance.

Callers own the transaction. No RFID, schedule, or attendance rows are created
here, and names alone never grant access to an existing personnel record.
"""
from uuid import uuid4

from sqlalchemy import select, func

from app.extensions import db
from app.models import User, PersonnelProfile, AttendanceAuditLog


ACCOUNT_ROLES = {"system administrator", "barangay official"}


def personnel_choices():
    people = db.session.scalars(
        select(PersonnelProfile).where(PersonnelProfile.user_id.is_(None))
        .order_by(PersonnelProfile.full_name, PersonnelProfile.id)
    ).all()
    return [("", "Create a new personnel record")] + [
        (person.id, f"{person.full_name} · {person.employee_id}" + (" · Inactive" if not person.active else ""))
        for person in people
    ]


def provision_account_personnel(account, *, personnel_id=None, full_name=None, position=None, actor_id=None):
    """Create a linked profile or explicitly claim one unused existing profile."""
    db.session.flush()
    eligible = any(role.status == "active" and role.name.casefold() in ACCOUNT_ROLES for role in account.roles)
    if not eligible:
        if personnel_id:
            raise ValueError("Only admin/official accounts can have an attendance personnel link.")
        return None

    # All account-link entry points lock the user before the personnel record.
    db.session.scalar(select(User).where(User.id == account.id).with_for_update())
    linked = db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.user_id == account.id))
    if linked:
        if personnel_id and linked.id != int(personnel_id):
            raise ValueError("This account already has a different personnel record.")
        return linked

    if personnel_id:
        person = db.session.scalar(
            select(PersonnelProfile).where(PersonnelProfile.id == int(personnel_id))
            .with_for_update().execution_options(populate_existing=True)
        )
        if not person or person.user_id is not None:
            raise ValueError("That personnel record is already linked or no longer available. Choose an unused record.")
        person.user = account
        action = "PERSONNEL_ACCOUNT_LINKED"
    else:
        official = account.official
        resident = account.resident
        resident_name = " ".join(filter(None, [resident.first_name, resident.middle_name, resident.last_name, resident.suffix])) if resident else None
        name = " ".join((full_name or (official.full_name if official else None)
                         or resident_name or account.username).split())
        # Prompt the administrator to choose the intended record, including when
        # several people share a name. Never silently attach another person's data.
        existing = db.session.scalar(
            select(PersonnelProfile.id).where(PersonnelProfile.user_id.is_(None),
                func.lower(func.trim(PersonnelProfile.full_name)) == name.lower()).limit(1)
        )
        if existing:
            raise ValueError("An unlinked personnel record already has this name. Select it under Attendance personnel record to keep its RFID and attendance history.")
        person = PersonnelProfile(
            user=account, employee_id="ACCOUNT-" + uuid4().hex[:12].upper(),
            full_name=name, position=position or (official.position if official else "System Administrator"),
            personnel_type="Official", email=account.email,
            mobile=official.contact_number if official else None, active=True,
        )
        db.session.add(person)
        action = "ACCOUNT_PERSONNEL_CREATED"
    db.session.flush()
    db.session.add(AttendanceAuditLog(
        actor_id=actor_id, entity_id=person.id, action=action,
        details=f"Personnel #{person.id} linked to account #{account.id}; existing RFID, schedules and attendance history retained.",
    ))
    return person
