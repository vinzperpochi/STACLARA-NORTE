"""Blotter case workflow and reporting helpers."""

from __future__ import annotations

from calendar import month_name
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func

from app.extensions import db
from app.models import BlotterCase, BlotterCaseEvent, BlotterEndorsement, BlotterHearing, BlotterMediation, BlotterParty, BlotterSettlement

CASE_STATUSES = {"OPEN", "UNDER_MEDIATION", "HEARING_SCHEDULED", "SETTLED", "ENDORSED", "CLOSED"}
CASE_TRANSITIONS = {"OPEN": {"UNDER_MEDIATION", "HEARING_SCHEDULED", "ENDORSED", "CLOSED"}, "UNDER_MEDIATION": {"SETTLED", "HEARING_SCHEDULED", "ENDORSED", "CLOSED"}, "HEARING_SCHEDULED": {"UNDER_MEDIATION", "SETTLED", "ENDORSED", "CLOSED"}, "SETTLED": {"CLOSED"}, "ENDORSED": {"CLOSED"}, "CLOSED": set()}


def new_case_number() -> str:
    return f"BLT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def transition_case(case: BlotterCase, new_status: str, actor, notes: str | None = None) -> None:
    new_status = new_status.upper()
    if new_status not in CASE_STATUSES or new_status not in CASE_TRANSITIONS.get(case.status, set()):
        raise ValueError(f"Cannot change case status from {case.status} to {new_status}.")
    old_status = case.status; case.status = new_status
    if new_status == "CLOSED": case.closed_at = datetime.now(timezone.utc)
    db.session.add(BlotterCaseEvent(case_id=case.id, from_status=old_status, to_status=new_status, changed_by_id=actor.id, notes=notes))


def add_party(case: BlotterCase, name: str, role: str, contact: str | None = None, notes: str | None = None) -> BlotterParty:
    if not name.strip() or not role.strip(): raise ValueError("Party name and role are required.")
    party = BlotterParty(case=case, name=name.strip(), role=role.strip(), contact_information=contact.strip() if contact else None, notes=notes.strip() if notes else None)
    db.session.add(party); return party


def statistics() -> dict:
    category_rows = db.session.execute(db.select(BlotterCase.category, func.count(BlotterCase.id)).group_by(BlotterCase.category).order_by(BlotterCase.category)).all()
    purok_rows = db.session.execute(db.select(BlotterCase.purok_id, func.count(BlotterCase.id)).group_by(BlotterCase.purok_id).order_by(BlotterCase.purok_id)).all()
    monthly_counts: dict[str, int] = {}
    for incident_date in db.session.scalars(db.select(BlotterCase.incident_date).order_by(BlotterCase.incident_date)).all():
        key = incident_date.strftime("%Y-%m")
        monthly_counts[key] = monthly_counts.get(key, 0) + 1
    resolved = db.session.scalars(db.select(BlotterCase).where(BlotterCase.closed_at.is_not(None), BlotterCase.created_at.is_not(None))).all()
    resolution_days = [(case.closed_at.replace(tzinfo=timezone.utc) - case.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 86400 for case in resolved]
    return {"case_categories": {label: count for label, count in category_rows}, "number_of_cases": db.session.scalar(db.select(func.count(BlotterCase.id))) or 0, "average_resolution_days": round(sum(resolution_days) / len(resolution_days), 2) if resolution_days else None, "cases_per_purok": {str(purok or "unassigned"): count for purok, count in purok_rows}, "monthly_trends": monthly_counts}
