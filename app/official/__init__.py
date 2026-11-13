"""Barangay official resident and household management."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import and_, func, or_, asc, desc
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app.auth.decorators import official_account_required
from app.blotter import add_party, statistics, transition_case
from app.documents import ensure_catalog, generate_document, release_document, transition_request
from app.form_values import strict_form_value
from app.extensions import db
from app.audit import record as audit_record
from app.email_service import send_resident_credentials
from app.forms.official import (
    ResidentForm, DocumentStatusForm, AdditionalRequirementForm, 
    BlotterStatusForm, BlotterPartyForm, BlotterHearingForm, BusinessForm,
    CollectionForm, CorrectionReviewForm, QueueUpdateForm, WelfareForm, AssistanceForm
)
from app.validation import ValidationService
from app.pagination import paginate_named
from app.registration import store_profile_uploads, profile_upload_snapshot, cleanup_replaced_uploads, cleanup_files
from app.models import (
    Household,
    Purok,
    Resident,
    ResidentCorrectionRequest,
    HealthRegistry,
    SocialWelfareRegistry,
    DocumentRequirement,
    Request,
    BlotterCase,
    BlotterCaseAccess,
    BlotterCaseEvent,
    BlotterEndorsement,
    BlotterHearing,
    BlotterMediation,
    BlotterParty,
    BlotterSettlement,
    AssistanceRecord,
    BeneficiaryRegistry,
    BusinessClearanceRequest,
    BusinessRecord,
    CollectionEntry,
    QueueRequest,
    User,
    DamageReport,
    DRRMEquipment,
    DRRMIncident,
    EmergencyAlert,
    EmergencyContact,
    EvacuationCenter,
    HazardZone,
    ReliefRecord,
    ReliefSupply,
)

official_bp = Blueprint("official", __name__, url_prefix="/official")


from app.querying import apply_sort


def allowed_photo(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["PROFILE_PHOTO_ALLOWED_EXTENSIONS"]


def save_profile_photo(file_storage) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    from app.image_uploads import save_image
    return save_image(file_storage, "profile_photos")


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def resident_form_data(existing: Resident | None = None) -> dict:
    form = request.form
    return {
        "first_name": form.get("first_name", existing.first_name if existing else "").strip(),
        "middle_name": form.get("middle_name", existing.middle_name if existing else "").strip() or None,
        "last_name": form.get("last_name", existing.last_name if existing else "").strip(),
        "suffix": form.get("suffix", existing.suffix if existing else "").strip() or None,
        "sex": form.get("sex", existing.sex if existing else "").strip() or None,
        "birth_date": parse_date(form.get("birth_date")) if request.method == "POST" else (existing.birth_date if existing else None),
        "civil_status": form.get("civil_status", existing.civil_status if existing else "").strip() or None,
        "occupation": form.get("occupation", existing.occupation if existing else "").strip() or None,
        "contact_number": form.get("contact_number", existing.contact_number if existing else "").strip() or None,
        "email": form.get("email", existing.email if existing else "").strip() or None,
        "address_line": form.get("address_line", existing.address_line if existing else "").strip() or None,
        "voter_status": form.get("voter_status", existing.voter_status if existing else "unknown").strip(),
        "purok_id": form.get("purok_id", existing.purok_id if existing else None, type=int),
        "household_id": form.get("household_id", existing.household_id if existing else None, type=int),
        "household_member_no": form.get("household_member_no", existing.household_member_no if existing else None, type=int),
    }


def archive_published_alerts(exclude_id: int | None = None) -> None:
    for alert in db.session.scalars(
        db.select(EmergencyAlert).where(EmergencyAlert.status == "PUBLISHED")
    ).all():
        if exclude_id is None or alert.id != exclude_id:
            alert.status = "ARCHIVED"


@official_bp.get("/")
@official_account_required
def dashboard():
    metrics = {
        "pending_documents": db.session.scalar(
            db.select(func.count(Request.id)).where(Request.status.in_(["PENDING", "UNDER_REVIEW", "PROCESSING"]))
        ) or 0,
        "open_blotter": db.session.scalar(
            db.select(func.count(BlotterCase.id)).where(BlotterCase.status.in_(["OPEN", "UNDER_MEDIATION", "HEARING_SCHEDULED"]))
        ) or 0,
        "queue_waiting": db.session.scalar(
            db.select(func.count(QueueRequest.id)).where(QueueRequest.status.in_(["PENDING", "PROCESSING", "SCHEDULED"]))
        ) or 0,
    }
    return render_template("areas/official_dashboard.html", metrics=metrics)


@official_bp.get("/account-approvals")
@official_account_required
def account_approvals():
    """Review resident registrations; available only to officials and system admins."""
    pagination = paginate_named(db.select(User)
        .where(User.resident_id.is_not(None), User.is_active.is_(False))
        .order_by(User.created_at.asc(), User.id.asc()))
    return render_template("official/account_approvals.html", pending_accounts=pagination.items, pagination=pagination)


@official_bp.post("/account-approvals/<int:user_id>/approve")
@official_account_required
def approve_resident_account(user_id: int):
    user = db.get_or_404(User, user_id)
    resident = user.resident
    if resident is None or user.is_active:
        flash("Hindi na pending ang account na ito.", "warning")
        return redirect(url_for("official.account_approvals"))
    
    if current_app.config.get("REQUIRE_EMAIL_VERIFICATION_FOR_APPROVAL", True) and user.email_verified_at is None:
        flash("Resident must verify their email before approval.", "danger")
        return redirect(url_for("official.account_approvals"))
    if user.status != "pending":
        flash("Only pending registrations can be approved.", "warning")
        return redirect(url_for("official.account_approvals"))

    if resident.birth_date is None:
        flash("Walang birthdate ang resident; hindi maaaring buuin ang temporary password.", "danger")
        return redirect(url_for("official.account_approvals"))

    resident_id = f"SCN-RES-{resident.id:06d}"
    suffix = 1
    while db.session.scalar(db.select(User.id).where(User.username == resident_id, User.id != user.id)):
        resident_id = f"SCN-RES-{resident.id:06d}-{suffix}"
        suffix += 1
    full_name = " ".join(part for part in (resident.first_name, resident.middle_name, resident.last_name, resident.suffix) if part)

    try:
        # Immediately activate the account upon official approval
        import secrets
        temporary_password = secrets.token_urlsafe(18)
        
        user.username = resident_id
        user.set_password(temporary_password)
        user.must_change_password = True
        user.status = "active"
        user.is_active = True
        user.activated_at = datetime.now(timezone.utc)
        user.activation_token_hash = None
        user.activation_expires_at = None
        
        resident.status = "active"
        resident.is_verified = True
        
        # Send credentials immediately via email
        send_resident_credentials(
            recipient=user.email,
            full_name=full_name,
            resident_id=resident_id,
            temporary_password=temporary_password,
        )
        
        audit_record("APPROVE_AND_ACTIVATE", "auth", "User", user.id,
                     f"Resident account {resident_id} approved and activated by official")
        db.session.commit()
        flash(f"Naaprubahan at na-activate na ang {resident_id}. Naipadala ang Resident ID at temporary password sa {user.email}.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Resident account approval/activation failed for user id %s", user_id)
        flash("Hindi naaprubahan ang account. Suriin ang SMTP configuration at subukang muli.", "danger")
    return redirect(url_for("official.account_approvals"))


@official_bp.get("/residents")
@official_account_required
def resident_list():
    query = db.select(Resident)
    
    # Search
    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(
            Resident.first_name.ilike(pattern), 
            Resident.middle_name.ilike(pattern), 
            Resident.last_name.ilike(pattern), 
            Resident.email.ilike(pattern)
        ))
    
    # Filters
    if request.args.get("purok_id", type=int):
        query = query.where(Resident.purok_id == request.args.get("purok_id", type=int))
    
    if request.args.get("status"):
        query = query.where(Resident.status == request.args.get("status"))
    
    if request.args.get("civil_status"):
        query = query.where(Resident.civil_status == request.args["civil_status"])
    
    if request.args.get("voter_status"):
        query = query.where(Resident.voter_status == request.args.get("voter_status"))
    
    today = date.today()
    age = request.args.get("age", type=int)
    if age is not None:
        cutoff = today.replace(year=today.year - age)
        query = query.where(Resident.birth_date.between(
            today.replace(year=today.year - age - 1) + __import__('datetime').timedelta(days=1), 
            cutoff
        ))
    
    if request.args.get("senior") == "1":
        query = query.where(Resident.birth_date <= today.replace(year=today.year - 60))
    
    if request.args.get("pwd") == "1":
        query = query.where(Resident.health_records.any(
            and_(HealthRegistry.disability_details.is_not(None), HealthRegistry.disability_details != "")
        ))
    
    if request.args.get("four_ps") == "1":
        query = query.where(Resident.social_records.any(SocialWelfareRegistry.category.ilike("%4p%")))
    
    if request.args.get("solo_parent") == "1":
        query = query.where(Resident.social_records.any(SocialWelfareRegistry.category.ilike("%solo%")))
    
    # Apply sorting (default: last_name, first_name ASC)
    sort_column = request.args.get('sort', 'last_name')
    sort_order = request.args.get('order', 'asc')
    
    if sort_column == 'name':
        # Special handling for name sorting
        if sort_order == 'desc':
            query = query.order_by(desc(Resident.last_name), desc(Resident.first_name))
        else:
            query = query.order_by(asc(Resident.last_name), asc(Resident.first_name))
    else:
        query = apply_sort(query, Resident, default_column='last_name', default_order='asc')
    
    pagination = paginate_named(query)
    
    return render_template(
        "official/residents.html", 
        residents=pagination.items, 
        pagination=pagination, 
        puroks=db.session.scalars(db.select(Purok).order_by(Purok.name)).all(), 
        filters=request.args, 
        selected_purok_id=request.args.get("purok_id", type=int), 
        today=today
    )


@official_bp.get("/households")
@official_account_required
def household_list():
    query = db.select(Household)
    
    # Apply sorting
    query = apply_sort(query, Household, default_column='household_number', default_order='asc')
    
    pagination = paginate_named(query)
    
    return render_template(
        "official/households.html", 
        households=pagination.items, 
        pagination=pagination,
        filters=request.args
    )


@official_bp.route("/residents/new", methods=["GET", "POST"])
@official_account_required
def resident_create():
    form = ResidentForm()
    
    if form.validate_on_submit():
        created_files = []
        try:
            # Create resident with validated and sanitized data
            resident = Resident(
                first_name=ValidationService.sanitize_input(form.first_name.data),
                middle_name=ValidationService.sanitize_input(form.middle_name.data) if form.middle_name.data else None,
                last_name=ValidationService.sanitize_input(form.last_name.data),
                suffix=ValidationService.sanitize_input(form.suffix.data) if form.suffix.data else None,
                sex=form.sex.data if form.sex.data else None,
                birth_date=form.birth_date.data,
                civil_status=form.civil_status.data if form.civil_status.data else None,
                occupation=ValidationService.sanitize_input(form.occupation.data) if form.occupation.data else None,
                contact_number=ValidationService.sanitize_input(form.contact_number.data) if form.contact_number.data else None,
                email=ValidationService.sanitize_input(form.email.data) if form.email.data else None,
                address_line=ValidationService.sanitize_input(form.address_line.data) if form.address_line.data else None,
                voter_status=form.voter_status.data,
                purok_id=form.purok_id.data if form.purok_id.data else None,
                household_id=form.household_id.data if form.household_id.data else None,
                household_member_no=form.household_member_no.data,
                status="active"
            )
            
            form.populate_obj(resident)
            store_profile_uploads(form, resident, created_files)
            
            db.session.add(resident)
            db.session.commit()
            flash("Resident record created successfully.", "success")
            return redirect(url_for("official.resident_detail", resident_id=resident.id))
            
        except Exception as e:
            db.session.rollback()
            cleanup_files(created_files)
            current_app.logger.exception("Resident record update failed")
            ValidationService.handle_form_error(form, str(e) if isinstance(e, ValueError) else "Unable to save resident. Check duplicate IDs and linked records.")
    
    # Handle validation errors
    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field.title()}: {error}", "danger")
    
    puroks = db.session.scalars(db.select(Purok).order_by(Purok.name)).all()
    households = db.session.scalars(db.select(Household).order_by(Household.household_number)).all()
    return render_template("official/resident_form.html", 
                         form=form, resident=None, puroks=puroks, households=households)


@official_bp.route("/residents/<int:resident_id>/edit", methods=["GET", "POST"])
@official_account_required
def resident_edit(resident_id: int):
    resident = db.get_or_404(Resident, resident_id)
    form = ResidentForm(obj=resident)
    
    if form.validate_on_submit():
        created_files = []
        previous_files = profile_upload_snapshot(resident)
        try:
            # Update resident with validated and sanitized data
            form.populate_obj(resident)
            
            # Sanitize text fields
            resident.first_name = ValidationService.sanitize_input(resident.first_name)
            if resident.middle_name:
                resident.middle_name = ValidationService.sanitize_input(resident.middle_name)
            resident.last_name = ValidationService.sanitize_input(resident.last_name)
            if resident.suffix:
                resident.suffix = ValidationService.sanitize_input(resident.suffix)
            if resident.occupation:
                resident.occupation = ValidationService.sanitize_input(resident.occupation)
            if resident.contact_number:
                resident.contact_number = ValidationService.sanitize_input(resident.contact_number)
            if resident.email:
                resident.email = ValidationService.sanitize_input(resident.email)
            if resident.address_line:
                resident.address_line = ValidationService.sanitize_input(resident.address_line)
            
            store_profile_uploads(form, resident, created_files)
            
            db.session.commit()
            cleanup_replaced_uploads(previous_files, resident)
            flash("Resident record updated successfully.", "success")
            return redirect(url_for("official.resident_detail", resident_id=resident.id))
            
        except Exception as e:
            db.session.rollback()
            cleanup_files(created_files)
            current_app.logger.exception("Resident record update failed")
            ValidationService.handle_form_error(form, str(e) if isinstance(e, ValueError) else "Unable to save resident. Check duplicate IDs and linked records.")
    
    # Handle validation errors
    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field.title()}: {error}", "danger")
    
    puroks = db.session.scalars(db.select(Purok).order_by(Purok.name)).all()
    households = db.session.scalars(db.select(Household).order_by(Household.household_number)).all()
    return render_template("official/resident_form.html", 
                         form=form, resident=resident, puroks=puroks, households=households)


@official_bp.get("/residents/<int:resident_id>")
@official_account_required
def resident_detail(resident_id: int):
    resident = db.get_or_404(Resident, resident_id)
    return render_template("official/resident_detail.html", resident=resident)


@official_bp.get("/residents/<int:resident_id>/household-members")
@official_account_required
def household_members(resident_id: int):
    resident = db.get_or_404(Resident, resident_id)
    if resident.household is None:
        return render_template("official/household_members.html", resident=resident, household=None, members=[])
    return render_template("official/household_members.html", resident=resident, household=resident.household, members=resident.household.residents)


@official_bp.get("/residents/<int:resident_id>/photo")
@official_account_required
def resident_photo(resident_id: int):
    resident = db.get_or_404(Resident, resident_id)
    if not resident.profile_photo_filename:
        abort(404)
    return send_from_directory(Path(current_app.config["STORAGE_ROOT"]) / "profile_photos", resident.profile_photo_filename)


@official_bp.get("/correction-requests")
@official_account_required
def correction_requests():
    query = db.select(ResidentCorrectionRequest)
    
    # Filter by status
    if request.args.get("status"):
        query = query.where(ResidentCorrectionRequest.status == request.args.get("status"))
    
    # Apply sorting
    query = apply_sort(query, ResidentCorrectionRequest, default_column='created_at', default_order='desc')
    
    pagination = paginate_named(query)
    
    return render_template(
        "official/correction_requests.html", 
        requests=pagination.items, 
        pagination=pagination,
        filters=request.args
    )


@official_bp.post("/correction-requests/<int:correction_id>/approve")
@official_account_required
def correction_approve(correction_id: int):
    item = db.get_or_404(ResidentCorrectionRequest, correction_id)
    if item.status != "pending":
        flash("Only pending correction requests can be approved.", "warning")
        return redirect(url_for("official.correction_requests"))

    review_notes = request.form.get("review_notes", "").strip() or None
    try:
        from app.registration import parse_correction
        setattr(item.resident, item.field_name, parse_correction(item.resident, item.field_name, item.proposed_value))
    except (AttributeError, ValueError) as error:
        flash(f"Correction could not be applied: {error}", "danger")
        return redirect(url_for("official.correction_requests"))

    item.status = "approved"
    item.reviewed_by_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_notes = review_notes

    # Notify the resident if they have an account
    if item.resident.user:
        from app.models import Notification
        db.session.add(Notification(
            user_id=item.resident.user.id,
            title="Correction request approved",
            message=f"Your correction to '{item.field_name}' has been approved and applied.",
            status="active",
        ))

    db.session.commit()
    flash(f"Correction to '{item.field_name}' approved and applied to the resident record.", "success")
    return redirect(url_for("official.correction_requests"))


@official_bp.post("/correction-requests/<int:correction_id>/reject")
@official_account_required
def correction_reject(correction_id: int):
    item = db.get_or_404(ResidentCorrectionRequest, correction_id)
    if item.status != "pending":
        flash("Only pending correction requests can be rejected.", "warning")
        return redirect(url_for("official.correction_requests"))

    review_notes = request.form.get("review_notes", "").strip()
    if not review_notes:
        flash("A rejection reason is required.", "danger")
        return redirect(url_for("official.correction_requests"))

    item.status = "rejected"
    item.reviewed_by_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_notes = review_notes

    # Notify the resident if they have an account
    if item.resident.user:
        from app.models import Notification
        db.session.add(Notification(
            user_id=item.resident.user.id,
            title="Correction request rejected",
            message=f"Your correction to '{item.field_name}' was not approved. Reason: {review_notes}",
            status="active",
        ))

    db.session.commit()
    flash(f"Correction request rejected.", "success")
    return redirect(url_for("official.correction_requests"))


@official_bp.get("/document-requests")
@official_account_required
def document_requests():
    ensure_catalog()
    query = db.select(Request).where(Request.document_type_id.is_not(None))
    from sqlalchemy import or_
    from app.documents.engine import DETAIL_FIELDS
    if request.args.get("q"):
        query=query.join(Resident)
        for word in request.args['q'].strip().split():
            term='%'+word+'%'
            query=query.where(or_(Resident.first_name.ilike(term),Resident.middle_name.ilike(term),Resident.last_name.ilike(term),Resident.suffix.ilike(term),Request.request_number.ilike(term)))
    for key,operator in [("start_date",">="),("end_date","<=")]:
        if request.args.get(key):
            try:
                day=date.fromisoformat(request.args[key])
                query=query.where(db.func.date(Request.created_at)>=day if operator==">=" else db.func.date(Request.created_at)<=day)
            except ValueError: flash("Enter valid filter dates.","danger")
    counts=dict(db.session.execute(db.select(Request.status,db.func.count(Request.id)).where(Request.document_type_id.is_not(None)).group_by(Request.status)).all())
    
    # Filter by status
    if request.args.get("status"):
        query = query.where(Request.status == request.args.get("status"))
    
    # Filter by document type
    if request.args.get("document_type_id", type=int):
        query = query.where(Request.document_type_id == request.args.get("document_type_id", type=int))
    
    # Apply sorting
    query = apply_sort(query, Request, default_column='created_at', default_order='desc')
    
    pagination = paginate_named(query)
    
    return render_template(
        "official/document_requests.html", 
        requests=pagination.items, 
        pagination=pagination,
        filters=request.args,counts=counts,document_types=ensure_catalog()
    )


@official_bp.get("/document-requests/<int:request_id>")
@official_account_required
def document_request_detail(request_id: int):
    item = db.get_or_404(Request, request_id)
    if item.document_type_id is None:
        abort(404)
    from app.documents.engine import resident_data,template_code,CHECKLISTS,active_signatories,configured_fee,fields_for,barangay_today,fee_confirmed
    try: checks=CHECKLISTS[template_code(item.document_type)]
    except ValueError: checks=[]
    from app.documents.workflow import ALLOWED_TRANSITIONS, validate_approval
    status_actions = ALLOWED_TRANSITIONS.get(item.status, set())
    approval_blocker = None
    if "APPROVED" in status_actions:
        try:
            validate_approval(item)
        except ValueError as error:
            approval_blocker = str(error)
    return render_template("official/document_request_detail.html",doc_request=item,resident_info=resident_data(item.resident),checks=checks,signatories=active_signatories(),fee=configured_fee(item.document_type,barangay_today()) if checks else item.document_type.base_fee,status_actions=status_actions,approval_blocker=approval_blocker,detail_fields=fields_for(item.resident,template_code(item.document_type)),paid_total=sum((p.amount for p in item.payments if p.status=='paid'),0),fee_is_confirmed=fee_confirmed(item.document_type,barangay_today()))


@official_bp.post("/document-requests/<int:request_id>/status")
@official_account_required
def document_request_status(request_id: int):
    from app.documents.routes import locked_request
    item = locked_request(request_id)
    new_status = request.form.get("status", "").strip().upper()
    notes = request.form.get("notes", "").strip() or None
    if new_status == "REJECTED" and not notes:
        flash("A rejection reason is required.", "danger")
        return redirect(url_for("official.document_request_detail", request_id=item.id))
    try:
        if new_status == "REJECTED":
            item.rejection_reason = notes
        if new_status=="NEEDS_CORRECTION": item.additional_requirements_note=notes
        transition_request(item, new_status, current_user, notes)
        if new_status=="APPROVED":
            # Serialize first-time entitlement checks across requests for one resident.
            db.session.scalar(db.select(Resident).where(Resident.id==item.resident_id).with_for_update())
            generate_document(item,current_user)
        db.session.commit()
        flash(f"Request moved to {new_status.replace('_', ' ').title()}.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("official.document_request_detail", request_id=item.id))


@official_bp.post("/document-requests/<int:request_id>/additional-requirement")
@official_account_required
def document_additional_requirement(request_id: int):
    item = db.get_or_404(Request, request_id)
    name = request.form.get("requirement_name", "").strip()
    notes = request.form.get("notes", "").strip() or None
    from app.documents.workflow import is_retired_requirement
    if is_retired_requirement(item, name):
        flash(f"This upload is no longer part of the {item.document_type.name} checklist.", "danger")
    elif item.status not in {"UNDER_REVIEW", "PROCESSING"} or not name:
        flash("Additional requirements can only be requested during review or processing.", "danger")
    else:
        db.session.add(DocumentRequirement(request_id=item.id, requirement_name=name, status="pending", is_required=True, notes=notes))
        item.additional_requirements_note = notes or name
        item.verified_at=None;item.verified_by_id=None
        from app.documents.workflow import notify_resident
        notify_resident(item, "Additional document requirement", f"Please provide: {name} for request {item.request_number}.")
        db.session.commit()
        flash("Additional requirement requested.", "success")
    return redirect(url_for("official.document_request_detail", request_id=item.id))


@official_bp.post("/document-requests/<int:request_id>/generate")
@official_account_required
def document_generate(request_id: int):
    from app.documents.routes import locked_request
    item = locked_request(request_id)
    try:
        generate_document(item, current_user)
        db.session.commit()
        flash("Document generated and marked ready for release.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("official.document_request_detail", request_id=item.id))


@official_bp.post("/document-requests/<int:request_id>/release")
@official_account_required
def document_release(request_id: int):
    from app.documents.routes import locked_request
    item = locked_request(request_id)
    try:
        release_document(item, current_user)
        db.session.commit()
        flash("Document released and issuance record created.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("official.document_request_detail", request_id=item.id))


@official_bp.get("/document-requests/<int:request_id>/requirements/<int:requirement_id>/download")
@official_account_required
def document_requirement_download(request_id: int, requirement_id: int):
    requirement = db.session.scalar(db.select(DocumentRequirement).where(DocumentRequirement.id == requirement_id, DocumentRequirement.request_id == request_id))
    if requirement is None or not requirement.filename:
        abort(404)
    from app.documents.workflow import send_requirement_image
    return send_requirement_image(requirement, as_attachment=True)


@official_bp.get("/document-requests/<int:request_id>/requirements/<int:requirement_id>/view")
@official_account_required
def document_requirement_view(request_id: int, requirement_id: int):
    requirement = db.session.scalar(db.select(DocumentRequirement).where(DocumentRequirement.id == requirement_id, DocumentRequirement.request_id == request_id))
    if requirement is None:
        abort(404)
    from app.documents.workflow import send_requirement_image
    response = send_requirement_image(requirement)
    from app.audit import record
    record("DOCUMENT_REQUIREMENT_VIEW", "documents", "DocumentRequirement", requirement.id, "Private requirement image viewed by staff")
    db.session.commit()
    return response


@official_bp.get("/blotter")
@official_account_required
def blotter_list():
    query = db.select(BlotterCase)
    
    # Filters
    if request.args.get("status"):
        query = query.where(BlotterCase.status == request.args["status"].upper())
    
    if request.args.get("category"):
        query = query.where(BlotterCase.category == request.args["category"])
    
    # Apply sorting
    query = query.order_by(BlotterCase.id.asc())
    
    pagination = paginate_named(query)
    from app.blotter.submissions import queue_position
    for case in pagination.items:
        case.queue_position = queue_position(case)
    latest_case_id = db.session.scalar(db.select(func.max(BlotterCase.id))) or 0
    
    return render_template(
        "official/blotter_cases.html", 
        cases=pagination.items, 
        pagination=pagination, 
        stats=statistics(), 
        latest_case_id=latest_case_id,
        filters=request.args
    )


@official_bp.get("/blotter/updates")
@official_account_required
def blotter_updates():
    """Return newly filed blotter cases for the official realtime list."""
    since_id = max(0, request.args.get("since_id", 0, type=int) or 0)
    query = db.select(BlotterCase).where(BlotterCase.id > since_id)
    status = request.args.get("status", "").strip().upper()
    category = request.args.get("category", "").strip()
    if status:
        query = query.where(BlotterCase.status == status)
    if category:
        query = query.where(BlotterCase.category == category)
    cases = db.session.scalars(query.order_by(BlotterCase.id.asc()).limit(50)).all()
    return jsonify({
        "cases": [{
            "id": case.id,
            "case_number": case.case_number,
            "complainant": case.complainant.full_name if case.complainant else "Unknown complainant",
            "category": case.category,
            "incident_date": case.incident_date.isoformat() if case.incident_date else "â€”",
            "status": case.status,
            "detail_url": url_for("official.blotter_detail", case_id=case.id),
        } for case in cases],
        "latest_case_id": max([case.id for case in cases], default=since_id),
    })


@official_bp.get("/blotter/statistics")
@official_account_required
def blotter_statistics():
    return render_template("official/blotter_statistics.html", stats=statistics())


@official_bp.get("/blotter-map")
@official_account_required
def blotter_map():
    """View all geotagged blotter cases on an OpenStreetMap."""
    try:
        return render_template(
            "official/blotter_map.html",
        )
    except Exception as e:
        current_app.logger.error(f"Error loading blotter map: {e}")
        flash("Error loading complaint map. Please try again.", "danger")
        return redirect(url_for("official.dashboard"))


def _blotter_map_payload() -> list[dict]:
    """Serialize geotagged cases for the live official map without exposing narrative text."""
    cases = db.session.scalars(
        db.select(BlotterCase)
        .where(BlotterCase.incident_latitude.is_not(None), BlotterCase.incident_longitude.is_not(None))
        .order_by(BlotterCase.created_at.desc())
    ).all()
    return [
        {
            "id": case.id,
            "case_number": case.case_number,
            "category": case.category or "Unknown",
            "status": case.status,
            "incident_date": case.incident_date.isoformat() if case.incident_date else None,
            "incident_location": case.incident_location or "",
            "incident_latitude": float(case.incident_latitude),
            "incident_longitude": float(case.incident_longitude),
            "complainant": case.complainant.full_name if case.complainant else "Anonymous",
            "respondent_name": case.respondent_name or "Unknown",
        }
        for case in cases
    ]


@official_bp.get("/blotter-map/data")
@official_account_required
def blotter_map_data():
    """Return current geotagged cases for the map's periodic refresh."""
    return jsonify({"cases": _blotter_map_payload(), "updated_at": datetime.now(timezone.utc).isoformat()})


