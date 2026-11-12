"""Application factory for the Barangay Records Management System."""

import importlib
import sys
import os
import logging
import logging.config
from pathlib import Path
bundled_python = Path(__file__).resolve().parents[1] / 'vendor' / 'python'
if bundled_python.is_dir():
    sys.path.insert(0, str(bundled_python))
from logging.handlers import RotatingFileHandler
from datetime import date, datetime, timezone

from flask import Flask, jsonify, render_template, request
from flask_login import current_user

import config as app_config

from .extensions import csrf, db, login_manager, migrate


def create_app(config_name: str | None = None, *, vercel: bool = False) -> Flask:
    """Create and configure a Flask application instance."""
    importlib.reload(app_config)
    config_by_name = app_config.config_by_name
    selected_config = config_name or os.getenv("FLASK_CONFIG", "development")
    config_class = config_by_name.get(selected_config, config_by_name["development"])
    if selected_config == "production":
        config_class.validate()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    if vercel:
        app_config.configure_vercel_database(app.config)
    storage_root = Path(app.config["STORAGE_ROOT"])
    storage_root.mkdir(parents=True, exist_ok=True)
    for directory in ("profile_photos", "document_requirements", "generated_documents", "registration_documents", "backups", "logs"):
        (storage_root / directory).mkdir(parents=True, exist_ok=True)
    configure_logging(app)

    register_extensions(app)
    register_models()
    register_blueprints(app)
    register_template_helpers(app)
    from .attendance.service import utc, MANILA
    app.jinja_env.filters['datetime_manila'] = lambda value: utc(value).astimezone(MANILA).strftime('%b %d, %Y, %I:%M %p') if value else ''
    app.jinja_env.filters['datetime_local'] = lambda value: utc(value).astimezone(MANILA).strftime('%Y-%m-%dT%H:%M') if value else ''
    app.jinja_env.filters['datetime_utc_iso'] = lambda value: utc(value).isoformat() if value else ''
    app.jinja_env.filters['time_manila'] = lambda value: utc(value).astimezone(MANILA).strftime('%I:%M %p') if value else ''
    app.jinja_env.filters['date_manila'] = lambda value: utc(value).astimezone(MANILA).strftime('%b %d') if value else ''
    from .operations_retention import register_retention_command
    register_retention_command(app)
    register_session_hooks(app)
    register_error_handlers(app)

    return app


def configure_logging(app: Flask) -> None:
    """Configure console and rotating file logs without embedding secrets."""
    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO"), logging.INFO)
    app.logger.setLevel(level)
    if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
        file_handler = RotatingFileHandler(app.config["LOG_FILE"], maxBytes=10 * 1024 * 1024, backupCount=5)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        file_handler.setLevel(level)
        app.logger.addHandler(file_handler)


def register_extensions(app: Flask) -> None:
    """Initialize Flask extensions with the application."""
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    from .extensions import oauth
    oauth.init_app(app)
    oauth.register(
        name="github",
        client_id=app.config.get("GITHUB_CLIENT_ID", ""),
        client_secret=app.config.get("GITHUB_CLIENT_SECRET", ""),
        access_token_url="https://github.com/login/oauth/access_token",
        access_token_params=None,
        authorize_url="https://github.com/login/oauth/authorize",
        authorize_params=None,
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )


def register_models() -> None:
    """Import all model classes so SQLAlchemy metadata is complete."""
    from . import models  # noqa: F401
    from . import model_validation, audit  # register persistence validators and transaction-local audit


@login_manager.user_loader
def load_user(user_id: str):
    """Load an active user for Flask-Login sessions."""
    from .models import User

    try:
        identity = int(user_id)
    except (TypeError, ValueError):
        return None
    user = db.session.get(User, identity)
    if user is None or not user.is_active or user.status != "active":
        return None
    return user


def register_blueprints(app: Flask) -> None:
    """Register application blueprints."""
    from .admin import admin_bp
    from .auth import auth_bp
    from .official import official_bp
    from .resident import resident_bp
    from .main import main_bp
    from .messaging import messaging_bp
    from .geocoding import geocoding_bp
    from .documents import routes as document_routes  # register original-template output routes

    from .workspace import workspace_bp
    from .attendance import attendance_bp
    from .incidents import incidents_bp
    app.register_blueprint(attendance_bp)
    app.register_blueprint(incidents_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(official_bp)
    app.register_blueprint(resident_bp)
    app.register_blueprint(messaging_bp)
    app.register_blueprint(geocoding_bp)


def register_session_hooks(app: Flask) -> None:
    """Validate and require server-side sessions on every protected request."""
    from .auth.session import enforce_request_session

    @app.before_request
    def validate_session():
        return enforce_request_session()

    @app.before_request
    def require_initial_password_change():
        if request.endpoint == "static":
            return None
        if (
            current_user.is_authenticated
            and current_user.must_change_password
            and request.endpoint not in {"auth.change_password", "auth.logout", "static"}
        ):
            from flask import redirect, url_for
            return redirect(url_for("auth.change_password"))

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "img-src 'self' data: https://*.tile.openstreetmap.org https://avatars.githubusercontent.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://unpkg.com; "
            "connect-src 'self'; " +
            ("frame-ancestors 'self'; " if request.endpoint in {'official.document_certificate', 'official.document_application'} else "frame-ancestors 'none'; ") + "base-uri 'self'; form-action 'self'",
        )
        if request.endpoint != "static" and (current_user.is_authenticated or request.path.startswith("/verify/") or request.path.startswith("/admin/")):
            response.headers["Cache-Control"] = "no-store"
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


