"""Administrator dashboard and system-management blueprint."""

from __future__ import annotations

import sqlite3
import secrets
from flask_login import current_user
import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import and_, func, or_, asc, desc
from sqlalchemy.exc import IntegrityError

from app.auth.decorators import roles_required, official_account_required
from app.form_values import strict_form_value
from app.extensions import db
from app.forms.admin import (
    UserForm, OfficialAccountForm, RoleForm, DocumentTypeForm, PurokForm, SystemSettingsForm,
    FeeScheduleForm, BackupRestoreForm, AuditLogFilterForm, ReportGenerationForm,
    BulkOperationForm, MaintenanceModeForm
)
from app.validation import ValidationService
from app.pagination import paginate_named
from app.email_service import send_official_credentials
from app.models import (
    AuditLog,
    BeneficiaryRegistry,
    BlotterCase,
    DRRMIncident,
    DocumentType,
    CollectionEntry,
    FeeConfiguration,
    HealthRegistry,
    Household,
    IssuedDocument,
    Official,
    Permission,
    Purok,
    ReliefRecord,
    Request as ServiceRequest,
    Resident,
    Role,
    SocialWelfareRegistry,
    BusinessRecord,
    SystemSetting,
    User,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


from app.querying import apply_sort


def admin_required(view):
    return roles_required("System Administrator")(view)


def log_action(action: str, entity_type: str, entity_id: int | None = None, details: str | None = None) -> None:
    from flask_login import current_user

    db.session.add(
        AuditLog(
            user_id=current_user.id,
            role=", ".join(sorted(role.name for role in current_user.roles)),
            action=action.upper(),
            module=entity_type,
            entity_type=entity_type,
            entity_id=entity_id,
            description=details,
            details=details,
            ip_address=request.remote_addr,
        )
    )


def commit_or_flash(success_message: str) -> bool:
    try:
        db.session.commit()
        flash(success_message, "success")
        return True
    except IntegrityError:
        db.session.rollback()
        flash("The operation could not be saved because it conflicts with an existing record.", "danger")
        return False


def age_on_date(birth_date: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def grouped_counts(query, label_column, value_column) -> dict[str, int]:
    return {str(row[0] or "Unknown"): int(row[1]) for row in db.session.execute(query).all()}


@admin_bp.get("/")
@admin_required
def dashboard():
    today = date.today()
    period = (request.args.get("period") or "all").lower()
    if period == "today":
        start = datetime.combine(today, datetime.min.time())
    elif period == "month":
        start = datetime.combine(today.replace(day=1), datetime.min.time())
    else:
        period = "all"
        start = None
    residents = db.session.scalars(db.select(Resident)).all()
    ages = [age_on_date(item.birth_date, today) for item in residents if item.birth_date]
    age_groups = Counter(
        "0-17" if age < 18 else "18-29" if age < 30 else "30-44" if age < 45 else "45-59" if age < 60 else "60+"
        for age in ages
    )
    gender = Counter((item.sex or "Unknown") for item in residents)
    purok_rows = db.session.execute(
        db.select(Purok.name, func.count(Resident.id)).join(Resident, Resident.purok_id == Purok.id, isouter=True).group_by(Purok.id, Purok.name).order_by(Purok.name)
    ).all()
    request_rows = db.session.execute(
        db.select(ServiceRequest.service_type, func.count(ServiceRequest.id)).group_by(ServiceRequest.service_type).order_by(func.count(ServiceRequest.id).desc())
    ).all()
    blotter_rows = db.session.execute(
        db.select(BlotterCase.status, func.count(BlotterCase.id)).group_by(BlotterCase.status)
    ).all()

    metrics = {
        "total_residents": len(residents),
        "total_households": db.session.scalar(db.select(func.count(Household.id))) or 0,
        "active_officials": db.session.scalar(db.select(func.count(Official.id)).where(Official.status == "active")) or 0,
        "pending_requests": db.session.scalar(
            db.select(func.count(ServiceRequest.id)).where(
                func.lower(ServiceRequest.status) == "pending",
                *([ServiceRequest.created_at >= start] if start else []),
            )
        ) or 0,
        "issued_documents": db.session.scalar(
            db.select(func.count(IssuedDocument.id)).where(*([IssuedDocument.issued_at >= start] if start else []))
        ) or 0,
        "open_blotter_cases": db.session.scalar(
            db.select(func.count(BlotterCase.id)).where(
                func.upper(BlotterCase.status).in_(["OPEN", "PENDING", "UNDER_MEDIATION", "HEARING_SCHEDULED"]),
                *([BlotterCase.created_at >= start] if start else []),
            )
        ) or 0,
        "registered_seniors": sum(1 for age in ages if age >= 60),
        "registered_pwd": db.session.scalar(db.select(func.count(HealthRegistry.id)).where(HealthRegistry.disability_details.is_not(None), HealthRegistry.disability_details != "")) or 0,
        "registered_4ps": db.session.scalar(db.select(func.count(SocialWelfareRegistry.id)).where(func.lower(SocialWelfareRegistry.category).like("%4p%"))) or 0,
        "solo_parents": db.session.scalar(db.select(func.count(SocialWelfareRegistry.id)).where(func.lower(SocialWelfareRegistry.category).like("%solo%"))) or 0,
        "drrm_incidents": db.session.scalar(db.select(func.count(DRRMIncident.id)).where(DRRMIncident.status.not_in(["closed", "resolved"]))) or 0,
    }
    charts = {
        "age": {"labels": list(age_groups.keys()), "values": list(age_groups.values())},
        "gender": {"labels": list(gender.keys()), "values": list(gender.values())},
        "purok": {"labels": [row[0] for row in purok_rows], "values": [row[1] for row in purok_rows]},
        "documents": {"labels": [row[0] for row in request_rows], "values": [row[1] for row in request_rows]},
        "blotter": {"labels": [row[0] for row in blotter_rows], "values": [row[1] for row in blotter_rows]},
        "service_demand": {"labels": [row[0] for row in request_rows], "values": [row[1] for row in request_rows]},
    }
    return render_template(
        "areas/admin_dashboard.html",
        metrics=metrics,
        charts=charts,
        period=period,
        official_form=OfficialAccountForm(),
        recent_audit=db.session.scalars(db.select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(5)).all(),
    )


@admin_bp.get("/dashboard-data")
@admin_required
def dashboard_data():
    return jsonify({"success": True, "metrics": {"residents": db.session.scalar(db.select(func.count(Resident.id))) or 0, "households": db.session.scalar(db.select(func.count(Household.id))) or 0, "blotter_cases": db.session.scalar(db.select(func.count(BlotterCase.id))) or 0, "service_requests": db.session.scalar(db.select(func.count(ServiceRequest.id))) or 0}, "updated_at": datetime.now(timezone.utc).isoformat()})


@admin_bp.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    form = UserForm()
    
    if form.validate_on_submit():
        try:
            # Create new user with validated data
            user = User(
                username=ValidationService.sanitize_input(form.username.data.lower()),
                email=ValidationService.sanitize_input(form.email.data.lower()),
                status="active",
                is_active=form.is_active.data
            )
            user.set_password(form.password.data)
            
            # Add role if specified
            if form.role_id.data:
                role = db.session.get(Role, form.role_id.data)
                if role:
                    user.roles.append(role)
            
            # Add optional profile information
            if form.profile_first_name.data:
                user.profile_first_name = ValidationService.sanitize_input(form.profile_first_name.data)
            if form.profile_last_name.data:
                user.profile_last_name = ValidationService.sanitize_input(form.profile_last_name.data)
            if form.profile_phone.data:
                user.profile_phone = ValidationService.sanitize_input(form.profile_phone.data)
            
            db.session.add(user)
            db.session.flush()
            from app.attendance.accounts import provision_account_personnel
            name = " ".join(filter(None, [form.profile_first_name.data, form.profile_last_name.data]))
            provision_account_personnel(user, personnel_id=form.attendance_personnel_id.data,
                                        full_name=name or None, actor_id=current_user.id)
            log_action("create", "User", user.id, user.username)
            
            if commit_or_flash("User created successfully."):
                return redirect(url_for("admin.users"))
                
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("User creation failed")
            flash("Account could not be saved. Check the supplied values and try again.", "danger")
    
    # Handle validation errors
    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field.title()}: {error}", "danger")
    
    # Build query with filters
    query = db.select(User)
    
    # Filter by status
    if request.args.get("status"):
        if request.args.get("status") == "active":
            query = query.where(User.is_active == True, User.status == "active")
        else:
            query = query.where(or_(User.is_active == False, User.status != "active"))
    
    # Filter by role
    if request.args.get("role"):
        query = query.join(User.roles).where(Role.name == request.args.get("role"))
    
    # Apply sorting
    query = apply_sort(query, User, default_column='username', default_order='asc')
    
    pagination = paginate_named(query)
    users = pagination.items
    roles = db.session.scalars(db.select(Role).where(func.lower(Role.name) != "barangay official").order_by(Role.name)).all()
    
    return render_template(
        "admin/users.html", 
        form=form, 
        users=users, 
        pagination=pagination, 
        roles=roles,
        filters=request.args
    )


@admin_bp.route("/official-accounts", methods=["GET", "POST"])
@admin_required
def official_accounts():
    """Only a System Administrator (Super Admin) can issue official accounts."""
    form = OfficialAccountForm()
    if form.validate_on_submit():
        try:
            role = db.session.scalar(
                db.select(Role).where(func.lower(Role.name) == "barangay official")
            )
            if role is None:
                role = Role(name="Barangay Official", description="Barangay official access")
                db.session.add(role)
                db.session.flush()

            official = Official(
                full_name=ValidationService.sanitize_input(form.full_name.data),
                position=ValidationService.sanitize_input(form.position.data),
                term_start=form.term_start.data,
                term_end=form.term_end.data,
                contact_number=ValidationService.sanitize_input(form.contact_number.data or "") or None,
                status="active",
            )
            db.session.add(official)
            db.session.flush()

            # Mirror the resident ID convention; suffix only if a legacy account
            # already occupies this username.
            username = f"SCN-OFF-{official.id:06d}"
            suffix = 1
            while db.session.scalar(
                db.select(User.id).where(func.lower(User.username) == username.casefold())
            ):
                username = f"SCN-OFF-{official.id:06d}-{suffix}"
                suffix += 1

            user = User(
                username=username,
                email=form.email.data,
                status="active",
                is_active=True,
                must_change_password=True,
                official_id=official.id,
            )
            temporary_password = secrets.token_urlsafe(18)
            user.set_password(temporary_password)
            user.roles.append(role)
            db.session.add(user)
            db.session.flush()
            from app.attendance.accounts import provision_account_personnel
            provision_account_personnel(user, personnel_id=form.attendance_personnel_id.data,
                                        actor_id=current_user.id)
            send_official_credentials(
                recipient=user.email,
                full_name=official.full_name,
                official_id=username,
                temporary_password=temporary_password,
            )
            log_action("create", "OfficialAccount", user.id, f"{user.username} — {official.full_name} ({official.position})")
            if commit_or_flash(
                f"Nagawa ang Barangay Official account: {user.username}. Naipadala ang login ID at temporary password sa {user.email}."
            ):
                return redirect(url_for("admin.official_accounts"))
        except IntegrityError:
            db.session.rollback()
            flash("Hindi naisave ang account. Maaaring nagamit na ang username o email.", "danger")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
        except RuntimeError as error:
            db.session.rollback()
            current_app.logger.warning("Official account email delivery blocked: %s", error)
            flash(f"Hindi nagawa ang official account. SMTP configuration error: {error}", "danger")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Official account creation/email delivery failed")
            flash("Hindi nagawa ang official account. Suriin ang SMTP configuration at subukang muli.", "danger")
    elif request.method == "POST":
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")

    official_role_only = and_(
        User.roles.any(func.lower(Role.name) == "barangay official"),
        ~User.roles.any(func.lower(Role.name) == "system administrator"),
    )
    official_filter = or_(User.official_id.is_not(None), official_role_only)
    pagination = paginate_named(db.select(User).where(official_filter).order_by(User.username))
    return render_template(
        "admin/official_accounts.html", form=form, officials=pagination.items,
        total_officials=pagination.total, page=pagination.page, per_page=pagination.per_page,
        total_pages=pagination.pages, pagination=pagination,
    )



@admin_bp.post("/official-accounts/<int:user_id>/delete")
@admin_required
def delete_official_account(user_id: int):
    """Delete an official login and its linked official profile."""
    user = db.get_or_404(User, user_id)
    is_official = user.official_id is not None or any(
        role.name.casefold() == "barangay official" for role in user.roles
    )
    if not is_official or user.id == current_user.id or any(r.name.casefold() == "system administrator" for r in user.roles):
        flash("Hindi maaaring burahin ang account na hindi Barangay Official.", "warning")
        return redirect(url_for("admin.official_accounts"))

    username = user.username
    official = user.official
    # Deleting a login must keep its saved personnel, RFID and attendance history.
    from app.models import PersonnelProfile, AttendanceAuditLog
    personnel = db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.user_id == user.id).with_for_update())
    if personnel:
        personnel.user = None
        db.session.add(AttendanceAuditLog(actor_id=current_user.id, entity_id=personnel.id,
            action="PERSONNEL_ACCOUNT_UNLINKED", details=f"Account #{user.id} deleted; personnel, RFID and attendance history retained."))
        db.session.flush()
    log_action("delete", "OfficialAccount", user.id, f"Deleted {username}")
    if official is not None:
        db.session.delete(official)
    db.session.delete(user)
    if commit_or_flash(f"Nabura ang official account na {username}."):
        return redirect(url_for("admin.official_accounts"))
    return redirect(url_for("admin.official_accounts"))