@official_bp.get("/blotter/<int:case_id>")
@official_account_required
def blotter_detail(case_id: int):
    return render_template(
        "official/blotter_detail.html",
        case=db.get_or_404(BlotterCase, case_id),
        residents=db.session.scalars(db.select(Resident).order_by(Resident.last_name, Resident.first_name)).all(),
    )


@official_bp.post("/blotter/<int:case_id>/status")
@official_account_required
def blotter_status(case_id: int):
    case = db.get_or_404(BlotterCase, case_id)
    try:
        transition_case(case, request.form.get("status", ""), current_user, request.form.get("notes", "").strip() or None)
        db.session.commit(); flash("Case status updated.", "success")
    except ValueError as error:
        db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.blotter_detail", case_id=case.id))


@official_bp.post("/blotter/<int:case_id>/party")
@official_account_required
def blotter_party(case_id: int):
    case = db.get_or_404(BlotterCase, case_id)
    try:
        add_party(case, request.form.get("name", ""), request.form.get("role", ""), request.form.get("contact_information"), request.form.get("notes")); db.session.commit(); flash("Party added.", "success")
    except ValueError as error:
        db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.blotter_detail", case_id=case.id))


@official_bp.post("/blotter/<int:case_id>/hearing")
@official_account_required
def blotter_hearing(case_id: int):
    case = db.get_or_404(BlotterCase, case_id)
    try:
        scheduled_at = datetime.fromisoformat(request.form["scheduled_at"])
        db.session.add(BlotterHearing(case_id=case.id, scheduled_at=scheduled_at, location=request.form.get("location"), notes=request.form.get("notes")))
        if case.status in {"OPEN", "UNDER_MEDIATION"}: transition_case(case, "HEARING_SCHEDULED", current_user, "Hearing scheduled.")
        db.session.commit(); flash("Hearing scheduled.", "success")
    except (ValueError, KeyError) as error:
        db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.blotter_detail", case_id=case.id))


