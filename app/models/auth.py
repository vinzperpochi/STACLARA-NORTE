"""Authentication, authorization, notification, and audit models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Table, Column, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import StatusMixin, TimestampedModel

if TYPE_CHECKING:
    from .governance import Announcement


user_roles = Table(
    "user_roles",
    TimestampedModel.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    TimestampedModel.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class User(UserMixin, StatusMixin, TimestampedModel):
    """System account; resident identity is stored separately."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("resident_id", name="uq_users_resident_id"),
        UniqueConstraint("official_id", name="uq_users_official_id"),
        UniqueConstraint("activation_token_hash", name="uq_users_activation_token_hash"),
        UniqueConstraint("reset_token_hash", name="uq_users_reset_token_hash"),
        UniqueConstraint("github_id", name="uq_users_github_id"),
        Index("ix_users_status_email", "status", "email"),
    )

    profile_photo_filename: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resident_id: Mapped[int | None] = mapped_column(
        ForeignKey("residents.id", name="fk_users_resident", ondelete="SET NULL")
    )
    official_id: Mapped[int | None] = mapped_column(
        ForeignKey("officials.id", name="fk_users_official", ondelete="SET NULL")
    )
    activation_token_hash: Mapped[str | None] = mapped_column(String(255))
    activation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reset_token_hash: Mapped[str | None] = mapped_column(String(255))
    reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    github_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    privacy_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_consent_version: Mapped[str | None] = mapped_column(String(30))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, back_populates="users")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="user")
    notifications: Mapped[list[Notification]] = relationship(back_populates="user")
    resident: Mapped["Resident | None"] = relationship(back_populates="user", foreign_keys=[resident_id])
    official: Mapped["Official | None"] = relationship(
        back_populates="user",
        foreign_keys=[official_id],
        uselist=False,
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Role(StatusMixin, TimestampedModel):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", name="uq_roles_name"),)

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")
    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, back_populates="roles")


class Permission(TimestampedModel):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("resource", "action", name="uq_permissions_resource_action"),)

    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")


class AuditLog(TimestampedModel):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    role: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    module: Mapped[str | None] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000))
    details: Mapped[str | None] = mapped_column(String(2000))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user: Mapped[User | None] = relationship(back_populates="audit_logs")


class Notification(StatusMixin, TimestampedModel):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)
    user: Mapped[User] = relationship(back_populates="notifications")


class LoginAttempt(TimestampedModel):
    """Sliding-window failed-login counter used to slow credential attacks."""

    __tablename__ = "login_attempts"
    __table_args__ = (
        UniqueConstraint("identifier", "ip_address", name="uq_login_attempts_identifier_ip"),
        Index("ix_login_attempts_locked_until", "locked_until"),
    )

    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(TimestampedModel):
    """Server-side record for revocable authenticated browser sessions."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_active", "user_id", "revoked_at", "expires_at"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()