@admin_bp.post("/users/<int:user_id>/toggle")
@admin_required
def toggle_user(user_id: int):
    user = db.get_or_404(User, user_id)
    if user.resident is not None and user.status == "pending" and not user.is_active:
        flash("Hindi maaaring manu-manong i-toggle ang pending resident account. Gumamit ng tamang approval process.", "warning")
        return redirect(url_for("official.account_approvals"))
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "warning")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    user.status = "active" if user.is_active else "inactive"
    log_action("update_status", "User", user.id, user.status)
    commit_or_flash("User status updated.")
    return redirect(url_for("admin.users"))


@admin_bp.post("/users/<int:user_id>/roles")
@admin_required
def assign_user_role(user_id: int):
    user = db.get_or_404(User, user_id)
    role = db.get_or_404(Role, strict_form_value("role_id", type=int))
    if role.name.casefold() == "barangay official":
        flash("Gamitin ang Official Accounts upang gumawa ng official account kasama ang tamang profile.", "warning")
        return redirect(url_for("admin.users"))
    if role not in user.roles:
        user.roles.append(role)
    log_action("assign_role", "User", user.id, role.name)
    commit_or_flash("Role assigned.")
    return redirect(url_for("admin.users"))


@admin_bp.route("/roles", methods=["GET", "POST"])
@admin_required
def roles():
    from .management import ensure_permission_catalog
    ensure_permission_catalog()
    if request.method == "POST":
        from .management import populate
        try:
            role = Role()
            populate(role,"roles",request.form)
            db.session.add(role)
            db.session.flush()
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error,ValueError) else 'This entry already exists or conflicts with another record.', 'danger')
            return redirect(url_for("admin.roles"))
        log_action("create", "Role", role.id, role.name)
        if commit_or_flash("Role created successfully."):
            return redirect(url_for("admin.roles"))
    pagination = paginate_named(db.select(Role).order_by(Role.name))
    return render_template("admin/roles.html", roles=pagination.items, pagination=pagination, permissions=db.session.scalars(db.select(Permission).order_by(Permission.resource, Permission.action)).all())