@official_bp.post("/blotter/<int:case_id>/mediation")
@official_account_required
def blotter_mediation(case_id: int):
    case = db.get_or_404(BlotterCase, case_id)
    db.session.add(BlotterMediation(case_id=case.id, scheduled_at=datetime.fromisoformat(request.form["scheduled_at"]) if request.form.get("scheduled_at") else None, mediator=request.form.get("mediator"), notes=request.form.get("notes"), outcome=request.form.get("outcome")))
    try:
        if case.status == "OPEN": transition_case(case, "UNDER_MEDIATION", current_user, "Mediation initiated.")
        db.session.commit(); flash("Mediation recorded.", "success")
    except ValueError as error:
        db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.blotter_detail", case_id=case.id))


@official_bp.post("/blotter/<int:case_id>/settlement")
@official_account_required
def blotter_settlement(case_id: int):
    case = db.get_or_404(BlotterCase, case_id); terms = request.form.get("terms", "").strip()
    if not terms: flash("Settlement terms are required.", "danger")
    else:
        db.session.add(BlotterSettlement(case_id=case.id, terms=terms, settled_at=datetime.now(timezone.utc), signed_by=request.form.get("signed_by")))
        try:
            transition_case(case, "SETTLED", current_user, "Settlement recorded."); case.resolution = terms; db.session.commit(); flash("Settlement recorded.", "success")
        except ValueError as error: db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.blotter_detail", case_id=case.id))


