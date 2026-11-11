"""Server-side session lifecycle helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, flash, g, jsonify, redirect, request, session, url_for
from flask_login import current_user, logout_user

from app.extensions import db
from app.models import UserSession


PUBLIC_ENDPOINTS = {
    "static",
    "main.index",
    "main.health_check",
    "main.privacy_notice",
    "main.help_page",
    "main.verify",
    "main.verify_document",
    "auth.login",
    "auth.register",
    "auth.activate",
    "auth.forgot_password",
    "auth.reset_password",
}

PROTECTED_BLUEPRINTS = {"admin", "official", "resident", "messaging", "geocoding", "workspace"}
PROTECTED_ENDPOINTS = {"auth.change_password", "auth.session_status", "main.search"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_timestamp(value: datetime) -> datetime:
    """Return a database timestamp as timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_session_record(user_id: int) -> None:
    """Create a revocable server-side session record."""
    token = secrets.token_urlsafe(48)
    expires_at = utc_now() + current_app.config["PERMANENT_SESSION_LIFETIME"]
    db.session.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            ip_address=request.remote_addr,
            user_agent=(request.user_agent.string or "")[:500],
            expires_at=expires_at,
        )
    )
    session["session_token"] = token
    session.permanent = True


def post_login_url() -> str:
    """Send an authenticated user to their role workspace instead of the public portal."""
    if not current_user.is_authenticated:
        return url_for("main.index")
    
    role_names = {role.name for role in current_user.roles}
    
    if "System Administrator" in role_names:
        return url_for("admin.dashboard")
    
    if "Barangay Official" in role_names:
        return url_for("official.dashboard")
    
    if "Resident" in role_names:
        # Check if user has a proper resident profile
        if hasattr(current_user, 'resident') and current_user.resident is not None:
            return url_for("resident.dashboard")
        else:
            # User has Resident role but no resident profile - stay on main page
            return url_for("main.index")
    
    return url_for("main.index")


def revoke_current_session() -> None:
    token = session.pop("session_token", None)
    if token:
        record = db.session.scalar(
            db.select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        if record and record.revoked_at is None:
            record.revoked_at = utc_now()
            db.session.commit()


def revoke_user_sessions(user_id: int, *, keep_current: bool = False) -> None:
    """Revoke every active server-side session for a user."""
    keep_hash = None
    if keep_current:
        token = session.get("session_token")
        if token:
            keep_hash = hash_token(token)
    now = utc_now()
    records = db.session.scalars(
        db.select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    )
    for record in records:
        if keep_hash and record.token_hash == keep_hash:
            continue
        record.revoked_at = now


def load_session_record() -> UserSession | None:
    token = session.get("session_token")
    if not token:
        return None
    return db.session.scalar(db.select(UserSession).where(UserSession.token_hash == hash_token(token)))


def validate_current_session() -> None:
    """Log out sessions missing, expired, or revoked server-side records."""
    if not current_user.is_authenticated:
        return

    record = load_session_record()
    now = utc_now()
    if record is None or record.revoked_at is not None or utc_timestamp(record.expires_at) <= now:
        if record and record.revoked_at is None:
            record.revoked_at = now
            db.session.commit()
        logout_user()
        session.pop("session_token", None)
        flash("Your session has expired. Please sign in again. / Nag-expire na ang session. Mag-sign in ulit.", "info")
        return
    if record.user_id != current_user.id:
        logout_user()
        session.pop("session_token", None)
        return
    g.current_user_session = record


def touch_current_session() -> UserSession | None:
    """Slide idle timeout on every authenticated request."""
    record = getattr(g, "current_user_session", None) or load_session_record()
    if record is None:
        return None

    lifetime = current_app.config["PERMANENT_SESSION_LIFETIME"]
    now = utc_now()
    new_expiry = now + lifetime
    remaining = utc_timestamp(record.expires_at) - now
    record.expires_at = new_expiry
    record.ip_address = request.remote_addr or record.ip_address
    if request.user_agent and request.user_agent.string:
        record.user_agent = request.user_agent.string[:500]
    session.permanent = True
    g.current_user_session = record
    if remaining < lifetime - timedelta(seconds=30):
        db.session.commit()
    return record


def session_payload() -> dict:
    record = getattr(g, "current_user_session", None)
    if record is None and current_user.is_authenticated:
        record = load_session_record()
    if record is None:
        return {
            "session_timeout_minutes": int(current_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() // 60),
            "session_expires_at": None,
            "session_remaining_seconds": 0,
        }
    expires = utc_timestamp(record.expires_at)
    remaining = max(0, int((expires - utc_now()).total_seconds()))
    return {
        "session_timeout_minutes": int(current_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() // 60),
        "session_expires_at": expires.isoformat(),
        "session_remaining_seconds": remaining,
    }


def wants_json() -> bool:
    if request.endpoint == "auth.session_status":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def enforce_request_session():
    """Validate, extend, and require a session on every protected page."""
    if request.endpoint in {None, "static"} or request.path.startswith("/static/"):
        return None

    validate_current_session()

    if current_user.is_authenticated:
        if not current_user.is_active or current_user.status != "active":
            logout_user()
            session.pop("session_token", None)
            flash("This account is no longer active.", "warning")
        else:
            touch_current_session()

    endpoint = request.endpoint or ""
    needs_auth = endpoint not in PUBLIC_ENDPOINTS and (
        request.blueprint in PROTECTED_BLUEPRINTS or endpoint in PROTECTED_ENDPOINTS
    )
    if not needs_auth or current_user.is_authenticated:
        return None
    if wants_json():
        return jsonify(active=False, error="session_required"), 401
    return redirect(url_for("auth.login", next=request.url))
