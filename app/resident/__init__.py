"""Resident self-service views restricted to the authenticated resident."""

from pathlib import Path
from datetime import date, datetime, timezone
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import or_
from werkzeug.exceptions import HTTPException

from app.auth.decorators import resident_owner_required
from app.blotter import add_party, new_case_number
from app.extensions import db
from app.documents import ensure_catalog, requirement_names, save_requirement_upload
from app.models import (
    BlotterCase, BlotterCaseAccess, BlotterCaseEvent, BlotterParty, 
    DocumentRequestEvent, DocumentRequirement, DocumentType, EmergencyAlert, 
    Notification, Purok, Request, ResidentCorrectionRequest, QueueRequest
)
from app.forms.resident import (
    CorrectionRequestForm, DocumentRequestForm, BlotterCaseForm, 
    QueueRequestForm, RequirementUploadForm
)
from app.validation import ValidationService
from app.pagination import paginate, Pagination

resident_bp = Blueprint("resident", __name__, url_prefix="/resident")
CORRECTABLE_FIELDS = {
    "first_name", "middle_name", "last_name", "birth_date", "sex", 
    "civil_status", "occupation", "contact_number", "email", 
    "address_line", "voter_status"
}


def current_user_resident():
    """Get the current user's resident profile safely."""
    if not current_user.is_authenticated:
        return None
    return getattr(current_user, 'resident', None)


@resident_bp.route('/profile-details', methods=['GET','POST'])
@resident_owner_required
def profile_details():
    from app.forms.profile_details import ProfileDetailsRequestForm
    from app.registration import (PROFILE_CORRECTION_FIELDS, correction_text, store_profile_uploads,
        profile_upload_snapshot, cleanup_replaced_uploads, cleanup_files)
    from app.audit import record
    from app.normalization import clean_text
    resident = current_user_resident()
    form = ProfileDetailsRequestForm(obj=resident)
    if form.validate_on_submit():
        created_files = []
        previous_files = profile_upload_snapshot(resident)
        try:
            pending = {item.field_name:item for item in db.session.scalars(db.select(ResidentCorrectionRequest)
                .where(ResidentCorrectionRequest.resident_id==resident.id, ResidentCorrectionRequest.status=='pending')
                .order_by(ResidentCorrectionRequest.id)).all()}
            count = 0
            for name in PROFILE_CORRECTION_FIELDS:
                if name not in request.form and not request.form.get('profile_details_present'):
                    continue
                value = form[name].data
                if isinstance(value,str): value = clean_text(value)
                # Keep an existing nationality when this optional input is blank.
                if name=='nationality' and not value: continue
                current = correction_text(getattr(resident,name))
                proposed = correction_text(value)
                item = pending.get(name)
                if proposed == current and item is None: continue
                if item is not None and item.proposed_value == proposed and item.reason == clean_text(form.reason.data):
                    continue
                if item is None:
                    item = ResidentCorrectionRequest(resident_id=resident.id, requested_by_id=current_user.id,
                        field_name=name, status='pending')
                    db.session.add(item)
                item.current_value = current
                item.proposed_value = proposed
                item.reason = clean_text(form.reason.data)
                count += 1
            store_profile_uploads(form,resident,created_files)
            if count:
                from app.notifications import notify_officials
                notify_officials('Registration details for review', 'A resident completed registration details. Review the changes in the Corrections Inbox.')
            if count or created_files:
                record('PROFILE_DETAILS_SUBMIT','registration','Resident',resident.id,
                    f'{count} fields submitted for review; {len(created_files)} private images uploaded')
            db.session.commit()
            cleanup_replaced_uploads(previous_files,resident)
            flash('Naisumite ang mga detalye para sa pagsusuri. Na-save ang mga napiling larawan.' if count else
                  ('Na-save ang mga napiling larawan.' if created_files else 'Walang nabagong detalye.'), 'success' if count or created_files else 'info')
            return redirect(url_for('resident.profile_details'))
        except Exception as error:
            db.session.rollback()
            cleanup_files(created_files)
            current_app.logger.exception('Resident details submission failed')
            flash(str(error) if isinstance(error,ValueError) else 'Hindi na-save ang form. Subukan muli.', 'danger')
    pending_items = db.session.scalars(db.select(ResidentCorrectionRequest)
        .where(ResidentCorrectionRequest.resident_id==resident.id,ResidentCorrectionRequest.status=='pending')
        .order_by(ResidentCorrectionRequest.id)).all()
    pending_count = len(pending_items)
    if request.method == 'GET':
        import json
        for item in pending_items:
            if item.field_name not in PROFILE_CORRECTION_FIELDS: continue
            try:
                value = json.loads(item.proposed_value) if item.field_name=='special_categories' else item.proposed_value
                form[item.field_name].process_data(value)
            except (ValueError,TypeError):
                continue
    return render_template('resident/profile_details.html',form=form,resident=resident,pending_count=pending_count)


