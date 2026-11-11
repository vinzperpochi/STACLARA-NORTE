"""System-wide settings and fee configuration models."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import StatusMixin, TimestampedModel


class FeeConfiguration(StatusMixin, TimestampedModel):
    """Effective fee for a document type, retained as an auditable record."""

    __tablename__ = "fee_configurations"
    __table_args__ = (
        Index("ix_fee_configurations_document_effective", "document_type_id", "effective_from"),
    )

    document_type_id: Mapped[int] = mapped_column(
        ForeignKey("document_types.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped["DocumentType"] = relationship()


class SystemSetting(TimestampedModel):
    """Typed-as-text key/value setting controlled by administrators."""

    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("setting_key", name="uq_system_settings_key"),)

    setting_key: Mapped[str] = mapped_column(String(100), nullable=False)
    setting_value: Mapped[str] = mapped_column(String(2000), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_secret: Mapped[bool] = mapped_column(nullable=False, default=False)