@official_bp.post("/blotter/<int:case_id>/endorsement")
@official_account_required
def blotter_endorsement(case_id: int):
    case = db.get_or_404(BlotterCase, case_id); agency = request.form.get("receiving_agency", "").strip(); reason = request.form.get("reason", "").strip()
    if not agency or not reason: flash("Receiving agency and endorsement reason are required.", "danger")
    else:
        db.session.add(BlotterEndorsement(case_id=case.id, receiving_agency=agency, reason=reason, endorsed_at=datetime.now(timezone.utc)))
        try:
            transition_case(case, "ENDORSED", current_user, "Case endorsed to another agency."); db.session.commit(); flash("Case endorsed.", "success")
        except ValueError as error: db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.blotter_detail", case_id=case.id))


@official_bp.post("/blotter/<int:case_id>/access")
@official_account_required
def blotter_access(case_id: int):
    case = db.get_or_404(BlotterCase, case_id)
    resident = db.session.get(Resident, strict_form_value("resident_id", type=int))
    if resident is None:
        flash("Select a valid resident.", "danger")
    else:
        existing = db.session.scalar(db.select(BlotterCaseAccess).where(BlotterCaseAccess.case_id == case.id, BlotterCaseAccess.resident_id == resident.id))
        if existing is None:
            db.session.add(BlotterCaseAccess(case_id=case.id, resident_id=resident.id, granted_by_id=current_user.id, reason=request.form.get("reason", "").strip() or None))
            db.session.commit(); flash("Resident viewing access granted.", "success")
        else:
            flash("That resident already has viewing access.", "info")
    return redirect(url_for("official.blotter_detail", case_id=case.id))