@resident_bp.route("/")
@resident_owner_required
def dashboard():
    """Resident dashboard with latest information."""
    try:
        resident = current_user_resident()
        if not resident:
            flash("Resident profile not found. Please contact administrator.", "danger")
            return redirect(url_for("auth.logout"))
        
        # Get latest request
        latest_request = db.session.scalars(
            db.select(Request)
            .where(Request.resident_id == resident.id)
            .order_by(Request.created_at.desc())
        ).first()
        
        # Get latest queue request
        latest_queue = db.session.scalars(
            db.select(QueueRequest)
            .where(QueueRequest.resident_id == resident.id)
            .order_by(QueueRequest.created_at.desc())
        ).first()
        
        # Get latest emergency alert
        latest_alert = db.session.scalars(
            db.select(EmergencyAlert)
            .where(EmergencyAlert.status == "PUBLISHED")
            .order_by(EmergencyAlert.issued_at.desc())
        ).first()
        
        # Get unread notifications count
        unread_count = db.session.scalar(
            db.select(db.func.count(Notification.id))
            .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        ) or 0
        
        # Get recent requests sorted
        recent_requests = db.session.scalars(
            db.select(Request)
            .where(Request.resident_id == resident.id)
            .order_by(Request.created_at.desc())
            .limit(5)
        ).all()
        
        return render_template(
            "areas/resident_dashboard.html",
            resident=resident,
            latest_request=latest_request,
            latest_queue=latest_queue,
            latest_alert=latest_alert,
            now=datetime.now(),
            unread_count=unread_count,
            recent_requests=recent_requests,
        )
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error(f"Dashboard error: {e}")
        flash("Error loading dashboard. Please try again.", "danger")
        return redirect(url_for("main.index"))


@resident_bp.route("/profile")
@resident_owner_required
def profile():
    """Resident profile view."""
    resident = current_user_resident()
    if not resident:
        flash("Resident profile not found.", "danger")
        return redirect(url_for("main.index"))
    return render_template("areas/resident_profile.html", resident=resident)


@resident_bp.route("/household")
@resident_owner_required
def household():
    """Household information view."""
    try:
        resident = current_user_resident()
        household = resident.household
        members = household.residents if household else []
        
        return render_template(
            "resident/household.html", 
            resident=resident, 
            household=household, 
            members=members
        )
    except HTTPException:
        raise
    except Exception as e:
        flash("Error loading household information.", "danger")
        return redirect(url_for("resident.dashboard"))


@resident_bp.route("/profile-photo")
@resident_owner_required
def profile_photo():
    """Serve resident profile photo."""
    resident = current_user_resident()
    if not resident.profile_photo_filename:
        abort(404)
    
    try:
        return send_from_directory(
            Path(current_app.config["STORAGE_ROOT"]) / "profile_photos", 
            resident.profile_photo_filename
        )
    except FileNotFoundError:
        abort(404)


@resident_bp.route("/requests")
@resident_owner_required
def requests():
    """View all document requests."""
    resident = current_user_resident()
    pagination = paginate(db.select(Request).where(Request.resident_id == resident.id).order_by(Request.created_at.desc()), request.args.get("page", 1, type=int), 5)
    return render_template("areas/resident_requests.html", requests=pagination.items, pagination=pagination)


