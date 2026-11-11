"""Application configuration classes."""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _project_path(value):
    path=Path(value)
    return str(path if path.is_absolute() else BASE_DIR/path)


def _database_uri() -> str:
    """Return configured PostgreSQL URI, or a local SQLite URI for development/tests."""
    configured_uri = os.getenv("DATABASE_URL")
    if not configured_uri:
        local_db = BASE_DIR / "instance" / "development.sqlite3"
        return f"sqlite:///{local_db.as_posix()}"
    
    # Use psycopg 3, the PostgreSQL driver declared in requirements.txt.
    if configured_uri.startswith("postgres://"):
        configured_uri = configured_uri.replace("postgres://", "postgresql+psycopg://", 1)
    elif configured_uri.startswith("postgresql://"):
        configured_uri = configured_uri.replace("postgresql://", "postgresql+psycopg://", 1)
    
    return configured_uri


class BaseConfig:
    """Shared configuration values."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-development-secret-key")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Flask-Login configuration.
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "barangay_session"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", "30")))
    SESSION_REFRESH_EACH_REQUEST = True
    SESSION_PROTECTION = "basic"
    WTF_CSRF_TIME_LIMIT = int(os.getenv("CSRF_TIME_LIMIT_SECONDS", "3600"))
    LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    ACTIVATION_TOKEN_HOURS = int(os.getenv("ACTIVATION_TOKEN_HOURS", "24"))
    PASSWORD_RESET_TOKEN_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", "5"))
    PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "12"))
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "").strip()
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Barangay Sta. Clara Norte e-Governance")
    SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "1") == "1"
    SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "0") == "1"
    SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "15"))
    EMAIL_VERIFICATION_TOKEN_HOURS = int(os.getenv("EMAIL_VERIFICATION_TOKEN_HOURS", "24"))
    EMAIL_VERIFICATION_RESEND_SECONDS = int(os.getenv("EMAIL_VERIFICATION_RESEND_SECONDS", "60"))
    # Require ownership verification before staff approval can activate a resident account.
    # Set REQUIRE_EMAIL_VERIFICATION_FOR_APPROVAL=0 only for a deliberate legacy migration.
    REQUIRE_EMAIL_VERIFICATION_FOR_APPROVAL = os.getenv("REQUIRE_EMAIL_VERIFICATION_FOR_APPROVAL", "1") == "1"
    # Public origin used in emailed links, e.g. https://sta-clara-norte.example.gov.ph (blank = use the request host).
    APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_REQUEST_BYTES", str(16 * 1024 * 1024)))
    REGISTRATION_REQUIRE_COMPLETE_PROFILE = True
    PROFILE_PHOTO_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    MAX_IMAGE_BYTES = 5 * 1024 * 1024
    SYSTEM_TIMEZONE = os.getenv("SYSTEM_TIMEZONE", "Asia/Manila")
    ATTENDANCE_RETENTION_DAYS = max(1, int(os.getenv('ATTENDANCE_RETENTION_DAYS', '2555')))
    INCIDENT_RETENTION_DAYS = max(1, int(os.getenv('INCIDENT_RETENTION_DAYS', '2555')))
    ATTENDANCE_OFFLINE_WINDOW_DAYS = min(30,max(1,int(os.getenv('ATTENDANCE_OFFLINE_WINDOW_DAYS', '7'))))
    ATTENDANCE_DEV_MODE = os.getenv('ATTENDANCE_DEV_MODE', 'false').lower() == 'true'
    ATTENDANCE_LOCAL_TEST_MODE = os.getenv('ATTENDANCE_LOCAL_TEST_MODE', 'false').lower() == 'true'
    ATTENDANCE_LOCAL_TEST_ALLOWED = False
    BARANGAY_NAME = os.getenv("BARANGAY_NAME", "Barangay Sta. Clara Norte")
    CHATBOT_NAME = os.getenv("CHATBOT_NAME", "").strip()
    STORAGE_ROOT = _project_path(os.getenv("STORAGE_ROOT", str(BASE_DIR / "instance")))
    LOG_FILE = _project_path(os.getenv("LOG_FILE", str(BASE_DIR / "instance" / "logs" / "barangay_records.log")))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    DOCUMENT_AUTHORIZED_SIGNATORY = os.getenv("DOCUMENT_AUTHORIZED_SIGNATORY", "Punong Barangay")
    DOCUMENT_VERIFICATION_BASE_URL = os.getenv("DOCUMENT_VERIFICATION_BASE_URL", "")
    DOCUMENT_PDF_RENDERER = os.getenv("DOCUMENT_PDF_RENDERER", "")
    DOCUMENT_PDF_BROWSER = os.getenv("DOCUMENT_PDF_BROWSER", "")
    BARANGAY_CONTACT_PHONE = os.getenv("BARANGAY_CONTACT_PHONE", "")
    BARANGAY_CONTACT_EMAIL = os.getenv("BARANGAY_CONTACT_EMAIL", "")
    BARANGAY_HALL_ADDRESS = os.getenv("BARANGAY_HALL_ADDRESS", "")
    BARANGAY_OFFICE_HOURS = os.getenv("BARANGAY_OFFICE_HOURS", "")
    DPO_NAME = os.getenv("DPO_NAME", "")
    DPO_EMAIL = os.getenv("DPO_EMAIL", "")
    DPO_PHONE = os.getenv("DPO_PHONE", "")
    # OpenStreetMap Nominatim User-Agent for geocoding requests.
    NOMINATIM_USER_AGENT = os.getenv("NOMINATIM_USER_AGENT", "BarangayManagementSystem").strip()
    PRIVACY_NOTICE_VERSION = "2026-09-18"
    MESSAGING_AUTO_REPLY_DELAY_SECONDS = int(os.getenv("MESSAGING_AUTO_REPLY_DELAY_SECONDS", "120"))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")).strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    GEMINI_API_TIMEOUT_SECONDS = int(os.getenv("GEMINI_API_TIMEOUT_SECONDS", "12"))

    # GitHub OAuth login
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "").strip()
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "").strip()


class DevelopmentConfig(BaseConfig):
    ATTENDANCE_LOCAL_TEST_ALLOWED = True
    ALLOW_DEVELOPMENT_SEED = True
    """Configuration used for local development."""

    DEBUG = False


class TestingConfig(BaseConfig):
    ATTENDANCE_LOCAL_TEST_ALLOWED = True
    ATTENDANCE_LOCAL_TEST_MODE = False
    """Configuration used by automated tests."""

    REGISTRATION_REQUIRE_COMPLETE_PROFILE = False  # Existing legacy fixture compatibility; new profile tests enable it.
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    """Configuration used in deployed environments."""

    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    @classmethod
    def validate(cls):
        """Fail closed when required production secrets or database settings are missing."""
        if cls.ATTENDANCE_LOCAL_TEST_MODE:
            raise RuntimeError('ATTENDANCE_LOCAL_TEST_MODE must be disabled in production.')
        if not os.getenv("SECRET_KEY") or len(cls.SECRET_KEY) < 32 or cls.SECRET_KEY in {"change-this-development-secret-key", "replace-with-a-long-random-secret"}:
            raise RuntimeError("SECRET_KEY must be a unique random value of at least 32 characters in production.")
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL must point to MySQL or PostgreSQL in production.")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