@admin_bp.route("/permissions", methods=["GET", "POST"])
@admin_required
def permissions():
    if request.method == "POST":
        from .management import populate
        try:
            permission = Permission()
            populate(permission,"permissions",request.form)
            db.session.add(permission)
            db.session.flush()
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error,ValueError) else 'This entry already exists or conflicts with another record.', 'danger')
            return redirect(url_for("admin.permissions"))
        log_action("create", "Permission", permission.id, f"{permission.resource}:{permission.action}")
        if commit_or_flash("Permission created successfully."):
            return redirect(url_for("admin.permissions"))
    pagination = paginate_named(db.select(Permission).order_by(Permission.resource, Permission.action))
    from .management import BUILTIN_PERMISSIONS, permission_key
    return render_template("admin/permissions.html", permissions=pagination.items, pagination=pagination, protected_permissions=BUILTIN_PERMISSIONS, permission_key=permission_key)

@admin_bp.post("/roles/<int:role_id>/permissions")
@admin_required
def assign_permission(role_id: int):
    role = db.get_or_404(Role, role_id)
    permission = db.get_or_404(Permission, strict_form_value("permission_id", type=int))
    if permission not in role.permissions:
        role.permissions.append(permission)
    log_action("assign_permission", "Role", role.id, f"{permission.resource}:{permission.action}")
    commit_or_flash("Permission assigned.")
    return redirect(url_for("admin.roles"))