# Phase 9 â€” business clearance and health/social welfare registries
BENEFICIARY_CATEGORIES = {
    "SENIOR": "Senior Citizens", "PWD": "PWD", "4PS": "4Ps beneficiaries",
    "SOLO_PARENT": "Solo Parents", "PREGNANT": "Pregnant women", "NEWBORN": "Newborns",
}

def _official_residents():
    return db.session.scalars(db.select(Resident).order_by(Resident.last_name, Resident.first_name)).all()

def _date_field(name, fallback=None):
    value = request.form.get(name, "").strip()
    return parse_date(value) if value else fallback

@official_bp.get("/businesses")
@official_account_required
def business_list():
    query = db.select(BusinessRecord).order_by(BusinessRecord.expiration_date, BusinessRecord.business_name)
    q = request.args.get("q", "").strip()
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(BusinessRecord.business_name.ilike(pattern), BusinessRecord.permit_number.ilike(pattern), BusinessRecord.business_address.ilike(pattern)))
    if request.args.get("status"):
        query = query.where(BusinessRecord.status == request.args["status"].upper())
    pagination = paginate_named(query)
    businesses = pagination.items
    today = date.today()
    renewal_due = [item for item in businesses if item.expiration_date <= today.replace(day=today.day) or (item.expiration_date - today).days <= 30]
    return render_template("official/businesses.html", businesses=businesses, pagination=pagination, renewal_due=renewal_due, today=today, filters=request.args)

@official_bp.route("/businesses/new", methods=["GET", "POST"])
@official_account_required
def business_create():
    if request.method == "POST":
        try:
            required = [request.form.get(key, "").strip() for key in ("business_name", "business_address", "business_type", "permit_number")]
            owner_id = strict_form_value("owner_id", type=int)
            registration_date = _date_field("registration_date")
            expiration_date = _date_field("expiration_date")
            if not all(required) or not owner_id or not registration_date or not expiration_date:
                raise ValueError("Business name, owner, address, type, permit number, and both dates are required.")
            if not db.session.get(Resident, owner_id):
                raise ValueError("Select an existing business owner.")
            db.session.add(BusinessRecord(business_name=required[0], owner_id=owner_id, business_address=required[1], business_type=required[2], permit_number=required[3], registration_date=registration_date, expiration_date=expiration_date, status=request.form.get("status", "ACTIVE").upper()))
            db.session.commit(); flash("Business record created.", "success"); return redirect(url_for("official.business_list"))
        except (ValueError, TypeError) as error:
            db.session.rollback(); flash(str(error), "danger")
        except IntegrityError:
            db.session.rollback(); flash("The permit number is already assigned or the record conflicts with an existing entry.", "danger")
    return render_template("official/business_form.html", business=None, residents=_official_residents())

@official_bp.route("/businesses/<int:business_id>/edit", methods=["GET", "POST"])
@official_account_required
def business_edit(business_id):
    business = db.get_or_404(BusinessRecord, business_id)
    if request.method == "POST":
        try:
            for field in ("business_name", "business_address", "business_type", "permit_number"):
                setattr(business, field, request.form.get(field, "").strip())
            business.owner_id = strict_form_value("owner_id", type=int)
            business.registration_date = _date_field("registration_date", business.registration_date)
            business.expiration_date = _date_field("expiration_date", business.expiration_date)
            business.status = request.form.get("status", "ACTIVE").upper()
            if not all((business.business_name, business.business_address, business.business_type, business.permit_number)):
                raise ValueError("Business name, address, type, and permit number are required.")
            if not business.owner_id or not db.session.get(Resident, business.owner_id):
                raise ValueError("Select an existing business owner.")
            db.session.commit(); flash("Business record updated.", "success"); return redirect(url_for("official.business_list"))
        except (ValueError, TypeError) as error:
            db.session.rollback(); flash(str(error), "danger")
        except IntegrityError:
            db.session.rollback(); flash("The permit number is already assigned or the record conflicts with an existing entry.", "danger")
    return render_template("official/business_form.html", business=business, residents=_official_residents())

@official_bp.get("/business-clearance-requests")
@official_account_required
def business_clearance_requests():
    query = db.select(BusinessClearanceRequest).order_by(BusinessClearanceRequest.created_at.desc())
    if request.args.get("status"): query = query.where(BusinessClearanceRequest.status == request.args["status"].upper())
    pagination = paginate_named(query)
    return render_template("official/business_requests.html", requests=pagination.items, pagination=pagination, filters=request.args)

