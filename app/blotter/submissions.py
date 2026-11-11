"""Transaction-local case submission with conservative exact-incident association."""
from datetime import date, datetime
from hashlib import sha256
import json
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import BlotterCase, BlotterCaseEvent, Notification, Role, User
from app.normalization import clean_text
from app.audit import record
from .workflow import add_party, new_case_number

ACTIVE_STATUSES = {'OPEN', 'UNDER_MEDIATION', 'HEARING_SCHEDULED'}


def incident_fingerprint(values):
    # Missing location leaves too much uncertainty; keep those submissions separate.
    if not clean_text(values.get('incident_location')) or not clean_text(values.get('narrative')):
        return None
    keys = ('complainant_id', 'respondent_name', 'category', 'incident_date', 'incident_datetime', 'incident_location', 'purok_id', 'narrative', 'incident_latitude', 'incident_longitude')
    normalized = []
    for key in keys:
        value = values.get(key)
        if isinstance(value, str):
            value = clean_text(value).casefold()
        elif isinstance(value, (datetime, date)):
            value = value.isoformat()
        elif value is not None:
            value = str(value)
        normalized.append(value)
    return sha256(json.dumps(normalized, ensure_ascii=True).encode()).hexdigest()


def submit_case(values, actor, contact=None, notes=None):
    """Return (case, associated); caller commits case, notifications and audit together."""
    fingerprint = incident_fingerprint(values)
    existing = db.session.scalar(db.select(BlotterCase).where(BlotterCase.incident_fingerprint == fingerprint)) if fingerprint else None
    if existing is None:
        try:
            with db.session.begin_nested():
                case = BlotterCase(**values, incident_fingerprint=fingerprint, case_number=new_case_number(), status='OPEN')
                db.session.add(case)
                db.session.flush()
                # Database primary-key allocation supplies a monotonic reference without COUNT()+1 races.
                case.case_number = f'BLT-{case.id:08d}'
                db.session.flush()
                add_party(case, values['respondent_name'], 'RESPONDENT', contact, notes)
        except IntegrityError:
            # A simultaneous identical submission may have won the unique fingerprint.
            existing = db.session.scalar(db.select(BlotterCase).where(BlotterCase.incident_fingerprint == fingerprint)) if fingerprint else None
            if existing is None:
                raise
    associated = existing is not None
    case = existing if associated else case
    db.session.add(BlotterCaseEvent(case_id=case.id, from_status=case.status if associated else None, to_status=case.status, changed_by_id=actor.id, notes='Identical incident submission associated with original case; original preserved.' if associated else 'Complaint filed by resident.'))
    record('BLOTTER_ASSOCIATE' if associated else 'BLOTTER_CREATE', 'blotter', 'BlotterCase', case.id, 'Exact-incident association' if associated else 'Complaint created')
    db.session.add(Notification(user_id=actor.id, title='Complaint submission received', message=f'Your submission is associated with {case.case_number}.' if associated else f'Complaint {case.case_number} was filed.', status='active'))
    if not associated:
        officials = db.session.scalars(db.select(User).join(User.roles).where(Role.name.in_(['Barangay Official', 'System Administrator']), User.is_active.is_(True), User.status == 'active').distinct()).all()
        for user in officials:
            db.session.add(Notification(user_id=user.id, title='New complaint', message=f'Complaint {case.case_number} is waiting for review.', status='active'))
    return case, associated


def queue_position(case):
    if case.status not in ACTIVE_STATUSES:
        return None
    return db.session.scalar(db.select(func.count(BlotterCase.id)).where(BlotterCase.status.in_(ACTIVE_STATUSES), BlotterCase.id <= case.id))
