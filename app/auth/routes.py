"""Authentication routes and account lifecycle workflows."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import LoginAttempt, Purok, Resident, Role, User
from app.audit import record as audit_record
from app.email_service import send_password_reset_otp, send_verification_email
from app.forms import LoginForm, RegisterForm, ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm, VerifyOtpForm, NewPasswordForm
from app.validation import ValidationService

from .session import (
    create_session_record,
    hash_token,
    post_login_url,
    revoke_current_session,
    revoke_user_sessions,
    utc_now,
    utc_timestamp,
)


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def now():
    return datetime.now(timezone.utc)


def is_expired(value) -> bool:
    """Compare database timestamps safely across SQLite and server databases."""
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < now()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def valid_password(password: str) -> bool:
    return len(password) >= current_app.config["PASSWORD_MIN_LENGTH"]


def client_ip() -> str:
    return (request.remote_addr or "unknown")[:45]


def safe_next_url(target: str | None) -> str | None:
    """Allow only local absolute paths as post-login redirects."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    if "\\" in target or any(ord(character) < 32 for character in target):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def attempt_record(identifier: str) -> LoginAttempt:
    record = db.session.scalar(
        db.select(LoginAttempt).where(
            LoginAttempt.identifier == identifier,
            LoginAttempt.ip_address == client_ip(),
        )
    )
    if record is None:
        record = LoginAttempt(identifier=identifier, ip_address=client_ip())
        db.session.add(record)
        db.session.flush()
    return record


def locked(record: LoginAttempt) -> bool:
    if record.locked_until is None:
        return False
    locked_until = record.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until > now()