@official_bp.post("/businesses/<int:business_id>/request-clearance")
@official_account_required
def business_request_clearance(business_id):
    business = db.get_or_404(BusinessRecord, business_id)
    number = f"BCR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{business.id}"
    db.session.add(BusinessClearanceRequest(request_number=number, business_id=business.id, requester_id=business.owner_id, requested_at=datetime.now(timezone.utc), notes=request.form.get("notes", "").strip() or None, status="PENDING"))
    db.session.commit(); flash("Business clearance request submitted for review.", "success")
    return redirect(url_for("official.business_list"))

@official_bp.post("/business-clearance-requests/<int:request_id>/status")
@official_account_required
def business_clearance_status(request_id):
    item = db.get_or_404(BusinessClearanceRequest, request_id)
    item.status = request.form.get("status", "PENDING").upper(); item.reviewed_by_id = current_user.id; item.reviewed_at = datetime.now(timezone.utc)
    db.session.commit(); flash("Clearance request status updated.", "success")
    return redirect(url_for("official.business_clearance_requests"))

@official_bp.get("/welfare")
@official_account_required
def welfare_registry():
    query = db.select(BeneficiaryRegistry).order_by(BeneficiaryRegistry.registered_date.desc())
    if request.args.get("category"): query = query.where(BeneficiaryRegistry.category == request.args["category"])
    if request.args.get("application_status"): query = query.where(BeneficiaryRegistry.application_status == request.args["application_status"].upper())
    q = request.args.get("q", "").strip()
    if q: query = query.join(Resident).where(or_(Resident.first_name.ilike(f"%{q}%"), Resident.last_name.ilike(f"%{q}%")))
    pagination = paginate_named(query)
    assistance_pagination=paginate_named(db.select(AssistanceRecord).order_by(AssistanceRecord.assistance_date.desc(),AssistanceRecord.id.desc()),"assistance_page")
    return render_template("official/welfare.html", beneficiaries=pagination.items, pagination=pagination, categories=BENEFICIARY_CATEGORIES, filters=request.args, assistance=assistance_pagination.items, assistance_pagination=assistance_pagination)

@official_bp.route("/welfare/new", methods=["GET", "POST"])
@official_account_required
def welfare_create():
    if request.method == "POST":
        try:
            resident_id = strict_form_value("resident_id", type=int); category = request.form.get("category", "")
            registered_date = _date_field("registered_date", date.today())
            if not resident_id or category not in BENEFICIARY_CATEGORIES: raise ValueError("Resident and a valid registry category are required.")
            db.session.add(BeneficiaryRegistry(resident_id=resident_id, category=category, application_status=request.form.get("application_status", "PENDING").upper(), registered_date=registered_date, application_notes=request.form.get("application_notes", "").strip() or None, status="ACTIVE"))
            db.session.commit(); flash("Beneficiary registered.", "success"); return redirect(url_for("official.welfare_registry"))
        except (ValueError, TypeError) as error:
            db.session.rollback(); flash(str(error), "danger")
    return render_template("official/welfare_form.html", beneficiary=None, residents=_official_residents(), categories=BENEFICIARY_CATEGORIES)

@official_bp.route("/welfare/<int:beneficiary_id>/edit", methods=["GET", "POST"])
@official_account_required
def welfare_edit(beneficiary_id):
    beneficiary = db.get_or_404(BeneficiaryRegistry, beneficiary_id)
    if request.method == "POST":
        try:
            resident_id = strict_form_value("resident_id", type=int)
            category = request.form.get("category", beneficiary.category)
            status = request.form.get("application_status", beneficiary.application_status).upper()
            if not resident_id or not db.session.get(Resident, resident_id) or category not in BENEFICIARY_CATEGORIES:
                raise ValueError("Select a resident and a valid registry category.")
            if status not in {"PENDING", "APPROVED", "REJECTED", "INACTIVE"}:
                raise ValueError("Select a valid application status.")
            beneficiary.resident_id = resident_id
            beneficiary.category = category
            beneficiary.application_status = status
            beneficiary.registered_date = _date_field("registered_date", beneficiary.registered_date)
            beneficiary.application_notes = request.form.get("application_notes", "").strip() or None
            db.session.commit()
            flash("Beneficiary record updated.", "success")
            return redirect(url_for("official.welfare_registry"))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "danger")
        except IntegrityError:
            db.session.rollback()
            flash("The beneficiary record conflicts with an existing entry.", "danger")
    return render_template("official/welfare_form.html", beneficiary=beneficiary, residents=_official_residents(), categories=BENEFICIARY_CATEGORIES)

@official_bp.post("/welfare/<int:beneficiary_id>/assistance")
@official_account_required
def welfare_assistance(beneficiary_id):
    beneficiary = db.get_or_404(BeneficiaryRegistry, beneficiary_id)
    try:
        db.session.add(AssistanceRecord(beneficiary_id=beneficiary.id, assistance_type=request.form.get("assistance_type", "").strip(), assistance_date=_date_field("assistance_date", date.today()), quantity=strict_form_value("quantity", 1, type=int), description=request.form.get("description", "").strip() or None, distribution_officer_id=current_user.id, remarks=request.form.get("remarks", "").strip() or None))
        db.session.commit(); flash("Assistance record saved.", "success")
    except (ValueError, TypeError):
        db.session.rollback(); flash("Assistance type and a valid quantity are required.", "danger")
    return redirect(url_for("official.welfare_registry"))


# Phase 12 â€” official queue management
QUEUE_STATUSES = ("PENDING", "PROCESSING", "READY", "SCHEDULED", "COMPLETED", "CLOSED")
QUEUE_TYPES = {"DOCUMENT": "Document", "COMPLAINT": "Complaint", "APPOINTMENT": "Appointment", "CONSULTATION": "Consultation", "OTHER": "Other barangay service"}

@official_bp.get("/queue")
@official_account_required
def queue_management():
    query = db.select(QueueRequest).order_by(QueueRequest.created_at.asc())
    if request.args.get("status"): query = query.where(QueueRequest.status == request.args["status"].upper())
    if request.args.get("request_type"): query = query.where(QueueRequest.request_type == request.args["request_type"].upper())
    pagination = paginate_named(query)
    return render_template("official/queue.html", requests=pagination.items, pagination=pagination, statuses=QUEUE_STATUSES, request_types=QUEUE_TYPES, officials=db.session.scalars(db.select(User).order_by(User.username)).all(), filters=request.args)

@official_bp.post("/queue/<int:queue_id>/update")
@official_account_required
def queue_update(queue_id):
    item = db.get_or_404(QueueRequest, queue_id)
    item.status = request.form.get("status", "PENDING").upper()
    item.assigned_official_id = strict_form_value("assigned_official_id", type=int) or None
    item.appointment_date = parse_date(request.form.get("appointment_date"))
    item.appointment_time = datetime.strptime(request.form["appointment_time"], "%H:%M").time() if request.form.get("appointment_time") else None
    item.remarks = request.form.get("remarks", "").strip() or None
    db.session.commit(); flash("Queue request updated.", "success")
    return redirect(url_for("official.queue_management"))

# Phase 13 â€” simple fee/collection ledger (not a full accounting system)
@official_bp.get("/collections")
@official_account_required
def collections():
    today = date.today()
    month_start = today.replace(day=1)
    pagination = paginate_named(db.select(CollectionEntry).order_by(CollectionEntry.transaction_date.desc(), CollectionEntry.created_at.desc()))
    entries = pagination.items
    amount = func.sum(CollectionEntry.amount)
    daily, monthly = db.session.execute(db.select(
        func.coalesce(amount.filter(CollectionEntry.transaction_date == today), 0),
        func.coalesce(amount.filter(CollectionEntry.transaction_date.between(month_start, today)), 0),
    )).one()
    by_service = db.session.execute(db.select(CollectionEntry.service, amount)
        .group_by(CollectionEntry.service).order_by(CollectionEntry.service)).all()
    return render_template("official/collections.html", entries=entries, pagination=pagination,
        daily=daily, monthly=monthly, by_service=by_service, residents=_official_residents(), today=today)