@resident_bp.route("/correction-requests", methods=["GET", "POST"])
@resident_owner_required
def correction_requests():
    """Handle correction requests for resident data."""
    resident = current_user_resident()
    form = CorrectionRequestForm()
    
    if request.method == "POST" and form.validate_on_submit():
        try:
            # Validate field name
            if form.field_name.data not in CORRECTABLE_FIELDS:
                flash("Please select a valid field for correction.", "danger")
                return render_template(
                    "resident/correction_requests.html", 
                    resident=resident, 
                    form=form, 
                    fields=sorted(CORRECTABLE_FIELDS),
                    requests=_get_correction_requests(resident.id)
                )
            
            # Create correction request
            item = ResidentCorrectionRequest(
                resident_id=resident.id,
                requested_by_id=current_user.id,
                field_name=ValidationService.sanitize_input(form.field_name.data),
                current_value=str(getattr(resident, form.field_name.data) or ""),
                proposed_value=ValidationService.sanitize_input(form.proposed_value.data),
                reason=ValidationService.sanitize_input(form.reason.data),
                status="pending",
            )
            
            db.session.add(item)
            from app.notifications import notify_officials
            notify_officials('New profile correction request', 'A resident submitted a profile correction for review in the Corrections Inbox.')
            db.session.commit()
            
            flash("Correction request submitted successfully.", "success")
            return redirect(url_for("resident.correction_requests"))
            
        except HTTPException:
            
            raise
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating correction request: {e}")
            flash("Error submitting correction request. Please try again.", "danger")
    
    # Handle form validation errors
    elif request.method == "POST" and form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error: {error}", "danger")
    
    try:
        pagination = paginate(db.select(ResidentCorrectionRequest).where(ResidentCorrectionRequest.resident_id == resident.id).order_by(ResidentCorrectionRequest.created_at.desc()), request.args.get("page", 1, type=int), 5)
        requests = pagination.items
        return render_template(
            "resident/correction_requests.html", 
            resident=resident, 
            form=form, 
            fields=sorted(CORRECTABLE_FIELDS),
            requests=requests,
            pagination=pagination
        )
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error(f"Error loading correction requests: {e}")
        flash("Error loading page. Please try again.", "danger")
        return redirect(url_for("resident.dashboard"))


def _get_correction_requests(resident_id):
    """Helper function to get correction requests for a resident."""
    return db.session.scalars(
        db.select(ResidentCorrectionRequest)
        .where(ResidentCorrectionRequest.resident_id == resident_id)
        .order_by(ResidentCorrectionRequest.created_at.desc())
    ).all()


@resident_bp.route("/documents")
@resident_owner_required
def documents():
    """View all document requests."""
    try:
        resident = current_user_resident()
        ensure_catalog()
        
        pagination = paginate(db.select(Request).where(Request.resident_id == resident.id).order_by(Request.created_at.desc()), request.args.get("page", 1, type=int), 5)
        items = pagination.items
        
        document_types = db.session.scalars(
            db.select(DocumentType)
            .where(DocumentType.status == "active")
            .order_by(DocumentType.name)
        ).all()
        
        from app.documents.engine import configured_fee, barangay_today
        return render_template(
            "resident/documents.html", 
            requests=items,
            pagination=pagination,
            document_types=document_types,
            document_fees={item.id: configured_fee(item, barangay_today()) for item in document_types}
        )
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error(f"Error loading documents: {e}")
        flash("Error loading documents page. Please try again.", "danger")
        return redirect(url_for("resident.dashboard"))


