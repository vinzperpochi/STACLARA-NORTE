"""Resident-facing service, document, permit, payment, and document-workflow models."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import StatusMixin, TimestampedModel


class DocumentType(StatusMixin, TimestampedModel):
    __tablename__ = "document_types"
    __table_args__ = (UniqueConstraint("code", name="uq_document_types_code"),)

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_fee: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    validity_days: Mapped[int | None] = mapped_column(nullable=True)
    template_code: Mapped[str | None] = mapped_column(String(10))
    issued_documents: Mapped[list[IssuedDocument]] = relationship(back_populates="document_type")
    requests: Mapped[list[Request]] = relationship(back_populates="document_type")


class IssuedDocument(StatusMixin, TimestampedModel):
    __tablename__ = "issued_documents"
    __table_args__ = (
        UniqueConstraint("document_number", name="uq_issued_documents_number"),
        UniqueConstraint("request_id", name="uq_issued_documents_request"),
        Index("ix_issued_documents_resident_status", "resident_id", "status"),
    )

    document_number: Mapped[str] = mapped_column(String(50), nullable=False)
    document_type_id: Mapped[int] = mapped_column(ForeignKey("document_types.id", ondelete="RESTRICT"), nullable=False)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id", ondelete="SET NULL"))
    purpose: Mapped[str | None] = mapped_column(String(255))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_signatory: Mapped[str] = mapped_column(String(200), nullable=False)
    verification_url: Mapped[str] = mapped_column(String(500), nullable=False)
    qr_code_data_uri: Mapped[str] = mapped_column(Text, nullable=False)
    verification_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    snapshot: Mapped[dict | None] = mapped_column(JSON)
    pdf_filename: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[DocumentType] = relationship(back_populates="issued_documents")
    resident: Mapped["Resident"] = relationship(back_populates="issued_documents")
    issued_by: Mapped["User | None"] = relationship()
    request: Mapped["Request | None"] = relationship(back_populates="issued_document", foreign_keys=[request_id])


class Request(StatusMixin, TimestampedModel):
    __tablename__ = "requests"
    __table_args__ = (Index("ix_requests_status_created", "status", "created_at"),)

    request_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    document_type_id: Mapped[int | None] = mapped_column(ForeignKey("document_types.id", ondelete="RESTRICT"), index=True)
    service_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    additional_requirements_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_filename: Mapped[str | None] = mapped_column(String(255))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    additional_data: Mapped[dict | None] = mapped_column(JSON)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_notes: Mapped[str | None] = mapped_column(Text)
    verification_digest: Mapped[str | None] = mapped_column(String(64))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signatory_id: Mapped[int | None] = mapped_column(ForeignKey("document_signatories.id", ondelete="RESTRICT"))
    resident: Mapped["Resident"] = relationship(back_populates="requests")
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id])
    payments: Mapped[list[Payment]] = relationship(back_populates="request")
    document_type: Mapped["DocumentType | None"] = relationship(back_populates="requests")
    requirements: Mapped[list[DocumentRequirement]] = relationship(back_populates="request", cascade="all, delete-orphan")
    status_history: Mapped[list[DocumentRequestEvent]] = relationship(back_populates="request", cascade="all, delete-orphan", order_by="DocumentRequestEvent.created_at")
    issued_document: Mapped["IssuedDocument | None"] = relationship(back_populates="request", uselist=False, foreign_keys="IssuedDocument.request_id")
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    verified_by: Mapped["User | None"] = relationship(foreign_keys=[verified_by_id])
    signatory: Mapped["DocumentSignatory | None"] = relationship()

    @property
    def active_requirements(self):
        from app.documents.workflow import active_requirements
        return active_requirements(self)


class DocumentSignatory(StatusMixin, TimestampedModel):
    """Names and designations explicitly authorized by an administrator."""
    __tablename__ = "document_signatories"
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    designation: Mapped[str] = mapped_column(String(100), nullable=False)
    authorized_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date)


class DocumentSequence(TimestampedModel):
    __tablename__ = "document_sequences"
    __table_args__ = (UniqueConstraint("template_code", "year", name="uq_document_sequence_year"),)
    template_code: Mapped[str] = mapped_column(String(10), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DocumentRequirement(TimestampedModel):
    """A requirement attached to a request, including uploaded evidence."""

    __tablename__ = "document_requirements"
    __table_args__ = (Index("ix_document_requirements_request_status", "request_id", "status"),)

    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    requirement_name: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    request: Mapped[Request] = relationship(back_populates="requirements")
    uploaded_by: Mapped["User | None"] = relationship()

    @property
    def image_available(self):
        from app.documents.workflow import evidence_available
        return evidence_available(self)


class DocumentRequestEvent(TimestampedModel):
    """Lifecycle event record for a document request."""

    __tablename__ = "document_request_events"
    __table_args__ = (Index("ix_document_request_events_request_created", "request_id", "created_at"),)

    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    request: Mapped[Request] = relationship(back_populates="status_history")
    changed_by: Mapped["User"] = relationship()


class BlotterCase(StatusMixin, TimestampedModel):
    __tablename__ = "blotter_cases"
    __table_args__ = (UniqueConstraint("case_number", name="uq_blotter_cases_number"), UniqueConstraint("incident_fingerprint", name="uq_blotter_cases_incident_fingerprint"), Index("ix_blotter_cases_status_incident_date", "status", "incident_date"), Index("ix_blotter_cases_category_purok", "category", "purok_id"), Index("ix_blotter_cases_status_queue", "status", "id"))

    incident_fingerprint: Mapped[str | None] = mapped_column(String(64))
    case_number: Mapped[str] = mapped_column(String(50), nullable=False)
    complainant_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    respondent_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="General Complaint")
    incident_date: Mapped[date] = mapped_column(Date, nullable=False)
    incident_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    incident_location: Mapped[str | None] = mapped_column(String(255))
    incident_latitude: Mapped[float | None] = mapped_column(Numeric(10, 6))  # GPS coordinates
    incident_longitude: Mapped[float | None] = mapped_column(Numeric(10, 6))  # GPS coordinates
    purok_id: Mapped[int | None] = mapped_column(ForeignKey("puroks.id", ondelete="SET NULL"), index=True)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    complainant: Mapped["Resident"] = relationship(back_populates="blotter_cases", foreign_keys=[complainant_id])
    purok: Mapped["Purok | None"] = relationship()
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id])
    parties: Mapped[list[BlotterParty]] = relationship(back_populates="case", cascade="all, delete-orphan")
    hearings: Mapped[list[BlotterHearing]] = relationship(back_populates="case", cascade="all, delete-orphan", order_by="BlotterHearing.scheduled_at")
    mediations: Mapped[list[BlotterMediation]] = relationship(back_populates="case", cascade="all, delete-orphan")
    settlements: Mapped[list[BlotterSettlement]] = relationship(back_populates="case", cascade="all, delete-orphan")
    endorsements: Mapped[list[BlotterEndorsement]] = relationship(back_populates="case", cascade="all, delete-orphan")
    status_history: Mapped[list[BlotterCaseEvent]] = relationship(back_populates="case", cascade="all, delete-orphan", order_by="BlotterCaseEvent.created_at")


class BlotterParty(TimestampedModel):
    __tablename__ = "blotter_parties"
    __table_args__ = (Index("ix_blotter_parties_case_role", "case_id", "role"),)
    case_id: Mapped[int] = mapped_column(ForeignKey("blotter_cases.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_information: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    case: Mapped[BlotterCase] = relationship(back_populates="parties")


class BlotterHearing(TimestampedModel):
    __tablename__ = "blotter_hearings"
    case_id: Mapped[int] = mapped_column(ForeignKey("blotter_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    case: Mapped[BlotterCase] = relationship(back_populates="hearings")


class BlotterMediation(TimestampedModel):
    __tablename__ = "blotter_mediations"
    case_id: Mapped[int] = mapped_column(ForeignKey("blotter_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mediator: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    case: Mapped[BlotterCase] = relationship(back_populates="mediations")


class BlotterSettlement(TimestampedModel):
    __tablename__ = "blotter_settlements"
    case_id: Mapped[int] = mapped_column(ForeignKey("blotter_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    terms: Mapped[str] = mapped_column(Text, nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signed_by: Mapped[str | None] = mapped_column(String(500))
    case: Mapped[BlotterCase] = relationship(back_populates="settlements")


class BlotterEndorsement(TimestampedModel):
    __tablename__ = "blotter_endorsements"
    case_id: Mapped[int] = mapped_column(ForeignKey("blotter_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    receiving_agency: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    endorsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    case: Mapped[BlotterCase] = relationship(back_populates="endorsements")


class BlotterCaseEvent(TimestampedModel):
    __tablename__ = "blotter_case_events"
    __table_args__ = (Index("ix_blotter_case_events_case_created", "case_id", "created_at"),)
    case_id: Mapped[int] = mapped_column(ForeignKey("blotter_cases.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    case: Mapped[BlotterCase] = relationship(back_populates="status_history")
    changed_by: Mapped["User"] = relationship()


class BlotterCaseAccess(TimestampedModel):
    __tablename__ = "blotter_case_access"
    __table_args__ = (UniqueConstraint("case_id", "resident_id", name="uq_blotter_case_access"),)
    case_id: Mapped[int] = mapped_column(ForeignKey("blotter_cases.id", ondelete="CASCADE"), nullable=False)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), nullable=False)
    granted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    case: Mapped[BlotterCase] = relationship()
    resident: Mapped["Resident"] = relationship()
    granted_by: Mapped["User"] = relationship()


class BusinessPermit(StatusMixin, TimestampedModel):
    __tablename__ = "business_permits"
    __table_args__ = (
        UniqueConstraint("permit_number", name="uq_business_permits_number"),
        Index("ix_business_permits_status_expiry", "status", "valid_until"),
    )

    permit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_type: Mapped[str | None] = mapped_column(String(150))
    business_address: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    applicant: Mapped["Resident"] = relationship(back_populates="business_permits")


class Payment(StatusMixin, TimestampedModel):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("receipt_number", name="uq_payments_receipt"),)

    receipt_number: Mapped[str] = mapped_column(String(50), nullable=False)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id", ondelete="SET NULL"))
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resident: Mapped["Resident"] = relationship(back_populates="payments")
    request: Mapped[Request | None] = relationship(back_populates="payments")