@official_bp.get("/reports")
@official_account_required
def reports():
    from app.admin import REPORT_CATALOG, report_rows

    kind = request.args.get("kind") or ""
    headers, rows = [], []
    if kind in REPORT_CATALOG:
        headers, rows = report_rows(kind)
    from app.pagination import paginate_items
    pagination=paginate_items(rows)
    return render_template("official/reports.html", catalog=REPORT_CATALOG, kind=kind, headers=headers, rows=pagination.items, pagination=pagination)

@official_bp.post("/collections/new")
@official_account_required
def collection_create():
    try:
        resident_id = strict_form_value("resident_id", type=int)
        service = request.form.get("service", "").strip()
        amount = float(request.form.get("amount", "0"))
        transaction_date = parse_date(request.form.get("transaction_date")) or date.today()
        if not resident_id or not service or amount < 0: raise ValueError("Resident, service, and a non-negative amount are required.")
        item = CollectionEntry(transaction_number=f"COL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:4].upper()}", resident_id=resident_id, service=service, amount=amount, payment_method=request.form.get("payment_method", "CASH"), transaction_date=transaction_date, receiving_official_id=current_user.id, reference_number=request.form.get("reference_number", "").strip() or None)
        db.session.add(item); db.session.commit(); flash("Collection recorded in the fee ledger.", "success")
    except (ValueError, TypeError) as error:
        db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.collections"))


# Phase 14 â€” Disaster Risk Reduction and Management
@official_bp.get("/drrm")
@official_account_required
def drrm_dashboard():
    edit_alert = None
    if request.args.get("edit_alert_id", type=int):
        edit_alert = db.get_or_404(EmergencyAlert, request.args["edit_alert_id"])
    archived_alerts = request.args.get("alerts_view") == "archived"
    alert_filter = EmergencyAlert.status == "ARCHIVED" if archived_alerts else EmergencyAlert.status != "ARCHIVED"
    queries = {
        'hazards': db.select(HazardZone).order_by(HazardZone.risk_level,HazardZone.name,HazardZone.id),
        'centers': db.select(EvacuationCenter).order_by(EvacuationCenter.name,EvacuationCenter.id),
        'contacts': db.select(EmergencyContact).order_by(EmergencyContact.agency,EmergencyContact.name,EmergencyContact.id),
        'equipment': db.select(DRRMEquipment).order_by(DRRMEquipment.name,DRRMEquipment.id),
        'supplies': db.select(ReliefSupply).order_by(ReliefSupply.name,ReliefSupply.id),
        'incidents': db.select(DRRMIncident).order_by(DRRMIncident.started_at.desc(),DRRMIncident.id.desc()),
        'alerts': db.select(EmergencyAlert).where(alert_filter).order_by(EmergencyAlert.issued_at.desc(),EmergencyAlert.id.desc()),
    }
    pagers={key:paginate_named(query,key+'_page') for key,query in queries.items()}
    return render_template("official/drrm.html", **{key:page.items for key,page in pagers.items()},
        pagers=pagers, all_centers=db.session.scalars(queries['centers']).all(),
        households=db.session.scalars(db.select(Household).order_by(Household.household_number)).all(),
        puroks=db.session.scalars(db.select(Purok).order_by(Purok.name)).all(), edit_alert=edit_alert,
        archived_alerts=archived_alerts)

@official_bp.post("/drrm/hazards")
@official_account_required
def drrm_hazard_create():
    db.session.add(HazardZone(name=request.form.get("name", "").strip(), hazard_type=request.form.get("hazard_type", "").strip(), description=request.form.get("description", "").strip() or None, purok_id=strict_form_value("purok_id", type=int) or None, risk_level=request.form.get("risk_level", "MEDIUM").upper(), status="ACTIVE"))
    db.session.commit(); flash("Hazard zone recorded.", "success"); return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/centers")
@official_account_required
def drrm_center_create():
    name, location = request.form.get("name", "").strip(), request.form.get("location", "").strip()
    try:
        if not name or not location: raise ValueError("Center name and location are required.")
        db.session.add(EvacuationCenter(name=name, address=location, location=location, capacity=strict_form_value("capacity", type=int) or 0, facilities=request.form.get("facilities", "").strip() or None, current_status=request.form.get("current_status", "AVAILABLE"), status="ACTIVE"))
        db.session.commit(); flash("Evacuation center recorded.", "success")
    except (ValueError, TypeError) as error: db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/contacts")
@official_account_required
def drrm_contact_create():
    db.session.add(EmergencyContact(name=request.form.get("name", "").strip(), agency=request.form.get("agency", "").strip() or None, contact_number=request.form.get("contact_number", "").strip(), role=request.form.get("role", "").strip() or None, availability_notes=request.form.get("availability_notes", "").strip() or None, status="ACTIVE"))
    db.session.commit(); flash("Emergency contact recorded.", "success"); return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/equipment")
@official_account_required
def drrm_equipment_create():
    db.session.add(DRRMEquipment(name=request.form.get("name", "").strip(), quantity=strict_form_value("quantity", 1, type=int), condition=request.form.get("condition", "GOOD"), storage_location=request.form.get("storage_location", "").strip() or None, notes=request.form.get("notes", "").strip() or None, status="ACTIVE"))
    db.session.commit(); flash("DRRM equipment recorded.", "success"); return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/supplies")
@official_account_required
def drrm_supply_create():
    db.session.add(ReliefSupply(name=request.form.get("name", "").strip(), quantity_on_hand=strict_form_value("quantity_on_hand", 0, type=float), unit=request.form.get("unit", "units").strip(), storage_location=request.form.get("storage_location", "").strip() or None, expiry_date=_date_field("expiry_date"), status="ACTIVE"))
    db.session.commit(); flash("Relief supply inventory updated.", "success"); return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/incidents")
@official_account_required
def drrm_incident_create():
    try:
        incident_date = _date_field("incident_date", date.today())
        started_at = datetime.fromisoformat(request.form.get("started_at")) if request.form.get("started_at") else datetime.now(timezone.utc)
        item = DRRMIncident(incident_type=request.form.get("incident_type", "").strip(), title=request.form.get("title", "").strip(), incident_date=incident_date, location=request.form.get("location", "").strip() or None, description=request.form.get("description", "").strip() or None, affected_households=strict_form_value("affected_households", 0, type=int), injuries=strict_form_value("injuries", 0, type=int), deaths=strict_form_value("deaths", 0, type=int), damage_assessment=request.form.get("damage_assessment", "").strip() or None, response_actions=request.form.get("response_actions", "").strip() or None, started_at=started_at, evacuation_center_id=strict_form_value("evacuation_center_id", type=int) or None, reported_by_id=current_user.id, status="ACTIVE")
        db.session.add(item); db.session.commit(); flash("Disaster incident recorded.", "success")
    except (ValueError, TypeError) as error: db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/incidents/<int:incident_id>/relief")
@official_account_required
def drrm_relief_create(incident_id):
    db.get_or_404(DRRMIncident, incident_id)
    db.session.add(ReliefRecord(incident_id=incident_id, evacuation_center_id=strict_form_value("evacuation_center_id", type=int) or None, household_id=strict_form_value("household_id", type=int) or None, item_description=request.form.get("item_description", "").strip(), quantity=strict_form_value("quantity", 0, type=float), distributed_at=datetime.now(timezone.utc), distributed_by_id=current_user.id, status="DISTRIBUTED"))
    db.session.commit(); flash("Relief distribution recorded.", "success"); return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/incidents/<int:incident_id>/damage")
