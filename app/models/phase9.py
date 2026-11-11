"""Phase 9 business clearance and health/social welfare records."""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import StatusMixin, TimestampedModel

class BusinessRecord(StatusMixin, TimestampedModel):
    __tablename__ = "business_records"
    __table_args__ = (Index("ix_business_records_status_expiration", "status", "expiration_date"),)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    business_address: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[str] = mapped_column(String(150), nullable=False)
    registration_date: Mapped[date] = mapped_column(Date, nullable=False)
    permit_number: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    owner = relationship("Resident")
    requests = relationship("BusinessClearanceRequest", back_populates="business", cascade="all, delete-orphan")

class BusinessClearanceRequest(StatusMixin, TimestampedModel):
    __tablename__ = "business_clearance_requests"
    __table_args__ = (Index("ix_business_clearance_requests_status_created", "status", "created_at"),)
    request_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("business_records.id", ondelete="CASCADE"), nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business = relationship("BusinessRecord", back_populates="requests")
    requester = relationship("Resident")
    reviewed_by = relationship("User")

class BeneficiaryRegistry(StatusMixin, TimestampedModel):
    __tablename__ = "beneficiary_registry"
    __table_args__ = (Index("ix_beneficiary_registry_category_status", "category", "status"),)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    application_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    registered_date: Mapped[date] = mapped_column(Date, nullable=False)
    application_notes: Mapped[str | None] = mapped_column(Text)
    resident = relationship("Resident")
    assistance_records = relationship("AssistanceRecord", back_populates="beneficiary", cascade="all, delete-orphan")

class AssistanceRecord(TimestampedModel):
    __tablename__ = "assistance_records"
    __table_args__ = (Index("ix_assistance_records_date", "assistance_date"),)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiary_registry.id", ondelete="CASCADE"), nullable=False)
    assistance_type: Mapped[str] = mapped_column(String(120), nullable=False)
    assistance_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text)
    distribution_officer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    remarks: Mapped[str | None] = mapped_column(Text)
    beneficiary = relationship("BeneficiaryRegistry", back_populates="assistance_records")
    distribution_officer = relationship("User")