@admin_bp.route("/puroks", methods=["GET", "POST"])
@admin_required
def puroks():
    form = PurokForm()
    if form.validate_on_submit():
        try:
            purok = Purok(name=form.name.data, description=form.description.data or None, status="active")
            db.session.add(purok)
            db.session.flush()
            log_action("create", "Purok", purok.id, "Purok created")
            db.session.commit()
            flash("Purok created successfully.", "success")
            return redirect(url_for("admin.puroks"))
        except (IntegrityError, ValueError):
            db.session.rollback()
            form.name.errors.append("This Purok already exists or its name is invalid.")
    archived = request.args.get("view") == "archived"
    query = db.select(Purok).where(Purok.status != "active" if archived else Purok.status == "active")
    search = request.args.get("q", "").strip()
    if search:
        query = query.where(Purok.name.ilike(f"%{search}%"))
    pagination = paginate_named(query.order_by(Purok.name))
    return render_template("admin/puroks.html", form=form, puroks=pagination.items,
                           pagination=pagination, archived=archived)


@admin_bp.route("/puroks/<int:purok_id>/edit", methods=["GET", "POST"])
@admin_required
def purok_edit(purok_id):
    purok = db.get_or_404(Purok, purok_id)
    form = PurokForm(obj=purok)
    form.edit_purok_id = purok.id
    if form.validate_on_submit():
        try:
            from app.normalization import purok_identity
            purok.name, _, purok.purok_number = purok_identity(form.name.data)
            purok.description = form.description.data or None
            db.session.flush()
            log_action("update", "Purok", purok.id, "Purok updated")
            db.session.commit()
            flash("Purok updated.", "success")
            return redirect(url_for("admin.puroks"))
        except (IntegrityError, ValueError):
            db.session.rollback()
            form.name.errors.append("This Purok already exists or its name is invalid.")
    return render_template("admin/purok_edit.html", form=form, purok=purok)


@admin_bp.post("/puroks/<int:purok_id>/archive")
@admin_required
def purok_archive(purok_id):
    purok = db.session.scalar(db.select(Purok).where(Purok.id == purok_id).with_for_update())
    if purok is None:
        abort(404)
    action = request.form.get("archive_action") or ("archive" if purok.status == "active" else "restore")
    if action not in {"archive", "restore"}:
        abort(400)
    status = "inactive" if action == "archive" else "active"
    if purok.status != status:
        purok.status = status
        log_action(action, "Purok", purok.id)
        db.session.commit()
    flash("Purok archived." if action == "archive" else "Purok restored.", "success")
    return redirect(url_for("admin.puroks", view="archived" if action == "restore" else None,
                            q=request.args.get("q"), page=request.args.get("page"),
                            per_page=request.args.get("per_page")))