@resident_bp.route("/documents/new", methods=["GET", "POST"])
@resident_owner_required
def document_request_create():
    """Create a new document request."""
    try:
        resident = current_user_resident()
        from app.documents.engine import template_code,fields_for,resident_data,configured_fee,fee_confirmed,DETAIL_FIELDS,TEMPLATE_CODES
        document_types = [dt for dt in ensure_catalog() if (dt.template_code or TEMPLATE_CODES.get(dt.code)) in DETAIL_FIELDS and dt.status=='active']
        for dt in document_types:
            dt.request_fee=configured_fee(dt,date.today());dt.fee_confirmed=fee_confirmed(dt,date.today())
        selected_id=request.form.get('document_type_id',type=int) or request.args.get('document_type_id',type=int)
        selected=next((dt for dt in document_types if dt.id==selected_id),document_types[0] if document_types else None)
        field_map=fields_for(resident,template_code(selected)) if selected else {}
        form = DocumentRequestForm()
        
        # Populate document type choices
        form.document_type_id.choices = [
            (dt.id, f"{dt.name} (₱{dt.base_fee:.2f})") 
            for dt in document_types if dt.status == "active"
        ]
        
        if request.method == "POST" and form.validate_on_submit():
            try:
                document_type = db.session.get(DocumentType, form.document_type_id.data)
                if not document_type or document_type.status != "active" or document_type.id not in {dt.id for dt in document_types}:
                    flash("Please select a valid supported document.", "danger")
                    return render_template(
                        "resident/document_request_form.html", 
                        form=form, 
                        document_types=document_types, selected=selected, field_map=field_map, resident_info=resident_data(resident)
                    )
                
                from app.documents.engine import validate_details
                from html import unescape
                initial_request = request.form.get('request_stage') == 'initial'
                # Intake never invents certificate data. Verification and approval
                # require complete details before generation, separately from request approval.
                details = {} if initial_request else validate_details(resident,template_code(document_type),request.form)
                if not initial_request and (not form.description.data or not form.description.data.strip()): raise ValueError("Purpose is required.")
                # Identity comes exclusively from the authenticated resident account.
                item = Request(
                    request_number=f"REQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}", 
                    resident_id=resident.id, 
                    document_type_id=document_type.id, 
                    service_type=document_type.name, 
                    description=unescape(ValidationService.sanitize_input((form.description.data or '').strip())) or None,
                    status="PENDING", additional_data=details
                )
                
                db.session.add(item)
                db.session.flush()
                
                # Add event record
                db.session.add(DocumentRequestEvent(
                    request_id=item.id, 
                    to_status="PENDING", 
                    changed_by_id=current_user.id, 
                    notes="Request submitted by resident."
                ))
                
                # Add requirements
                for name in requirement_names(template_code(document_type),details,resident):
                    db.session.add(DocumentRequirement(
                        request_id=item.id, 
                        requirement_name=name, 
                        status="pending", 
                        is_required=True
                    ))
                
                # Add notification
                from app.notifications import notify_officials
                notify_officials('New document request', f'Request {item.request_number} is waiting for review in Document Requests.')
                db.session.add(Notification(
                    user_id=current_user.id, 
                    title="Document request submitted", 
                    message=f"Request {item.request_number} is pending review.", 
                    status="active"
                ))
                
                db.session.commit()
                flash("Document request submitted successfully.", "success")
                return redirect(url_for("resident.document_request_detail", request_id=item.id))
                
            except HTTPException:
                raise
            except ValueError as e:
                db.session.rollback();flash(str(e),"danger")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error creating document request: {e}")
                flash("Error submitting document request. Please try again.", "danger")
        
        # Handle form validation errors
        elif request.method == "POST" and form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error: {error}", "danger")
        
        return render_template(
            "resident/document_request_form.html", 
            form=form, 
            document_types=document_types,selected=selected,field_map=field_map,resident_info=resident_data(resident)
        )
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        current_app.logger.error(f"Error in document request creation: {e}")
        flash("Error loading document request form. Please try again.", "danger")
        return redirect(url_for("resident.documents"))


@resident_bp.route("/documents/<int:request_id>")
@resident_owner_required
def document_request_detail(request_id: int):
    """View document request details."""
    try:
        item = db.session.scalar(
            db.select(Request)
            .where(Request.id == request_id, Request.resident_id == current_user_resident().id)
        )
        
        if item is None:
            flash("Document request not found.", "danger")
            abort(404)
            
        return render_template("resident/document_request_detail.html", request=item)
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        current_app.logger.error(f"Error loading document request {request_id}: {e}")
        flash("Error loading document request details.", "danger")
        return redirect(url_for("resident.documents"))


