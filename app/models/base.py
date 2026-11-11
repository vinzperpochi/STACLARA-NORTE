"""Shared SQLAlchemy model primitives."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class BaseModelMixin:
    """Common primary key and audit timestamp columns."""

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


Base = db.Model


class TimestampedModel(BaseModelMixin, Base):
    """Abstract base for normalized application entities."""

    __abstract__ = True


class StatusMixin:
    """Reusable status field for operational entities."""

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