def record_failed_login(record: LoginAttempt) -> None:
    record.failed_attempts += 1
    record.last_attempt_at = now()
    if record.failed_attempts >= current_app.config["LOGIN_MAX_ATTEMPTS"]:
        record.locked_until = now() + timedelta(minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"])
    db.session.commit()


def clear_failed_logins(record: LoginAttempt) -> None:
    record.failed_attempts = 0
    record.locked_until = None
    record.last_attempt_at = now()
    db.session.commit()


def _full_name(user: User) -> str:
    resident = user.resident
    if resident is None:
        return user.email
    return " ".join(part for part in (resident.first_name, resident.middle_name, resident.last_name, resident.suffix) if part)


def _verification_url(token: str) -> str:
    path = url_for("auth.verify_email", token=token, _external=False)
    base = current_app.config.get("APP_BASE_URL")
    return f"{base}{path}" if base else url_for("auth.verify_email", token=token, _external=True)


def issue_email_verification(user: User) -> bool:
    """Create a fresh single-use verification link and email it; return False if delivery fails."""
    hours = current_app.config["EMAIL_VERIFICATION_TOKEN_HOURS"]
    token = secrets.token_urlsafe(32)
    user.activation_token_hash = token_digest(token)
    user.activation_expires_at = now() + timedelta(hours=hours)
    db.session.commit()
    try:
        send_verification_email(
            recipient=user.email,
            full_name=_full_name(user),
            verification_url=_verification_url(token),
            valid_hours=hours,
        )
    except Exception:
        current_app.logger.exception("Verification email delivery failed for user id %s", user.id)
        return False
    return True


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(post_login_url())

    from app.registration import apply_profile, cleanup_files
    form = RegisterForm()
    
    # Load puroks for the template
    from app.models.people import Purok
    puroks = db.session.scalars(
        db.select(Purok).where(Purok.status == 'active').order_by(Purok.name)
    ).all()
    
    if request.method == "POST":
        if ValidationService.validate_form(form, flash_errors=True):
            created_files = []
            registration_saved = False
            try:
                # Create resident record
                resident = Resident(
                    first_name=form.first_name.data,
                    middle_name=form.middle_name.data,
                    last_name=form.last_name.data,
                    suffix=form.suffix.data,
                    sex=form.sex.data or None,
                    birth_date=form.birth_date.data,
                    civil_status=form.civil_status.data or None,
                    nationality=form.nationality.data.strip(),
                    contact_number=form.contact_number.data,
                    address_line=form.address_line.data,
                    occupation=form.occupation.data,
                    voter_status=form.voter_status.data,
                    email=form.email.data,
                    purok_id=form.purok_id.data if form.purok_id.data else None,
                    status="pending",
                    is_verified=False,
                )
                
                # Keep the account unusable until a staff member approves it.
                user = User(
                    username=f"PENDING-{secrets.token_hex(16)}",
                    email=form.email.data,
                    status="pending",
                    is_active=False,
                    privacy_consent_at=now(),
                    privacy_consent_version=current_app.config["PRIVACY_NOTICE_VERSION"],
                    terms_accepted_at=now(),
                    resident=resident,
                )
                user.set_password(secrets.token_urlsafe(32))
                
                # Assign resident role
                role = db.session.scalar(db.select(Role).where(Role.name == "Resident"))
                if role is None:
                    role = Role(name="Resident", description="Registered barangay resident")
                    db.session.add(role)
                user.roles.append(role)
                
                apply_profile(form, resident, user, created_files)
                db.session.add(user)
                from app.audit import record
                db.session.flush()
                record("REGISTER", "auth", "Resident", resident.id, "Registration profile and private verification images submitted")
                from app.notifications import notify_officials
                notify_officials('New resident registration', 'A resident submitted an account registration. Check Account Approvals for verification and review.')
                db.session.commit()
                registration_saved = True
                
                email_sent = issue_email_verification(user)
                if email_sent:
                    flash("Registration submitted. Tingnan ang iyong email para sa verification link.", "success")
                else:
                    flash("Naisumite ang registration pero hindi naipadala ang verification email. Pindutin ang 'Ipadala muli'.", "warning")
                return render_template("auth/activation_created.html", email=user.email, email_sent=email_sent)
                
            except IntegrityError:
                db.session.rollback()
                if not registration_saved: cleanup_files(created_files)
                flash("Registration failed due to duplicate information. Please check your username and email.", "danger")
            except ValueError as e:
                db.session.rollback()
                if not registration_saved: cleanup_files(created_files)
                flash(str(e), "danger")
            except Exception as e:
                db.session.rollback()
                if not registration_saved: cleanup_files(created_files)
                current_app.logger.error(f"Registration error: {e}")
                flash("An error occurred during registration. Please try again.", "danger")

    return render_template("auth/register.html", form=form, errors=form.errors, puroks=puroks)


@auth_bp.get("/verify-email/<token>")
def verify_email(token: str):
    """Confirm the registrant owns the email address. This does not activate the account."""
    user = db.session.scalar(db.select(User).where(User.activation_token_hash == token_digest(token)))
    if user is None or is_expired(user.activation_expires_at):
        return render_template("auth/email_verified.html", success=False), 400
    user.email_verified_at = now()
    user.activation_token_hash = None
    user.activation_expires_at = None
    audit_record("VERIFY_EMAIL", "auth", "User", user.id, "Registration email verified")
    db.session.commit()
    return render_template("auth/email_verified.html", success=True)


@auth_bp.post("/resend-verification")
def resend_verification():
    email = request.form.get("email", "").strip().lower()
    user = db.session.scalar(
        db.select(User).where(func.lower(User.email) == email, User.status == "pending", User.is_active.is_(False))
    )
    if user is not None and user.email_verified_at is None:
        cooldown = current_app.config["EMAIL_VERIFICATION_RESEND_SECONDS"]
        hours = current_app.config["EMAIL_VERIFICATION_TOKEN_HOURS"]
        last_sent = None
        if user.activation_expires_at is not None:
            last_sent = user.activation_expires_at - timedelta(hours=hours)
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
        if last_sent is None or (now() - last_sent).total_seconds() >= cooldown:
            issue_email_verification(user)
    # Same message whether or not the address exists, so this cannot be used to probe registrations.
    flash("Kung may pending na registration para sa email na iyon, may bagong verification link na ipinadala.", "info")
    return render_template("auth/activation_created.html", email=email, email_sent=True), 200


@auth_bp.get("/activate/<token>")
def activate(token: str):
    # Legacy links are deliberately inert; only the staff approval workflow activates accounts.
    current_app.logger.info("Ignored legacy self-activation URL")
    flash("Admin o barangay official lamang ang maaaring mag-activate ng resident account.", "warning")
    return redirect(url_for("auth.login"))


LOGIN_ROLES = {
    "resident": ("Resident", "resident.dashboard"),
    "staff": ("Barangay Official", "official.dashboard"),
    "captain": ("System Administrator", "admin.dashboard"),
}


def can_sign_in_as(user, selected_role):
    required = LOGIN_ROLES.get(selected_role)
    return required is not None and any(
        role.status == "active" and role.name.casefold() == required[0].casefold()
        for role in user.roles
    )


def selected_workspace(user, selected_role):
    if selected_role == "resident" and user.resident is None:
        return url_for("main.index")
    dashboard = url_for(LOGIN_ROLES[selected_role][1])
    next_url = safe_next_url(request.args.get("next"))
    prefix = dashboard.rsplit("/", 1)[0] + "/"
    return next_url if next_url and urlsplit(next_url).path.startswith(prefix) else dashboard


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(post_login_url())

    form = LoginForm()
    
    if request.method == "POST":
        selected_role = request.form.get("role", "")
        if selected_role not in LOGIN_ROLES:
            flash("Select a valid sign-in role.", "warning")
            return render_template("auth/login.html", form=form, errors=form.errors), 400
        if ValidationService.validate_form(form, flash_errors=False):
            # Official IDs are generated in uppercase (SCN-OFF-xxxxxx), while
            # users may paste them with spaces or different capitalization.
            identifier = (form.identifier.data or "").strip().lower()
            password = form.password.data
            
            record = attempt_record(identifier or "unknown")
            if locked(record):
                flash("Too many failed attempts. Try again later.", "danger")
                return render_template("auth/login.html", form=form, errors=form.errors), 429

            user = db.session.scalar(
                db.select(User).where(
                    or_(func.lower(User.email) == identifier, func.lower(User.username) == identifier)
                )
            )
            
            if user is None or not user.check_password(password):
                record_failed_login(record)
                flash("Invalid credentials.", "danger")
                return render_template("auth/login.html", form=form, errors=form.errors), 401
            
            if not user.is_active or user.status != "active":
                flash("Your account must be activated before signing in.", "warning")
                return render_template("auth/login.html", form=form, errors=form.errors), 403

            if not can_sign_in_as(user, selected_role):
                flash("This account is not assigned to the selected sign-in role.", "danger")
                return render_template("auth/login.html", form=form, errors=form.errors), 403

            clear_failed_logins(record)
            login_user(user, fresh=True, remember=form.remember_me.data)
            user.last_login_at = now()
            create_session_record(user.id)
            audit_record("LOGIN", "auth", "User", user.id, f"User {user.username} logged in")
            db.session.commit()
            if user.must_change_password:
                flash("Palitan muna ang pansamantalang password bago magpatuloy.", "warning")
                return redirect(url_for("auth.change_password"))
            return redirect(selected_workspace(user, selected_role))
        else:
            # Form validation failed
            ValidationService.flash_form_errors(form)

    return render_template("auth/login.html", form=form, errors=form.errors)


@auth_bp.get("/session")
@login_required
def session_status():
    """Return remaining idle time and refresh the server-side session."""
    record = getattr(g, "current_user_session", None)
    if record is None:
        return jsonify(active=False), 401
    expires = utc_timestamp(record.expires_at)
    remaining = max(0, int((expires - utc_now()).total_seconds()))
    return jsonify(active=True, remaining_seconds=remaining, expires_at=expires.isoformat())


@auth_bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        audit_record("LOGOUT", "auth", "User", current_user.id, f"User {current_user.username} logged out")
        db.session.commit()
    revoke_current_session()
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.index"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    
    if request.method == "POST":
        if ValidationService.validate_form(form, flash_errors=False):
            if not current_user.check_password(form.current_password.data):
                form.current_password.errors.append("Old password is incorrect.")
                flash("Old password is incorrect.", "danger")
            else:
                current_user.set_password(form.new_password.data)
                current_user.must_change_password = False
                revoke_user_sessions(current_user.id, keep_current=True)
                audit_record("CHANGE_PASSWORD", "auth", "User", current_user.id, "Password changed")
                db.session.commit()
                flash("Your password has been changed.", "success")
                return redirect(post_login_url())
        else:
            ValidationService.flash_form_errors(form)
    
    password_min_length = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
    return render_template("auth/change_password.html", form=form, errors=form.errors, password_min_length=password_min_length)


@auth_bp.route("/enter-activation-code", methods=["GET", "POST"])
def enter_activation_code():
    """Handle activation code entry for newly approved residents."""
    from flask import session as flask_session
    from werkzeug.security import check_password_hash
    
    user_id = flask_session.get('pending_user_id')
    if not user_id:
        flash("Session expired. Please login again.", "warning")
        return redirect(url_for("auth.login"))
    
    user = db.get_or_404(User, user_id)
    
    if user.status != "pending_activation" or not user.activation_token_hash:
        flash("Account already activated or invalid state.", "warning")
        flask_session.pop('pending_user_id', None)
        return redirect(url_for("auth.login"))
    
    if request.method == "POST":
        activation_code = request.form.get("activation_code", "").strip()
        
        if not activation_code:
            flash("Please enter the activation code.", "danger")
            return render_template("auth/enter_activation_code.html", user=user)
        
        # Verify activation code
        if check_password_hash(user.activation_token_hash, activation_code):
            # Activate the account
            user.is_active = True
            user.status = "active"
            user.activated_at = datetime.now(timezone.utc)
            user.email_verified_at = datetime.now(timezone.utc)
            user.activation_token_hash = None
            
            # Activate resident record
            if user.resident:
                user.resident.status = "active"
                user.resident.is_verified = True
            
            audit_record("ACTIVATE_WITH_CODE", "auth", "User", user.id, 
                        f"Resident account {user.username} activated with code")
            db.session.commit()
            
            # Clear session and login
            flask_session.pop('pending_user_id', None)
            login_user(user, fresh=True)
            create_session_record(user.id)
            
            flash("Account activated successfully! Palitan muna ang password.", "success")
            return redirect(url_for("auth.change_password"))
        else:
            flash("Invalid activation code. Please check your email and try again.", "danger")
            return render_template("auth/enter_activation_code.html", user=user)
    
    return render_template("auth/enter_activation_code.html", user=user)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Issue a short-lived, single-use email OTP without exposing account existence."""
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(db.select(User).where(User.email == email, User.is_active.is_(True)))
        if user:
            otp = f"{secrets.randbelow(1_000_000):06d}"
            user.reset_token_hash = generate_password_hash(otp)
            user.reset_expires_at = now() + timedelta(minutes=current_app.config["PASSWORD_RESET_TOKEN_MINUTES"])
            session["password_reset_user_id"] = user.id
            session.pop("password_reset_attempts", None)
            db.session.commit()
            try:
                send_password_reset_otp(
                    recipient=user.email,
                    full_name=_full_name(user),
                    otp=otp,
                    valid_minutes=current_app.config["PASSWORD_RESET_TOKEN_MINUTES"],
                )
                audit_record("PASSWORD_RESET_OTP_SENT", "auth", "User", user.id, "Password recovery OTP sent")
                db.session.commit()
            except Exception:
                current_app.logger.exception("Password reset OTP delivery failed for user id %s", user.id)
        flash(
            "If an active account matches that email, a 6-digit code will be sent. "
            "Check your Inbox and Spam/Junk folder. If no code arrives, contact the barangay office.",
            "info",
        )
        return redirect(url_for("auth.reset_password"))
    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Step 1 — verify the 6-digit OTP. On success, mark session and redirect to new-password."""
    user_id = session.get("password_reset_user_id")
    user = db.session.get(User, user_id) if user_id else None
    if user is None or not user.is_active or not user.reset_token_hash or is_expired(user.reset_expires_at):
        session.pop("password_reset_user_id", None)
        session.pop("password_reset_otp_verified", None)
        flash("Your password recovery code is invalid or expired. Request a new code.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = VerifyOtpForm()
    if form.validate_on_submit():
        reset_attempt = attempt_record(f"password-reset:{user.id}")
        if locked(reset_attempt):
            flash("Too many incorrect codes. Please wait before trying again.", "danger")
        elif not check_password_hash(user.reset_token_hash, form.otp.data):
            record_failed_login(reset_attempt)
            flash("The one-time code is incorrect. Please check your email and try again.", "danger")
        else:
            clear_failed_logins(reset_attempt)
            # Mark OTP as verified — gate the new-password page behind this flag
            session["password_reset_otp_verified"] = True
            audit_record("PASSWORD_RESET_OTP_VERIFIED", "auth", "User", user.id,
                         "Password reset OTP verified; proceeding to new password step")
            db.session.commit()
            return redirect(url_for("auth.new_password"))
    return render_template(
        "auth/reset_password.html",
        form=form,
        reset_valid_minutes=current_app.config["PASSWORD_RESET_TOKEN_MINUTES"],
        reset_email=user.email,
    )


@auth_bp.route("/new-password", methods=["GET", "POST"])
def new_password():
    """Step 2 — set the new password, only reachable after OTP is verified."""
    user_id = session.get("password_reset_user_id")
    otp_verified = session.get("password_reset_otp_verified", False)
    user = db.session.get(User, user_id) if user_id else None

    if not otp_verified or user is None or not user.is_active or is_expired(user.reset_expires_at):
        session.pop("password_reset_user_id", None)
        session.pop("password_reset_otp_verified", None)
        flash("Please verify your one-time code first.", "warning")
        return redirect(url_for("auth.forgot_password"))

    form = NewPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.must_change_password = False
        user.reset_token_hash = None
        user.reset_expires_at = None
        revoke_user_sessions(user.id)
        audit_record("PASSWORD_RESET_WITH_OTP", "auth", "User", user.id,
                     "Password reset after email OTP verification")
        db.session.commit()
        session.pop("password_reset_user_id", None)
        session.pop("password_reset_otp_verified", None)
        flash("Your password has been reset. You may now sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/new_password.html",
        form=form,
        password_min_length=current_app.config["PASSWORD_MIN_LENGTH"],
    )


@auth_bp.route("/reset-password/<token>")
def legacy_reset_password(token: str):
    """Gracefully retire old link-based recovery URLs without accepting them."""
    flash("Password reset now uses a one-time code sent to your email.", "info")
    return redirect(url_for("auth.forgot_password"))


@auth_bp.route("/terms-and-conditions")
def terms_and_conditions():
    """Display Terms and Conditions page."""
    return render_template("auth/terms_and_conditions.html")


# ---------------------------------------------------------------------------
# GitHub OAuth
# ---------------------------------------------------------------------------

@auth_bp.get("/login/github")
def github_login():
    """Redirect to GitHub for OAuth authorisation."""
    from app.extensions import oauth
    selected_role = request.args.get("role", "")
    if selected_role not in LOGIN_ROLES:
        flash("Select a valid sign-in role.", "warning")
        return redirect(url_for("auth.login"))
    state = secrets.token_urlsafe(32)
    session["github_login_role"] = {"state": state, "role": selected_role}
    redirect_uri = url_for("auth.github_callback", _external=True)
    return oauth.github.authorize_redirect(redirect_uri, state=state)


@auth_bp.get("/login/github/callback")
def github_callback():
    """Handle GitHub OAuth callback — link or log in the matching resident account."""
    from app.extensions import oauth
    flow = session.pop("github_login_role", {})
    selected_role = flow.get("role")
    if selected_role not in LOGIN_ROLES or flow.get("state") != request.args.get("state"):
        flash("GitHub sign-in expired. Select your role and try again.", "warning")
        return redirect(url_for("auth.login"))
    try:
        token = oauth.github.authorize_access_token()
    except Exception:
        current_app.logger.exception("GitHub OAuth token exchange failed")
        flash("GitHub login failed. Please try again.", "danger")
        return redirect(url_for("auth.login"))

    # Fetch the authenticated GitHub user profile.
    resp = oauth.github.get("user", token=token)
    github_profile = resp.json()
    github_id = str(github_profile.get("id", ""))
    if not github_id.isdigit():
        flash("GitHub sign-in did not return a valid account.", "danger")
        return redirect(url_for("auth.login", role=selected_role))

    # Fetch the primary verified email if the profile email is hidden.
    email = github_profile.get("email")
    if not email:
        emails_resp = oauth.github.get("user/emails", token=token)
        for entry in emails_resp.json():
            if entry.get("primary") and entry.get("verified"):
                email = entry["email"]
                break

    if not email:
        flash("Your GitHub account does not have a verified public email. Please add one and try again.", "warning")
        return redirect(url_for("auth.login"))

    email = email.strip().lower()

    # --- Link by GitHub ID first (fastest and most stable path) ---
    user = db.session.scalar(db.select(User).where(User.github_id == github_id))

    # --- Fall back to email match for first-time GitHub login ---
    if user is None:
        user = db.session.scalar(
            db.select(User).where(
                db.func.lower(User.email) == email,
                User.github_id.is_(None),
                User.is_active.is_(True),
                User.status == "active",
            )
        )

    if user is None:
        flash(
            "No active account was found for the GitHub email address. "
            "Please register first or contact the barangay office.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    if not user.is_active or user.status != "active":
        flash("Your account is not yet active. Please wait for barangay approval.", "warning")
        return redirect(url_for("auth.login"))

    if not can_sign_in_as(user, selected_role):
        flash("This account is not assigned to the selected sign-in role.", "danger")
        return redirect(url_for("auth.login", role=selected_role))

    if not user.github_id:
        user.github_id = github_id
        audit_record("GITHUB_ACCOUNT_LINKED", "auth", "User", user.id,
                     f"GitHub account {github_profile.get('login')} linked to user")
    login_user(user, fresh=True)
    user.last_login_at = now()
    create_session_record(user.id)
    audit_record("LOGIN_GITHUB", "auth", "User", user.id,
                 f"User {user.username} signed in via GitHub OAuth")
    db.session.commit()
    if user.must_change_password:
        flash("Palitan muna ang pansamantalang password bago magpatuloy.", "warning")
        return redirect(url_for("auth.change_password"))
    return redirect(selected_workspace(user, selected_role))