@resident_bp.route("/documents/<int:request_id>/requirements/<int:requirement_id>/upload", methods=["POST"])
@resident_owner_required
def document_requirement_upload(request_id: int, requirement_id: int):
    """Upload a document requirement file."""
    try:
        resident = current_user_resident()
        
        # Verify request ownership
        item = db.session.scalar(
            db.select(Request).where(
                Request.id == request_id, 
                Request.resident_id == resident.id
            )
        )
        
        # Verify requirement exists
        requirement = db.session.scalar(
            db.select(DocumentRequirement).where(
                DocumentRequirement.id == requirement_id, 
                DocumentRequirement.request_id == request_id
            )
        )
        
        if item is None or requirement is None:
            flash("Document request or requirement not found.", "danger")
            abort(404)
        if item.status not in {"PENDING", "UNDER_REVIEW", "NEEDS_CORRECTION"}:
            flash("Requirements cannot be changed after processing has started.", "warning")
            return redirect(url_for("resident.document_request_detail", request_id=request_id))
        
        form = RequirementUploadForm()
        
        if form.validate_on_submit():
            previous_filename = requirement.filename
            new_filename = None
            try:
                new_filename = save_requirement_upload(form.requirement_file.data)
                requirement.filename = new_filename
                requirement.uploaded_by_id = current_user.id
                requirement.uploaded_at = datetime.now(timezone.utc)
                requirement.status = "uploaded"
                item.verified_at=None;item.verified_by_id=None
                
                if form.notes.data:
                    requirement.notes = ValidationService.sanitize_input(form.notes.data)
                
                db.session.add(Notification(
                    user_id=current_user.id, 
                    title="Requirement uploaded", 
                    message=f"A requirement was uploaded for {item.request_number}.", 
                    status="active"
                ))
                
                from app.audit import record
                from app.notifications import notify_officials
                notify_officials('Document requirement uploaded', f'Request {item.request_number} has an uploaded requirement ready for review.')
                record("DOCUMENT_UPLOAD", "documents", "DocumentRequirement", requirement.id, "Private requirement image uploaded/replaced")
                db.session.commit()
                from app.image_uploads import remove_image
                remove_image("document_requirements", previous_filename)
                flash("Requirement uploaded successfully.", "success")
                
            except HTTPException:
                
                raise
                
            except ValueError as e:
                db.session.rollback()
                from app.image_uploads import remove_image
                remove_image("document_requirements", new_filename)
                flash(str(e), "danger")
            except Exception as e:
                db.session.rollback()
                from app.image_uploads import remove_image
                remove_image("document_requirements", new_filename)
                current_app.logger.error(f"Error uploading requirement: {e}")
                flash("Error uploading file. Please try again.", "danger")
        else:
            # Handle file validation errors
            if form.errors:
                for field, errors in form.errors.items():
                    for error in errors:
                        flash(f"Upload error: {error}", "danger")
        
        return redirect(url_for("resident.document_request_detail", request_id=request_id))
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        current_app.logger.error(f"Error in document requirement upload: {e}")
        flash("Error processing upload. Please try again.", "danger")
        return redirect(url_for("resident.documents"))


@resident_bp.route("/documents/<int:request_id>/download")
@resident_owner_required
def document_download(request_id: int):
    """Download a completed document."""
    try:
        resident = current_user_resident()
        item = db.session.scalar(
            db.select(Request).where(
                Request.id == request_id, 
                Request.resident_id == resident.id
            )
        )
        
        if item is None:
            flash("Document request not found.", "danger")
            abort(404)
            
        if item.generated_filename:
            abort(403)  # Residents collect the signed, sealed certificate from the office.
        if item.status not in {"READY_FOR_RELEASE", "RELEASED"} or not item.generated_filename:
            flash("Document is not ready for download yet.", "warning")
            abort(404)
        
        if item.issued_document and item.issued_document.verification_token:
            abort(403)  # Official original certificates are available only to authorized staff.
        file_path = Path(current_app.config["STORAGE_ROOT"]) / "generated_documents"
        return send_from_directory(
            file_path, 
            item.generated_filename, 
            as_attachment=True, 
            download_name=f"{item.document_type.code}-{item.request_number}.html"
        )
        
    except FileNotFoundError:
        flash("Document file not found.", "danger")
        abort(404)
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error(f"Error downloading document {request_id}: {e}")
        flash("Error downloading document. Please try again.", "danger")
        return redirect(url_for("resident.documents"))