def register_template_helpers(app: Flask) -> None:
    """Workspace chrome data available to every template."""
    from .pagination import pagination_url
    app.jinja_env.globals["pagination_url"] = pagination_url
    from sqlalchemy import func, or_
    import xml.etree.ElementTree as ET
    symbols = ET.parse(Path(app.static_folder) / "img" / "icons.svg")
    from app.registration import EDUCATION, RELATIONSHIPS, DURATIONS, CATEGORIES
    app.jinja_env.globals['registration_labels'] = dict(EDUCATION + RELATIONSHIPS + DURATIONS + CATEGORIES)
    from .forms.common import client_validation_schema
    app.jinja_env.globals['client_validation_schema'] = client_validation_schema
    from .site_information import public_information, site_info_value
    app.jinja_env.globals['site_info_value'] = site_info_value
    app.jinja_env.globals["svg_symbols"] = {element.attrib["id"] for element in symbols.iter() if "id" in element.attrib}

    @app.context_processor
    def inject_workspace():
        today = date.today()
        try:
            birth_date_max = today.replace(year=today.year - 10)
        except ValueError:
            birth_date_max = today.replace(year=today.year - 10, day=28)
        unread = 0
        role_names: set[str] = set()
        ticker_alert = None
        if current_user.is_authenticated:
            role_names = {role.name for role in current_user.roles}
            from .models import Notification

            unread = (
                db.session.scalar(
                    db.select(func.count()).select_from(Notification).where(
                        Notification.user_id == current_user.id,
                        Notification.is_read.is_(False),
                    )
                )
                or 0
            )
            if request.blueprint == "resident":
                from .models import EmergencyAlert

                try:
                    ticker_alert = db.session.scalar(
                        db.select(EmergencyAlert)
                        .where(
                            func.upper(EmergencyAlert.status) == "PUBLISHED",
                            or_(
                                EmergencyAlert.expires_at.is_(None),
                                EmergencyAlert.expires_at > datetime.now(timezone.utc),
                            ),
                        )
                        .order_by(EmergencyAlert.issued_at.desc())
                        .limit(1)
                    )
                except Exception:
                    db.session.rollback()
        from .auth.session import session_payload

        payload = session_payload() if current_user.is_authenticated else {
            "session_timeout_minutes": int(app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() // 60),
            "session_expires_at": None,
            "session_remaining_seconds": 0,
        }
        from .profile_management import profile_context
        profile_data = profile_context(current_user) if current_user.is_authenticated else {}
        from .permissions import can
        return {
            'barangay_info':public_information(),
            'dpo_name':site_info_value('dpo_name'),
            'dpo_email':site_info_value('dpo_email'),
            'dpo_phone':site_info_value('dpo_phone'),
            'hotline':site_info_value('contact_phone'),
            "can": can,
            **profile_data,
            "unread_notifications": unread,
            "chatbot_name": app.config.get("CHATBOT_NAME") or app.config["BARANGAY_NAME"] + " Assistant",
            "system_timezone": app.config["SYSTEM_TIMEZONE"],
            "ticker_alert": ticker_alert,
            "is_admin": "System Administrator" in role_names,
            # Keep the Super Admin and official workspaces separate.
            "is_official": "Barangay Official" in role_names and "System Administrator" not in role_names,
            "is_resident": "Resident" in role_names,
            "password_min_length": app.config.get("PASSWORD_MIN_LENGTH", 12),
            "birth_date_max": birth_date_max.isoformat(),
            "max_upload_bytes": app.config.get("MAX_CONTENT_LENGTH", 5 * 1024 * 1024),
            **payload,
        }


def register_error_handlers(app: Flask) -> None:
    """Register consistent HTML and JSON-friendly error responses."""

    def _wants_json() -> bool:
        """Return True only when the client explicitly prefers JSON over HTML."""
        best = request.accept_mimetypes.best_match(
            ["application/json", "text/html"], default="text/html"
        )
        return best == "application/json"

    @app.errorhandler(404)
    def not_found(error):
        if _wants_json():
            return jsonify(success=False, error="Not Found", message="The requested resource was not found."), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        app.logger.exception("Unhandled application error", exc_info=error)
        db.session.rollback()
        if _wants_json():
            return jsonify(success=False, error="Internal Server Error", message="An unexpected error occurred."), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(403)
    def forbidden(error):
        if _wants_json():
            return jsonify(success=False, error="Forbidden", message="You are not authorized to access this resource."), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(ValueError)
    def invalid_value(error):
        db.session.rollback()
        if _wants_json():
            return jsonify(success=False, message="Invalid information. Check required fields, dates and numbers."), 400
        return render_template("errors/request.html", title="Invalid information", message="Check required fields, dates and numbers, then return to the form and try again."), 400

    from sqlalchemy.exc import IntegrityError
    @app.errorhandler(IntegrityError)
    def invalid_reference(error):
        db.session.rollback()
        if _wants_json():
            return jsonify(success=False, message="This record already exists or a linked record is invalid."), 409
        return render_template("errors/request.html", title="Record conflict", message="This record already exists or a linked record is invalid. Return to the form and check your entries."), 409

    @app.errorhandler(400)
    def bad_request(error):
        if _wants_json():
            return jsonify(success=False, message="Invalid request. Refresh the page and try again."), 400
        return render_template("errors/request.html", title="Invalid request", message="Refresh the page and try again. Your session or form token may have expired."), 400

    @app.errorhandler(413)
    def upload_too_large(error):
        if _wants_json():
            return jsonify(success=False, message="Upload is too large. Use a JPEG or PNG image up to 5 MB."), 413
        return render_template("errors/request.html", title="Upload too large", message="Use a JPEG or PNG image up to 5 MB."), 413