@admin_bp.route("/document-types", methods=["GET", "POST"])
@admin_required
def document_types():
    if request.method == "POST":
        from .management import populate
        try:
            document_type = DocumentType()
            populate(document_type,"document-types",request.form)
            db.session.add(document_type)
            db.session.flush()
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error,ValueError) else 'This entry already exists or conflicts with another record.', 'danger')
            return redirect(url_for("admin.document_types"))
        log_action("create", "DocumentType", document_type.id, document_type.code)
        if commit_or_flash("Document type created successfully."):
            return redirect(url_for("admin.document_types"))
    archived = request.args.get("view") == "archived"
    query = db.select(DocumentType).where(DocumentType.status == ("inactive" if archived else "active"))
    pagination = paginate_named(query.order_by(DocumentType.name))
    return render_template("admin/document_types.html", document_types=pagination.items, pagination=pagination,
                           archived=archived, archive_endpoint="admin.document_types")

@admin_bp.route("/fees", methods=["GET", "POST"])
@admin_required
def fees():
    if request.method == "POST":
        from .management import populate
        try:
            fee = FeeConfiguration()
            populate(fee,"fees",request.form)
            db.session.add(fee)
            db.session.flush()
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error,ValueError) else 'This entry already exists or conflicts with another record.', 'danger')
            return redirect(url_for("admin.fees"))
        log_action("create", "FeeConfiguration", fee.id)
        if commit_or_flash("Fee configuration saved."):
            return redirect(url_for("admin.fees"))
    archived = request.args.get("view") == "archived"
    query = db.select(FeeConfiguration).where(FeeConfiguration.status == ("inactive" if archived else "active"))
    pagination = paginate_named(query.order_by(FeeConfiguration.effective_from.desc()))
    document_types = db.session.scalars(db.select(DocumentType).where(DocumentType.status == "active").order_by(DocumentType.name)).all()
    return render_template("admin/fees.html", fees=pagination.items, pagination=pagination,
                           document_types=document_types, archived=archived, archive_endpoint="admin.fees")

@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    from app.site_information import public_information, save_public_information, FIELD_GROUPS
    from app.forms.site_information import BarangayInformationForm
    barangay_form = BarangayInformationForm(data=public_information())
    if request.method == 'POST' and request.form.get('action') == 'barangay_information':
        if barangay_form.validate_on_submit():
            save_public_information(barangay_form)
            log_action('update','SystemSetting',None,'Public barangay contact and office information')
            if commit_or_flash('Barangay information saved. Public pages now use these details.'):
                return redirect(url_for('admin.settings'))
        else:
            flash('Check the highlighted barangay information fields.', 'danger')
    elif request.method == "POST":
        key = request.form.get("setting_key", "").strip()
        setting = db.session.scalar(db.select(SystemSetting).where(SystemSetting.setting_key == key))
        if setting is None:
            setting = SystemSetting(setting_key=key)
            db.session.add(setting)
        setting.setting_value = request.form.get("setting_value", "")
        setting.description = request.form.get("description", "").strip() or None
        setting.is_secret = request.form.get("is_secret") == "on"
        db.session.flush()
        log_action("upsert", "SystemSetting", setting.id, key)
        if commit_or_flash("System setting saved."):
            return redirect(url_for("admin.settings"))
    pagination = paginate_named(db.select(SystemSetting).order_by(SystemSetting.setting_key))
    return render_template("admin/settings.html", settings=pagination.items, pagination=pagination,
                           barangay_form=barangay_form, barangay_info_groups=FIELD_GROUPS)


@admin_bp.get("/audit-logs")
@official_account_required
def audit_logs():
    query = db.select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)
    if request.args.get("action"): query = query.where(AuditLog.action == request.args["action"].upper())
    if request.args.get("module"): query = query.where(AuditLog.module == request.args["module"])
    if request.args.get("user_id", type=int): query = query.where(AuditLog.user_id == request.args.get("user_id", type=int))
    try:
        audit_start = date.fromisoformat(request.args["start"]) if request.args.get("start") else None
        audit_end = date.fromisoformat(request.args["end"]) if request.args.get("end") else None
    except ValueError:
        flash("Use valid YYYY-MM-DD audit date filters.", "danger")
        return redirect(url_for("admin.audit_logs"))
    if audit_start: query = query.where(AuditLog.created_at >= datetime.combine(audit_start, datetime.min.time()))
    if audit_end: query = query.where(AuditLog.created_at < datetime.combine(audit_end, datetime.max.time()))
    pagination = paginate_named(query)
    logs = pagination.items
    return render_template("admin/audit_logs.html", logs=logs, pagination=pagination, filters=request.args, users=db.session.scalars(db.select(User).order_by(User.username)).all())