@resident_bp.route("/notifications")
@resident_owner_required
def notifications():
    """View all notifications."""
    try:
        from sqlalchemy import case, func, or_
        q=request.args.get('q','').strip()[:200]
        unread=request.args.get('unread')=='1'
        category=request.args.get('category','all')
        message=func.lower(func.coalesce(Notification.title,'')+' '+func.coalesce(Notification.message,''))
        groups=[('emergency',['emergency','alert','babala']),('health',['health','medical','kalusugan','philhealth']),('event',['event','assembly','kaganapan','meeting']),('service',['document','request','clearance','serbisyo'])]
        classification=case(*[(or_(*[message.contains(word) for word in words]),name) for name,words in groups],else_='announcement')
        query=db.select(Notification).where(Notification.user_id==current_user.id)
        if q: query=query.where(message.contains(q.lower(),autoescape=True))
        if unread: query=query.where(Notification.is_read.is_(False))
        counts=dict(db.session.execute(db.select(classification,func.count(Notification.id)).where(query.whereclause).group_by(classification)).all())
        if category in {'emergency','health','event','service','announcement'}: query=query.where(classification==category)
        else: category='all'
        pagination=paginate(query.order_by(Notification.created_at.desc(),Notification.id.desc()),request.args.get('page',1,type=int),5)
        unread_count=db.session.scalar(db.select(func.count(Notification.id)).where(Notification.user_id==current_user.id,Notification.is_read.is_(False))) or 0
        category_counts={**counts,'all':sum(counts.values())}
        category_links={key:url_for('resident.notifications',q=q,unread='1' if unread else '',category=key) for key in ['all','emergency','health','event','service','announcement']}
        return render_template("resident/notifications.html",notifications=pagination.items,pagination=pagination,unread_count=unread_count,category_counts=category_counts,category_links=category_links,category=category,q=q,unread=unread)
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        current_app.logger.error(f"Error loading notifications: {e}")
        flash("Error loading notifications.", "danger")
        return redirect(url_for("resident.dashboard"))


@resident_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@resident_owner_required
def notification_read(notification_id: int):
    """Mark a notification as read."""
    try:
        item = db.session.scalar(
            db.select(Notification).where(
                Notification.id == notification_id, 
                Notification.user_id == current_user.id
            )
        )
        
        if item is None:
            flash("Notification not found.", "danger")
            abort(404)
            
        item.is_read = True
        item.read_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return redirect(url_for("resident.notifications"))
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking notification as read: {e}")
        flash("Error updating notification.", "danger")
        return redirect(url_for("resident.notifications"))


@resident_bp.route("/notifications/read-all", methods=["POST"])
@resident_owner_required
def notifications_read_all():
    """Mark all notifications as read."""
    try:
        items = db.session.scalars(
            db.select(Notification).where(
                Notification.user_id == current_user.id, 
                Notification.is_read.is_(False)
            )
        ).all()
        
        stamped = datetime.now(timezone.utc)
        for item in items:
            item.is_read = True
            item.read_at = stamped
            
        db.session.commit()
        flash("All notifications marked as read.", "success")
        
        return redirect(url_for("resident.notifications"))
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking all notifications as read: {e}")
        flash("Error updating notifications.", "danger")
        return redirect(url_for("resident.notifications"))


# Phase 12 — centralized request queue
QUEUE_REQUEST_TYPES = {
    "DOCUMENT": "Document", 
    "COMPLAINT": "Complaint", 
    "APPOINTMENT": "Appointment", 
    "CONSULTATION": "Consultation", 
    "OTHER": "Other barangay service"
}


@resident_bp.route("/queue")
@resident_owner_required
def queue_requests():
    """View all queue requests."""
    try:
        resident = current_user_resident()
        pagination = paginate(db.select(QueueRequest).where(QueueRequest.resident_id == resident.id).order_by(QueueRequest.created_at.desc()), request.args.get("page", 1, type=int), 5)
        items = pagination.items
        
        return render_template(
            "resident/queue.html", 
            requests=items,
            pagination=pagination,
            request_types=QUEUE_REQUEST_TYPES
        )
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        current_app.logger.error(f"Error loading queue requests: {e}")
        flash("Error loading queue requests.", "danger")
        return redirect(url_for("resident.dashboard"))


@resident_bp.route("/queue/new", methods=["GET", "POST"])
@resident_owner_required
def queue_request_create():
    """Create a new queue request."""
    form = QueueRequestForm()
    
    if request.method == "POST" and form.validate_on_submit():
        try:
            resident = current_user_resident()
            
            item = QueueRequest(
                queue_number=f"Q-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}", 
                resident_id=resident.id, 
                request_type=form.request_type.data, 
                description=ValidationService.sanitize_input(form.description.data), 
                appointment_date=form.appointment_date.data, 
                appointment_time=form.appointment_time.data, 
                remarks=(
                    ValidationService.sanitize_input(form.priority_reason.data)
                    if form.priority_reason.data else None
                ),
                status="PENDING"
            )
            
            db.session.add(item)
            db.session.commit()
            
            flash(f"Request {item.queue_number} submitted successfully.", "success")
            return redirect(url_for("resident.queue_requests"))
            
        except HTTPException:
            
            raise
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating queue request: {e}")
            flash("Error submitting request. Please try again.", "danger")
    
    # Handle form validation errors
    elif request.method == "POST" and form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error: {error}", "danger")
    
    return render_template(
        "resident/queue_form.html", 
        form=form, 
        request_types=QUEUE_REQUEST_TYPES
    )


