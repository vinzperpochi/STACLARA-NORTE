"""Reusable document-request workflow services."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import current_app

from app.extensions import db
from app.models import DocumentRequestEvent, DocumentType, IssuedDocument, Notification, Request, Resident
from .verification import qr_data_uri, verification_url
from .engine import template_code, next_number, expiry, snapshot_data, render_original, active_signatories, fields_for, TEMPLATE_CODES

SUPPORTED_DOCUMENTS = {
    "BARANGAY_CLEARANCE": ("Barangay Clearance", ["Valid government-issued ID"]),
    "CERTIFICATE_RESIDENCY": ("Certificate of Residency", ["Valid government-issued ID", "Proof of address", "Community Tax Certificate (cedula)", "1 pc. 1x1 recent ID photo"]),
    "CERTIFICATE_INDIGENCY": ("Certificate of Indigency", ["Valid government-issued ID", "Proof of residency"]),
    "CERTIFICATE_GOOD_MORAL": ("Certificate of Good Moral Character", ["Valid government-issued ID", "Community Tax Certificate (cedula)", "Request letter / requirement of agency", "1 pc. 1x1 recent ID photo"]),
    "BUSINESS_CLEARANCE": ("Barangay Business Permit / Business Clearance", ["DTI / SEC / CDA registration", "Valid ID of owner / operator", "Contract of lease / title / owner's consent", "Community Tax Certificate (cedula)", "Location sketch of the establishment"]),
    "FIRST_TIME_JOBSEEKER": ("First-Time Jobseeker Certificate", ["Valid ID or proof of identity", "Proof of residency", "First-time jobseeker signed oath / affidavit", "1 pc. 1x1 recent ID photo"]),
    "SOLO_PARENT_ENDORSEMENT": ("Solo Parent Endorsement", ["Valid government-issued ID", "PSA birth certificate of each child", "Proof of solo status (death cert. / affidavit / court order)", "Proof of residency", "2 pcs. 1x1 recent ID photos", "Barangay certification of residency"]),
}
ALLOWED_TRANSITIONS = {
 "PENDING":{"UNDER_REVIEW"}, "UNDER_REVIEW":{"PROCESSING","NEEDS_CORRECTION","APPROVED","REJECTED"},
 "PROCESSING":{"NEEDS_CORRECTION","APPROVED","REJECTED"}, "NEEDS_CORRECTION":{"PENDING","UNDER_REVIEW"},
 "APPROVED":{"READY_FOR_PRINTING"}, "READY_FOR_PRINTING":{"PRINTED"}, "PRINTED":{"PRINTED","RELEASED"},
 "READY_FOR_RELEASE":{"PRINTED","RELEASED"},
}
REQUIREMENT_EXTENSIONS = {"jpg", "jpeg", "png"}

RETIRED_CLEARANCE_REQUIREMENTS = {"Community Tax Certificate (cedula)", "2 pcs. 1x1 recent ID photos"}
RETIRED_INDIGENCY_REQUIREMENTS = {"Supporting document (medical abstract, request letter, etc.)", "1 pc. 1x1 recent ID photo"}


def is_retired_requirement(item, name):
    if not item.document_type:
        return False
    retired = {"SCN-CLR": RETIRED_CLEARANCE_REQUIREMENTS, "SCN-IND": RETIRED_INDIGENCY_REQUIREMENTS}
    return name in retired.get(template_code(item.document_type), set())


def active_requirements(item):
    """Apply the current checklist to legacy requests without deleting evidence."""
    return [e for e in item.requirements if not is_retired_requirement(item, e.requirement_name)]


def evidence_source(evidence):
    """Prefer this request's upload; otherwise reuse its resident's registration ID."""
    if evidence.filename:
        return "document_requirements", evidence.filename
    resident = evidence.request.resident
    if evidence.requirement_name in {"Valid government-issued ID", "Valid ID or proof of identity", "Valid ID of owner / operator"}:
        return "registration_documents", resident.philsys_card_filename
    if evidence.requirement_name.startswith("Proof of residency") or evidence.requirement_name == "Proof of address":
        return "registration_documents", resident.proof_of_residency_filename
    return "document_requirements", None


def evidence_available(evidence):
    folder, filename = evidence_source(evidence)
    from app.private_storage import private_image_path
    return private_image_path(folder,filename) is not None


def ensure_catalog() -> list[DocumentType]:
    existing = {item.code: item for item in db.session.scalars(db.select(DocumentType)).all()}
    changed = False
    for code, (name, _requirements) in SUPPORTED_DOCUMENTS.items():
        if code not in existing:
            item = DocumentType(code=code, name=name, description=f"Resident document: {name}", template_code=TEMPLATE_CODES[code], base_fee=0, validity_days=(365 if code in {"FIRST_TIME_JOBSEEKER","SOLO_PARENT_ENDORSEMENT"} else 183), status="active")
            dialect=db.session.get_bind().dialect.name
            if dialect=='postgresql': from sqlalchemy.dialects.postgresql import insert
            else: from sqlalchemy.dialects.sqlite import insert
            statement=insert(DocumentType).values(code=code,name=name,description=item.description,template_code=item.template_code,base_fee=0,validity_days=item.validity_days,status='active')
            db.session.execute(statement.on_conflict_do_nothing(index_elements=['code']))
            changed = True
    if changed: db.session.commit()
    if changed: existing={item.code:item for item in db.session.scalars(db.select(DocumentType)).all()}
    return sorted(existing.values(), key=lambda item: item.name)


def requirement_names(code: str, details=None, resident=None) -> list[str]:
    from .engine import TEMPLATE_CODES
    legacy=next((old for old,new in TEMPLATE_CODES.items() if new==code),code)
    if legacy not in SUPPORTED_DOCUMENTS: raise ValueError('This document has no configured requirement checklist.')
    names=list(SUPPORTED_DOCUMENTS[legacy][1])
    if legacy=='BUSINESS_CLEARANCE' and (details or {}).get('application_type')=='Renewal': names.append('Previous Barangay Permit (for renewal)')
    if legacy=='BARANGAY_CLEARANCE' and resident and not resident.is_verified: names.append('Proof of residency (if not in the verified registry)')
    return names


def notify_resident(request_record: Request, title: str, message: str) -> None:
    if request_record.resident.user:
        db.session.add(Notification(user_id=request_record.resident.user.id, title=title, message=message, status="active"))


def transition_request(request_record: Request, new_status: str, actor, notes: str | None = None, *, approval_only=False) -> None:
    if notes and len(notes)>2000: raise ValueError('Status notes must not exceed 2000 characters.')
    old_status = request_record.status
    if old_status == "PENDING" and new_status == "APPROVED":
        raise ValueError("Begin review and save verification before approving this request.")
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()): raise ValueError(f"Cannot change status from {old_status} to {new_status}.")
    if new_status in {"PROCESSING", "APPROVED"}:
        missing = [r.requirement_name for r in active_requirements(request_record) if r.is_required and (not evidence_available(r) or r.status not in {"verified", "approved"})]
        if missing: raise ValueError("Verify all required evidence before approval: " + ", ".join(missing))
    if new_status == "APPROVED":
        validate_approval(request_record, require_complete=not approval_only)
        request_record.approved_by_id=actor.id;request_record.approved_at=datetime.now(timezone.utc)
    if new_status == "NEEDS_CORRECTION":
        if not notes: raise ValueError("Correction instructions are required.")
        request_record.verified_at=None;request_record.verified_by_id=None
    request_record.status = new_status
    if new_status in {"UNDER_REVIEW", "PROCESSING", "APPROVED", "REJECTED"}:
        request_record.reviewed_by_id = actor.id; request_record.reviewed_at = datetime.now(timezone.utc)
    db.session.add(DocumentRequestEvent(request_id=request_record.id, from_status=old_status, to_status=new_status, changed_by_id=actor.id, notes=notes))
    notify_resident(request_record, f"Document request {request_record.request_number} updated", f"Your request is now {new_status.replace('_', ' ').title()}.")


def save_requirement_upload(file_storage) -> str:
    from app.image_uploads import save_image
    return save_image(file_storage, "document_requirements")


def validate_approval(item, *, require_complete=True):
    code=template_code(item.document_type)
    if not item.verified_at or not item.verified_by_id or not item.verification_notes:
        raise ValueError("Verify resident information, evidence and document-specific eligibility first.")
    from .engine import verification_digest
    if item.verification_digest!=verification_digest(item):
        raise ValueError("Information, fee or evidence changed after verification. Verify this request again.")
    for evidence in active_requirements(item):
        if evidence.is_required and not evidence_available(evidence):
            raise ValueError('Required evidence file is unavailable. Request a corrected upload.')
    if not item.signatory or item.signatory not in active_signatories():
        raise ValueError("Select an active administrator-approved issuing signatory.")
    if code=="SCN-FTJ":
        previous=db.session.scalar(db.select(IssuedDocument.id).join(DocumentType).where(IssuedDocument.resident_id==item.resident_id,db.or_(DocumentType.code.in_(['FIRST_TIME_JOBSEEKER','SCN-FTJ']),DocumentType.template_code=='SCN-FTJ')))
        if previous: raise ValueError("A first-time jobseeker certification has already been issued for this resident.")
    if not require_complete:
        return
    if code!='SCN-FTJ' and not item.document_type.base_fee:
        from app.models import FeeConfiguration
        from sqlalchemy import or_
        from .engine import barangay_today
        today=barangay_today()
        configured=db.session.scalar(db.select(FeeConfiguration.id).where(FeeConfiguration.document_type_id==item.document_type_id,FeeConfiguration.status=='active',FeeConfiguration.effective_from<=today,or_(FeeConfiguration.effective_until.is_(None),FeeConfiguration.effective_until>=today)))
        if not configured: raise ValueError('An administrator must confirm the actual fee schedule, including any zero-fee service, before issuance.')
    values=item.additional_data or {}
    for key,label in fields_for(item.resident,code).items():
        from .engine import OPTIONAL
        if key not in OPTIONAL and not values.get(key): raise ValueError("Verified information is missing: "+label)
    if not item.description and code not in {"SCN-BIZ","SCN-SPE"}: raise ValueError("Purpose is required.")
    # Prevent a repeated first-time benefit. A revoked grant also consumes this benefit.
    if code=="SCN-FTJ":
        previous=db.session.scalar(db.select(IssuedDocument.id).join(DocumentType).where(IssuedDocument.resident_id==item.resident_id,db.or_(DocumentType.code.in_(['FIRST_TIME_JOBSEEKER','SCN-FTJ']),DocumentType.template_code=='SCN-FTJ')))
        if previous: raise ValueError("A first-time jobseeker certification has already been issued for this resident.")


def generate_document(request_record: Request, actor, *, allow_blank_fields=False) -> None:
    if request_record.status != "APPROVED": raise ValueError("Only approved requests can be generated.")
    if request_record.issued_document: raise ValueError("This request already has a generated document.")
    if template_code(request_record.document_type)=='SCN-FTJ':
        db.session.scalar(db.select(Resident).where(Resident.id==request_record.resident_id).with_for_update())
    validate_approval(request_record, require_complete=not allow_blank_fields)
    now=request_record.approved_at
    if now.tzinfo is None: now=now.replace(tzinfo=timezone.utc)
    from zoneinfo import ZoneInfo
    local=now.astimezone(ZoneInfo("Asia/Manila"))
    code=template_code(request_record.document_type)
    number=next_number(code,local.year);token=secrets.token_urlsafe(32)
    until=expiry(code,local.date())
    expires=datetime.combine(until,datetime.max.time(),tzinfo=ZoneInfo("Asia/Manila"))
    verify_url=verification_url(token)
    issued=IssuedDocument(document_number=number,document_type_id=request_record.document_type_id,resident_id=request_record.resident_id,issued_by_id=request_record.approved_by_id,request_id=request_record.id,purpose=(request_record.description or '')[:255],issued_at=local,expires_at=expires,authorized_signatory=request_record.signatory.full_name,verification_token=token,verification_url=verify_url,qr_code_data_uri=qr_data_uri(verify_url),status="ready_for_printing")
    db.session.add(issued);db.session.flush()
    issued.snapshot=snapshot_data(request_record,issued,allow_pending_payment=allow_blank_fields)
    content=render_original(code,issued.snapshot)
    filename=f"{number}-{uuid4().hex}.html"
    directory=Path(current_app.config["STORAGE_ROOT"])/"generated_documents";directory.mkdir(parents=True,exist_ok=True)
    (directory/filename).write_text(content,encoding="utf-8")
    request_record.generated_filename=filename;request_record.generated_at=datetime.now(timezone.utc);request_record.ready_at=request_record.generated_at
    transition_request(request_record,"READY_FOR_PRINTING",actor,"Original certificate generated after verified approval.")


def release_document(request_record: Request, actor) -> IssuedDocument:
    if request_record.status not in {"PRINTED","READY_FOR_RELEASE"} or not request_record.generated_filename or not request_record.issued_document:
        raise ValueError("Print and record the official certificate before release.")
    document=request_record.issued_document
    if document.status=="revoked": raise ValueError("A revoked document cannot be released.")
    from .engine import fee_confirmed, configured_fee, barangay_today
    from decimal import Decimal
    day=barangay_today()
    if not fee_confirmed(request_record.document_type,day):
        raise ValueError('Confirm the actual fee before release. Printing is available while payment is pending.')
    paid=sum((Decimal(str(p.amount)) for p in request_record.payments if p.status=='paid'),Decimal(0))
    if paid<configured_fee(request_record.document_type,day):
        raise ValueError('Record the actual in-person payment and official receipt before release.')
    document.status="released";request_record.released_at=datetime.now(timezone.utc)
    transition_request(request_record,"RELEASED",actor,"Document released to resident.")
    return document