@admin_bp.post("/backup")
@admin_required
def backup():
    if db.engine.url.get_backend_name() != "sqlite" or not db.engine.url.database or db.engine.url.database == ":memory:":
        flash("The built-in backup control supports SQLite development databases only. Use the database provider backup service for production databases.", "warning")
        return redirect(url_for("admin.dashboard"))
    source_path = Path(db.engine.url.database)
    if not source_path.is_absolute():
        source_path = Path(current_app.root_path).parent / source_path
    backup_dir = Path(current_app.instance_path) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"barangay_records_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db"
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    log_action("backup", "Database", details=str(backup_path.name))
    db.session.commit()
    return send_file(backup_path, as_attachment=True, download_name=backup_path.name, mimetype="application/vnd.sqlite3")


# Phase 15 — real-time analytics dashboard
def _month_key(value):
    if not value:
        return None
    return value.strftime("%Y-%m") if hasattr(value, "strftime") else str(value)[:7]

def analytics_payload():
    today = date.today()
    residents = db.session.scalars(db.select(Resident)).all()
    households = db.session.scalars(db.select(Household)).all()
    age_groups = Counter()
    for resident in residents:
        if resident.birth_date:
            age = age_on_date(resident.birth_date, today)
            age_groups["0-17" if age < 18 else "18-29" if age < 30 else "30-44" if age < 45 else "45-59" if age < 60 else "60+"] += 1
    sex = Counter((item.sex or "Unknown") for item in residents)
    civil = Counter((item.civil_status or "Unknown") for item in residents)
    purok = Counter((item.purok.name if item.purok else "Unassigned") for item in residents)
    household_sizes = Counter(str(len(item.residents)) for item in households)
    beneficiary_counts = Counter(item.category for item in db.session.scalars(db.select(BeneficiaryRegistry)).all())

    requests = db.session.scalars(db.select(ServiceRequest)).all()
    document_counts = Counter((item.document_type.name if item.document_type else item.service_type) for item in requests)
    requests_month = Counter(_month_key(item.created_at) for item in requests if item.created_at)
    processing_days = []
    for item in requests:
        if item.resolved_at and item.created_at:
            processing_days.append(max(0, (item.resolved_at - item.created_at).total_seconds() / 86400))
    pending = sum(1 for item in requests if str(item.status).upper() in {"PENDING", "UNDER_REVIEW", "PROCESSING"})

    blotters = db.session.scalars(db.select(BlotterCase)).all()
    blotter_categories = Counter((item.category or "Uncategorized") for item in blotters)
    blotter_purok = Counter((item.purok.name if item.purok else "Unassigned") for item in blotters)
    blotter_month = Counter(_month_key(item.incident_date) for item in blotters if item.incident_date)
    blotter_resolution = []
    for item in blotters:
        if item.closed_at and item.created_at:
            blotter_resolution.append(max(0, (item.closed_at - item.created_at).total_seconds() / 86400))

    incidents = db.session.scalars(db.select(DRRMIncident)).all()
    relief = db.session.scalars(db.select(ReliefRecord)).all()
    incident_month = Counter(_month_key(item.incident_date or item.started_at) for item in incidents)
    relief_month = Counter(_month_key(item.distributed_at) for item in relief)
    relief_quantity = sum(float(item.quantity or 0) for item in relief)
    center_usage = Counter((item.evacuation_center.name if item.evacuation_center else "No center assigned") for item in relief)
    center_incident_usage = Counter((item.evacuation_center.name if item.evacuation_center else "No center assigned") for item in incidents)
    for label, count in center_incident_usage.items(): center_usage[label] += count

    def series(counter):
        pairs = sorted((key, value) for key, value in counter.items() if key is not None)
        return {"labels": [str(key) for key, _ in pairs], "values": [int(value) for _, value in pairs]}
    return {
        "population": {"total": len(residents), "sex": series(sex), "age_groups": series(age_groups), "civil_status": series(civil), "purok": series(purok), "household_size": series(household_sizes)},
        "social": {"labels": ["SENIOR", "PWD", "4PS", "SOLO_PARENT", "PREGNANT", "NEWBORN"], "values": [beneficiary_counts.get(key, 0) for key in ["SENIOR", "PWD", "4PS", "SOLO_PARENT", "PREGNANT", "NEWBORN"]]},
        "services": {"documents": series(document_counts), "monthly": series(requests_month), "average_processing_days": round(sum(processing_days) / len(processing_days), 2) if processing_days else 0, "pending": pending},
        "peace_order": {"categories": series(blotter_categories), "purok": series(blotter_purok), "monthly": series(blotter_month), "average_resolution_days": round(sum(blotter_resolution) / len(blotter_resolution), 2) if blotter_resolution else 0},
        "drrm": {"incidents": series(incident_month), "affected_households": sum(int(item.affected_households or 0) for item in incidents), "relief_distribution": series(relief_month), "relief_quantity": relief_quantity, "evacuation_usage": series(center_usage)},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

@admin_bp.get("/analytics")
@official_account_required
def analytics():
    return render_template("admin/analytics.html", analytics=analytics_payload())


@admin_bp.get("/blotter-map")
@admin_required 
def blotter_map():
    """View all blotter cases on an interactive Google Maps map."""
    try:
        # Get all blotter cases with GPS coordinates
        cases = db.session.scalars(
            db.select(BlotterCase)
            .where(
                BlotterCase.incident_latitude.is_not(None),
                BlotterCase.incident_longitude.is_not(None)
            )
            .order_by(BlotterCase.created_at.desc())
        ).all()
        
        # Prepare cases data for JSON serialization
        cases_data = []
        for case in cases:
            complainant_name = "Anonymous"
            if case.complainant:
                complainant_name = case.complainant.full_name
            
            cases_data.append({
                'id': case.id,
                'case_number': case.case_number,
                'category': case.category or 'Unknown',
                'status': case.status,
                'incident_date': case.incident_date.isoformat() if case.incident_date else None,
                'incident_location': case.incident_location or '',
                'incident_latitude': float(case.incident_latitude),
                'incident_longitude': float(case.incident_longitude),
                'complainant': complainant_name,
                'respondent_name': case.respondent_name or 'Unknown',
                'narrative': case.narrative or ''
            })
        
        return render_template(
            "admin/blotter_map.html", 
            cases_data=cases_data,
            total_cases=len(cases_data)
        )
        
    except Exception as e:
        current_app.logger.error(f"Error loading blotter map: {e}")
        flash("Error loading complaint map. Please try again.", "danger")
        return redirect(url_for("admin.dashboard"))

@admin_bp.get("/analytics-data")
@official_account_required
def analytics_data():
    return jsonify(analytics_payload())


# Phase 16 — protected report center and exports
REPORT_CATALOG = {
    "residents": "Resident master list", "households": "Household list", "population": "Population report", "puroks": "Purok report", "documents": "Document issuance report", "requests": "Request report", "blotter": "Blotter report", "health": "Health registry report", "social": "Social welfare report", "collections": "Collection report", "drrm": "DRRM report",
}

def _report_date(value):
    if value is None: return None
    return value.date() if hasattr(value, "date") else value

def _in_range(value, start, end):
    value = _report_date(value)
    return (start is None or (value and value >= start)) and (end is None or (value and value <= end))

def report_rows(kind, start=None, end=None):
    if kind == "residents":
        return (["ID", "Name", "Sex", "Birth date", "Civil status", "Purok", "Status"], [[r.id, f"{r.last_name}, {r.first_name}", r.sex or "", r.birth_date or "", r.civil_status or "", r.purok.name if r.purok else "", r.status] for r in db.session.scalars(db.select(Resident).order_by(Resident.last_name, Resident.first_name)).all() if _in_range(r.created_at, start, end)])
    if kind == "households":
        return (["Household number", "Address", "Purok", "Members", "Status"], [[h.household_number, h.address_line, h.purok.name if h.purok else "", len(h.residents), h.status] for h in db.session.scalars(db.select(Household).order_by(Household.household_number)).all() if _in_range(h.created_at, start, end)])
    if kind == "population":
        residents = [r for r in db.session.scalars(db.select(Resident)).all() if _in_range(r.created_at, start, end)]; counts = Counter((r.sex or "Unknown") for r in residents)
        return (["Measure", "Category", "Count"], [["Sex", key, value] for key, value in sorted(counts.items())])
    if kind == "puroks":
        return (["Purok", "Residents", "Households"], [[p.name, len(p.residents), len(p.households)] for p in db.session.scalars(db.select(Purok).order_by(Purok.name)).all() if _in_range(p.created_at, start, end)])
    if kind == "documents":
        items = [x for x in db.session.scalars(db.select(IssuedDocument).order_by(IssuedDocument.issued_at.desc())).all() if _in_range(x.issued_at, start, end)]
        return (["Document number", "Type", "Resident", "Issued at", "Status"], [[x.document_number, x.document_type.name, f"{x.resident.last_name}, {x.resident.first_name}", x.issued_at, x.status] for x in items])
    if kind == "requests":
        items = [x for x in db.session.scalars(db.select(ServiceRequest).order_by(ServiceRequest.created_at.desc())).all() if _in_range(x.created_at, start, end)]
        return (["Request number", "Resident", "Service", "Created", "Status", "Resolved"], [[x.request_number, f"{x.resident.last_name}, {x.resident.first_name}", x.service_type, x.created_at, x.status, x.resolved_at or ""] for x in items])
    if kind == "blotter":
        items = [x for x in db.session.scalars(db.select(BlotterCase).order_by(BlotterCase.incident_date.desc())).all() if _in_range(x.incident_date, start, end)]
        return (["Case number", "Complainant", "Category", "Incident date", "Purok", "Status", "Closed"], [[x.case_number, f"{x.complainant.last_name}, {x.complainant.first_name}", x.category, x.incident_date, x.purok.name if x.purok else "", x.status, x.closed_at or ""] for x in items])
    if kind == "health":
        items = db.session.scalars(db.select(HealthRegistry).order_by(HealthRegistry.created_at.desc())).all()
        return (["Resident", "Blood type", "Medical conditions", "Allergies", "Disability details", "Status"], [[f"{x.resident.last_name}, {x.resident.first_name}", x.blood_type or "", x.medical_conditions or "", x.allergies or "", x.disability_details or "", x.status] for x in items if _in_range(x.created_at, start, end)])
    if kind == "social":
        items = db.session.scalars(db.select(BeneficiaryRegistry).order_by(BeneficiaryRegistry.registered_date.desc())).all()
        return (["Resident", "Registry", "Registered", "Application status", "Notes"], [[f"{x.resident.last_name}, {x.resident.first_name}", x.category, x.registered_date, x.application_status, x.application_notes or ""] for x in items if _in_range(x.registered_date, start, end)])
    if kind == "collections":
        items = [x for x in db.session.scalars(db.select(CollectionEntry).order_by(CollectionEntry.transaction_date.desc())).all() if _in_range(x.transaction_date, start, end)]
        return (["Transaction", "Resident", "Service", "Amount", "Payment method", "Date", "Reference"], [[x.transaction_number, f"{x.resident.last_name}, {x.resident.first_name}", x.service, x.amount, x.payment_method, x.transaction_date, x.reference_number or ""] for x in items])
    if kind == "drrm":
        items = [x for x in db.session.scalars(db.select(DRRMIncident).order_by(DRRMIncident.started_at.desc())).all() if _in_range(x.incident_date or x.started_at, start, end)]
        return (["Incident", "Type", "Date", "Location", "Affected households", "Injuries", "Deaths", "Damage assessment", "Response actions"], [[x.title, x.incident_type, x.incident_date or x.started_at, x.location or "", x.affected_households, x.injuries, x.deaths, x.damage_assessment or "", x.response_actions or ""] for x in items])
    raise ValueError("Unknown report type")

@admin_bp.get("/reports")
@official_account_required
def reports():
    return render_template("admin/reports.html", catalog=REPORT_CATALOG)

@admin_bp.get("/reports/export")
@official_account_required
def report_download():
    return render_report_export(request.args.get("kind", ""), request.args.get("format", "csv"))


@admin_bp.get("/reports/export/<kind>/<export_format>")
@official_account_required
def report_export(kind, export_format):
    return render_report_export(kind, export_format)


def render_report_export(kind, export_format, reports_endpoint="admin.reports"):
    if kind not in REPORT_CATALOG or export_format not in {"csv", "pdf"}: return ("Unknown report or export format", 404)
    try:
        start = date.fromisoformat(request.args["start"]) if request.args.get("start") else None
        end = date.fromisoformat(request.args["end"]) if request.args.get("end") else None
    except ValueError:
        flash("Use valid YYYY-MM-DD date filters.", "danger"); return redirect(url_for(reports_endpoint))
    if start and end and start > end:
        flash("Report start date must be on or before the end date.", "danger"); return redirect(url_for(reports_endpoint))
    headers, rows = report_rows(kind, start, end)
    log_action("EXPORT_REPORT", "Report", details=f"{REPORT_CATALOG[kind]} ({export_format.upper()}) {start or ''} to {end or ''}")
    db.session.commit()
    filename = f"{kind}_report_{start or 'all'}_{end or 'all'}"
    if export_format == "csv":
        def csv_value(value):
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                return "'" + value
            return value
        stream = io.StringIO(); writer = csv.writer(stream); writer.writerow(headers); writer.writerows([[csv_value(value) for value in row] for row in rows]); stream.seek(0)
        return send_file(io.BytesIO(stream.getvalue().encode("utf-8-sig")), as_attachment=True, download_name=f"{filename}.csv", mimetype="text/csv")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    output = io.BytesIO(); doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=0.35*inch, leftMargin=0.35*inch, topMargin=0.35*inch, bottomMargin=0.35*inch)
    styles = getSampleStyleSheet(); story = [Paragraph(REPORT_CATALOG[kind], styles["Title"]), Paragraph(f"Date range: {start or 'All'} to {end or 'All'} · Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]), Spacer(1, 0.15*inch)]
    from html import escape
    cell_style = ParagraphStyle("ReportCell", fontSize=7, leading=9, wordWrap="CJK")
    header_style = ParagraphStyle("ReportHeader", parent=cell_style, textColor=colors.white, fontName="Helvetica-Bold")
    table_data = [[Paragraph(escape(str(value)), header_style) for value in headers]]
    table_data += [[Paragraph(escape(str(value if value is not None else "")), cell_style) for value in row] for row in rows]
    if not rows:
        story.append(Paragraph("No records match the selected date range.", styles["Normal"]))
    table = Table(table_data, colWidths=[doc.width / len(headers)] * len(headers), repeatRows=1, splitInRow=1); table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0d6efd")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.25, colors.grey), ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP")]))
    story.append(table); doc.build(story); output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"{filename}.pdf", mimetype="application/pdf")

from . import management