@official_account_required
def drrm_damage_create(incident_id):
    db.get_or_404(DRRMIncident, incident_id)
    db.session.add(DamageReport(incident_id=incident_id, household_id=strict_form_value("household_id", type=int) or None, property_description=request.form.get("property_description", "").strip(), estimated_cost=strict_form_value("estimated_cost", type=float), assessment_notes=request.form.get("assessment_notes", "").strip() or None, status="RECORDED"))
    db.session.commit(); flash("Damage report recorded.", "success"); return redirect(url_for("official.drrm_dashboard"))

@official_bp.post("/drrm/alerts")
@official_account_required
def drrm_alert_create():
    try:
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        alert_level = request.form.get("alert_level", "ADVISORY").strip().upper() or "ADVISORY"
        expires_at = datetime.fromisoformat(request.form["expires_at"]) if request.form.get("expires_at") else None
        if not title or not message:
            raise ValueError("Title and message are required.")
        item = EmergencyAlert(title=title, message=message, alert_level=alert_level, issued_at=datetime.now(timezone.utc), expires_at=expires_at, issued_by_id=current_user.id, status="PUBLISHED")
        db.session.add(item)
        db.session.flush()
        archive_published_alerts(item.id)
        db.session.commit()
        flash("Emergency alert published.", "success")
    except (TypeError, ValueError) as error:
        db.session.rollback(); flash(str(error), "danger")
    return redirect(url_for("official.drrm_dashboard"))


@official_bp.get("/drrm/alerts/<int:alert_id>/edit")
@official_account_required
def drrm_alert_edit(alert_id):
    item = db.get_or_404(EmergencyAlert, alert_id)
    return redirect(url_for("official.drrm_dashboard", edit_alert_id=item.id, _anchor="drrm-alerts"))


@official_bp.post("/drrm/alerts/<int:alert_id>/update")
@official_account_required
def drrm_alert_update(alert_id):
    item = db.get_or_404(EmergencyAlert, alert_id)
    try:
        item.title = request.form.get("title", item.title).strip()
        item.message = request.form.get("message", item.message).strip()
        item.alert_level = (request.form.get("alert_level", item.alert_level) or item.alert_level).strip().upper()
        if "expires_at" in request.form:
            item.expires_at = datetime.fromisoformat(request.form["expires_at"]) if request.form["expires_at"] else None
        item.status = request.form.get("status", item.status).strip().upper() or item.status
        if not item.title or len(item.title) > 200 or not item.message:
            raise ValueError("Enter a title of up to 200 characters and an alert message.")
        if item.alert_level not in {"ADVISORY", "WARNING", "CRITICAL"} or item.status not in {"DRAFT", "PUBLISHED", "ARCHIVED"}:
            raise ValueError("Choose a valid alert level and status.")
        if item.status == "PUBLISHED":
            archive_published_alerts(item.id)
            item.status = "PUBLISHED"
        db.session.commit()
        flash("Emergency alert updated.", "success")
    except (TypeError, ValueError) as error:
        db.session.rollback(); flash(str(error), "danger")
        return redirect(url_for("official.drrm_dashboard", edit_alert_id=alert_id, _anchor="drrm-alerts"))
    return redirect(url_for("official.drrm_dashboard", alerts_view="archived" if item.status == "ARCHIVED" else None,
                            _anchor="drrm-alerts"))


@official_bp.post("/drrm/alerts/<int:alert_id>/delete")
@official_account_required
def drrm_alert_delete(alert_id):
    item = db.get_or_404(EmergencyAlert, alert_id)
    db.session.delete(item)
    db.session.commit()
    flash("Emergency alert deleted.", "success")
    return redirect(url_for("official.drrm_dashboard"))


@official_bp.post("/drrm/alerts/<int:alert_id>/archive")
@official_account_required
def drrm_alert_archive(alert_id):
    item = db.get_or_404(EmergencyAlert, alert_id)
    item.status = "ARCHIVED"
    db.session.commit()
    flash("Emergency alert archived.", "success")
    return redirect(url_for("official.drrm_dashboard", _anchor="drrm-alerts"))


@official_bp.post("/drrm/alerts/<int:alert_id>/restore")
@official_account_required
def drrm_alert_restore(alert_id):
    item = db.session.scalar(db.select(EmergencyAlert).where(EmergencyAlert.id == alert_id).with_for_update())
    if item is None:
        abort(404)
    if item.status == "ARCHIVED":
        item.status = "DRAFT"
        db.session.commit()
        flash("Emergency alert restored as a draft. Review it before publishing.", "success")
    return redirect(url_for("official.drrm_dashboard", alerts_view="archived", _anchor="drrm-alerts"))


@official_bp.get('/puroks')
@official_account_required
def purok_list():
    """Staff can inspect geographic records; administration owns changes."""
    from app.permissions import can
    if not can('puroks.view'):
        abort(403)
    query = db.select(Purok).order_by(Purok.name)
    term = request.args.get('q', '').strip()
    if term:
        query = query.where(Purok.name.ilike('%' + term + '%'))
    pagination = paginate_named(query)
    return render_template('official/puroks.html', puroks=pagination.items, pagination=pagination)


@official_bp.get('/residents/<int:resident_id>/registration-files/<kind>')
@official_account_required
def registration_file(resident_id, kind):
    from app.registration import send_registration_file
    return send_registration_file(db.get_or_404(Resident, resident_id), kind)


@official_bp.get("/analytics")
@official_account_required
def analytics():
    from app.admin import analytics_payload
    return render_template("admin/analytics.html", analytics=analytics_payload(),
        workspace_base="official/_official_base.html", analytics_endpoint="official.analytics",
        analytics_data_endpoint="official.analytics_data", dashboard_endpoint="official.dashboard",
        dashboard_label="Staff overview")


@official_bp.get("/analytics-data")
@official_account_required
def analytics_data():
    from flask import jsonify
    from app.admin import analytics_payload
    return jsonify(analytics_payload())


@official_bp.get("/report-center")
@official_account_required
def report_center():
    from app.admin import REPORT_CATALOG
    return render_template("admin/reports.html", catalog=REPORT_CATALOG,
        workspace_base="official/_official_base.html", reports_endpoint="official.report_center",
        activity_endpoint="official.reports", activity_label="Activity Logs",
        report_download_endpoint="official.report_download", report_export_endpoint="official.report_export")


@official_bp.get("/report-center/export/<kind>/<export_format>")
@official_account_required
def report_export(kind, export_format):
    from app.admin import render_report_export
    return render_report_export(kind, export_format, reports_endpoint="official.report_center")


@official_bp.get("/report-center/export")
@official_account_required
def report_download():
    from app.admin import render_report_export
    return render_report_export(request.args.get("kind", ""), request.args.get("format", "csv"), reports_endpoint="official.report_center")


@official_bp.before_request
def enforce_workspace_permission():
    if not current_user.is_authenticated:return
    from app.permissions import can
    name=(request.endpoint or '').split('.')[-1]
    permission=None
    if name.startswith('document'):permission='documents.review'
    elif name.startswith('blotter'):permission='blotters.manage'
    elif name.startswith(('resident','household','correction','welfare')):permission='residents.manage'
    elif name.startswith('purok'):permission='puroks.view'
    elif name.startswith(('report','analytics')):permission='reports.view'
    elif name=='dashboard':permission='dashboard'
    if permission and not can(permission):abort(403)

from . import walk_in  # Register staff intake routes.
