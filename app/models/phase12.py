"""Phase 12 request queue and Phase 13 fee collection ledger."""
from __future__ import annotations
from datetime import date, time, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import StatusMixin, TimestampedModel

class QueueRequest(StatusMixin, TimestampedModel):
    __tablename__ = "queue_requests"
    __table_args__ = (Index("ix_queue_requests_status_date", "status", "appointment_date"), Index("ix_queue_requests_resident", "resident_id"))
    queue_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    request_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    appointment_date: Mapped[date | None] = mapped_column(Date)
    appointment_time: Mapped[time | None] = mapped_column(Time)
    assigned_official_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    remarks: Mapped[str | None] = mapped_column(Text)
    resident = relationship("Resident")
    assigned_official = relationship("User")

class CollectionEntry(TimestampedModel):
    __tablename__ = "collection_entries"
    __table_args__ = (UniqueConstraint("transaction_number", name="uq_collection_entries_transaction"), Index("ix_collection_entries_date_service", "transaction_date", "service"))
    transaction_number: Mapped[str] = mapped_column(String(50), nullable=False)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    service: Mapped[str] = mapped_column(String(150), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    receiving_official_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reference_number: Mapped[str | None] = mapped_column(String(100))
    resident = relationship("Resident")
    receiving_official = relationship("User")