@resident_bp.route("/emergency-alerts")
@resident_owner_required
def emergency_alerts():
    """View emergency alerts."""
    try:
        page = max(1, request.args.get("page", 1, type=int) or 1)
        per_page = 5
        total_items = db.session.scalar(
            db.select(db.func.count(EmergencyAlert.id)).where(EmergencyAlert.status == "PUBLISHED")
        ) or 0
        total_pages = max(1, (total_items + per_page - 1) // per_page) if total_items else 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * per_page
        items = db.session.scalars(
            db.select(EmergencyAlert)
            .where(EmergencyAlert.status == "PUBLISHED")
            .order_by(EmergencyAlert.issued_at.desc())
            .offset(offset)
            .limit(per_page)
        ).all()
        return render_template(
            "resident/emergency_alerts.html",
            alerts=items,
            page=page,
            total_pages=total_pages,
            total_items=total_items,
            per_page=per_page,
            pagination=Pagination(items,page,per_page,total_items,total_pages),
        )
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error(f"Error loading emergency alerts: {e}")
        flash("Error loading emergency alerts.", "danger")
        return redirect(url_for("resident.dashboard"))


@resident_bp.route("/blotter")
@resident_owner_required
def blotter_cases():
    """View all blotter cases for the resident."""
    try:
        resident = current_user_resident()
        if not resident:
            flash("Resident profile required.", "danger")
            return redirect(url_for("main.index"))
            
        from app.incidents.resident_workspace import resident_reports
        pagination = resident_reports(resident.id,request.args.get('page',1,type=int),request.args.get('kind',''),request.args.get('q',''))
        return render_template("resident/blotter_cases.html", reports=pagination.items, pagination=pagination)
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        current_app.logger.error(f"Error loading blotter cases: {e}")
        flash("Error loading blotter cases. Please try again.", "danger")
        return redirect(url_for("resident.dashboard"))


@resident_bp.route("/blotter/new", methods=["GET", "POST"])
@resident_owner_required
def blotter_create():
    """Create a new blotter case/complaint."""
    resident = current_user_resident()
    if not resident:
        flash("Resident profile required to file complaints.", "danger")
        return redirect(url_for("main.index"))
    
    form = BlotterCaseForm()
    
    # Populate purok choices
    try:
        puroks = db.session.scalars(db.select(Purok).where(Purok.status == "active").order_by(Purok.name)).all()
        form.purok_id.choices = [(None, 'Select purok')] + [
            (p.id, p.name) for p in puroks
        ]
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error(f"Error loading puroks: {e}")
        puroks = []
        form.purok_id.choices = [(None, 'Select purok')]
    
    if request.method == "POST" and form.validate_on_submit():
        try:
            # Parse GPS coordinates if provided
            incident_latitude = None
            incident_longitude = None
            
            if form.incident_latitude.data and form.incident_longitude.data:
                try:
                    incident_latitude = float(form.incident_latitude.data)
                    incident_longitude = float(form.incident_longitude.data)
                    
                    # Validate coordinate ranges
                    if not (-90 <= incident_latitude <= 90) or not (-180 <= incident_longitude <= 180):
                        flash("Invalid GPS coordinates provided.", "warning")
                        raise ValueError("Invalid GPS coordinates.")
                        
                except (ValueError, TypeError):
                    flash("Invalid GPS coordinates format.", "warning")
                    form.incident_latitude.errors.append("Invalid GPS coordinates.")
                    return render_template("resident/blotter_form.html", form=form, puroks=puroks, today=date.today()), 400
            
            from app.blotter.submissions import submit_case
            case, associated = submit_case({
                'complainant_id': resident.id,
                'respondent_name': ValidationService.sanitize_input(form.respondent_name.data),
                'category': ValidationService.sanitize_input(form.category.data),
                'incident_date': form.incident_date.data,
                'incident_datetime': form.incident_datetime.data,
                'incident_location': ValidationService.sanitize_input(form.incident_location.data) if form.incident_location.data else None,
                'incident_latitude': incident_latitude,
                'incident_longitude': incident_longitude,
                'purok_id': form.purok_id.data or None,
                'narrative': ValidationService.sanitize_input(form.narrative.data),
            }, current_user, ValidationService.sanitize_input(form.respondent_contact.data), ValidationService.sanitize_input(form.respondent_notes.data))
            db.session.commit()
            flash(f"Identical submission associated with {case.case_number}." if associated else f"Complaint filed successfully as {case.case_number}.", "success")
            return redirect(url_for("resident.blotter_detail", case_id=case.id))
            
        except HTTPException:
            
            raise
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating blotter case: {e}")
            flash("Error filing complaint. Please try again.", "danger")
    
    # Handle form validation errors
    elif request.method == "POST" and form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error: {error}", "danger")
    
    return render_template("resident/blotter_form.html", form=form, puroks=puroks, today=date.today())


@resident_bp.route("/blotter/<int:case_id>")
@resident_owner_required
def blotter_detail(case_id: int):
    """View blotter case details."""
    try:
        resident = current_user_resident()
        if not resident:
            flash("Resident profile required.", "danger")
            return redirect(url_for("main.index"))
            
        case = db.session.scalar(
            db.select(BlotterCase)
            .outerjoin(BlotterCaseAccess, BlotterCaseAccess.case_id == BlotterCase.id)
            .where(
                BlotterCase.id == case_id,
                or_(
                    BlotterCase.complainant_id == resident.id, 
                    BlotterCaseAccess.resident_id == resident.id
                )
            )
        )
        
        if case is None:
            flash("Blotter case not found or you don't have access to it.", "danger")
            abort(404)
            
        return render_template("resident/blotter_detail.html", case=case)
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        current_app.logger.error(f"Error loading blotter case {case_id}: {e}")
        flash("Error loading case details.", "danger")
        return redirect(url_for("resident.blotter_cases"))


@resident_bp.get('/documents/<int:request_id>/requirements/<int:requirement_id>/view')
@resident_owner_required
def document_requirement_view(request_id, requirement_id):
    item = db.session.scalar(db.select(Request).where(Request.id == request_id, Request.resident_id == current_user.resident.id))
    requirement = db.session.scalar(db.select(DocumentRequirement).where(DocumentRequirement.id == requirement_id, DocumentRequirement.request_id == request_id))
    if item is None or requirement is None:
        abort(404)
    from app.documents.workflow import evidence_source, evidence_available
    if not evidence_available(requirement): abort(404)
    folder, filename = evidence_source(requirement)
    from app.audit import record
    record('DOCUMENT_VIEW', 'documents', 'DocumentRequirement', requirement.id)
    db.session.commit()
    from app.private_storage import private_image_path
    image_path = private_image_path(folder, filename)
    if image_path is None: abort(404)
    response = send_from_directory(image_path.parent, image_path.name, as_attachment=False)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@resident_bp.post('/documents/<int:request_id>/requirements/<int:requirement_id>/remove')
@resident_owner_required
def document_requirement_remove(request_id, requirement_id):
    item = db.session.scalar(db.select(Request).where(Request.id == request_id, Request.resident_id == current_user.resident.id))
    requirement = db.session.scalar(db.select(DocumentRequirement).where(DocumentRequirement.id == requirement_id, DocumentRequirement.request_id == request_id))
    if item is None or requirement is None:
        abort(404)
    if item.status not in {'PENDING', 'UNDER_REVIEW'}:
        abort(403)
    old = requirement.filename
    requirement.filename = None
    requirement.uploaded_by_id = None
    requirement.uploaded_at = None
    requirement.status = 'pending'
    from app.audit import record
    record('DOCUMENT_REMOVE', 'documents', 'DocumentRequirement', requirement.id)
    db.session.commit()
    from app.image_uploads import remove_image
    remove_image('document_requirements', old)
    flash('Requirement image removed.', 'success')
    return redirect(url_for('resident.document_request_detail', request_id=request_id))


@resident_bp.get('/registration-files/<kind>')
@resident_owner_required
def registration_file(kind):
    from app.registration import send_registration_file
    return send_registration_file(current_user.resident, kind)
