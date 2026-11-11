"""Resident, household, geographic, official, and registry models."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, JSON, Integer, event, Boolean, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import StatusMixin, TimestampedModel

if TYPE_CHECKING:
    from .auth import User
    from .services import BusinessPermit, BlotterCase, IssuedDocument, Payment, Request


class Purok(StatusMixin, TimestampedModel):
    __tablename__ = "puroks"
    __table_args__ = (
        UniqueConstraint("name", name="uq_puroks_name"),
        UniqueConstraint("name_key", name="uq_puroks_name_key"),
        UniqueConstraint("purok_number", name="uq_puroks_number"),
        CheckConstraint("name_key = lower(name) AND name = trim(name) AND name NOT LIKE '%  %'", name="ck_puroks_normalized"),
        CheckConstraint("length(name) >= 2 AND length(name) <= 100", name="ck_puroks_name_length"),
        CheckConstraint("purok_number IS NULL OR (purok_number >= 1 AND purok_number <= 9999)", name="ck_puroks_number_range"),
    )
    name_key: Mapped[str] = mapped_column(String(100), nullable=False)
    purok_number: Mapped[int | None] = mapped_column(Integer)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    households: Mapped[list[Household]] = relationship(back_populates="purok")
    residents: Mapped[list[Resident]] = relationship(back_populates="purok")
    hazard_zones: Mapped[list["HazardZone"]] = relationship(back_populates="purok")


class Household(StatusMixin, TimestampedModel):
    __tablename__ = "households"
    __table_args__ = (Index("ix_households_purok_status", "purok_id", "status"),)

    household_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    purok_id: Mapped[int] = mapped_column(ForeignKey("puroks.id", ondelete="RESTRICT"), nullable=False)
    head_resident_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "residents.id",
            name="fk_households_head_resident",
            ondelete="SET NULL",
            use_alter=True,
        )
    )
    purok: Mapped[Purok] = relationship(back_populates="households")
    head_resident: Mapped[Resident | None] = relationship(foreign_keys=[head_resident_id], post_update=True)
    residents: Mapped[list[Resident]] = relationship(
        back_populates="household",
        foreign_keys="Resident.household_id",
    )


class Resident(StatusMixin, TimestampedModel):
    __tablename__ = "residents"
    __table_args__ = (
        UniqueConstraint("household_id", "household_member_no", name="uq_residents_household_member"),
        Index("ix_residents_name", "last_name", "first_name"),
        Index("ix_residents_purok_status", "purok_id", "status"),
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    suffix: Mapped[str | None] = mapped_column(String(20))
    sex: Mapped[str | None] = mapped_column(String(30))
    birth_date: Mapped[date | None] = mapped_column(Date)
    civil_status: Mapped[str | None] = mapped_column(String(30))
    place_of_birth: Mapped[str | None] = mapped_column(String(200))
    religion: Mapped[str | None] = mapped_column(String(100))
    educational_attainment: Mapped[str | None] = mapped_column(String(80))
    household_relationship: Mapped[str | None] = mapped_column(String(80))
    house_no: Mapped[str | None] = mapped_column(String(100))
    street_landmark: Mapped[str | None] = mapped_column(String(155))
    residency_duration: Mapped[str | None] = mapped_column(String(40))
    proof_of_residency_filename: Mapped[str | None] = mapped_column(String(255))
    philsys_card_filename: Mapped[str | None] = mapped_column(String(255))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_relationship: Mapped[str | None] = mapped_column(String(80))
    emergency_contact_number: Mapped[str | None] = mapped_column(String(30))
    special_categories: Mapped[list[str] | None] = mapped_column(JSON)
    nationality: Mapped[str] = mapped_column(String(80), nullable=False, default="Filipino")
    contact_number: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    address_line: Mapped[str | None] = mapped_column(String(255))
    occupation: Mapped[str | None] = mapped_column(String(150))
    voter_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    profile_photo_filename: Mapped[str | None] = mapped_column(String(255))
    household_member_no: Mapped[int | None] = mapped_column()
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id", ondelete="SET NULL"))
    purok_id: Mapped[int | None] = mapped_column(ForeignKey("puroks.id", ondelete="SET NULL"), index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    household: Mapped[Household | None] = relationship(back_populates="residents", foreign_keys=[household_id])
    purok: Mapped[Purok | None] = relationship(back_populates="residents")
    requests: Mapped[list[Request]] = relationship(back_populates="resident")
    issued_documents: Mapped[list[IssuedDocument]] = relationship(back_populates="resident")
    blotter_cases: Mapped[list[BlotterCase]] = relationship(back_populates="complainant", foreign_keys="BlotterCase.complainant_id")
    business_permits: Mapped[list[BusinessPermit]] = relationship(back_populates="applicant")
    health_records: Mapped[list[HealthRegistry]] = relationship(back_populates="resident")
    social_records: Mapped[list[SocialWelfareRegistry]] = relationship(back_populates="resident")
    payments: Mapped[list[Payment]] = relationship(back_populates="resident")
    user: Mapped["User | None"] = relationship(back_populates="resident", foreign_keys="User.resident_id")
    correction_requests: Mapped[list[ResidentCorrectionRequest]] = relationship(back_populates="resident")


class Official(StatusMixin, TimestampedModel):
    __tablename__ = "officials"
    __table_args__ = (Index("ix_officials_term", "term_start", "term_end"),)

    resident_id: Mapped[int | None] = mapped_column(ForeignKey("residents.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    term_start: Mapped[date] = mapped_column(Date, nullable=False)
    term_end: Mapped[date | None] = mapped_column(Date)
    contact_number: Mapped[str | None] = mapped_column(String(30))
    resident: Mapped[Resident | None] = relationship()
    user: Mapped["User | None"] = relationship(
        back_populates="official",
        foreign_keys="User.official_id",
        uselist=False,
    )


class HealthRegistry(StatusMixin, TimestampedModel):
    __tablename__ = "health_registry"
    __table_args__ = (UniqueConstraint("resident_id", name="uq_health_registry_resident"),)

    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), nullable=False)
    blood_type: Mapped[str | None] = mapped_column(String(10))
    medical_conditions: Mapped[str | None] = mapped_column(Text)
    allergies: Mapped[str | None] = mapped_column(Text)
    disability_details: Mapped[str | None] = mapped_column(Text)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_number: Mapped[str | None] = mapped_column(String(30))
    resident: Mapped[Resident] = relationship(back_populates="health_records")


class SocialWelfareRegistry(StatusMixin, TimestampedModel):
    __tablename__ = "social_welfare_registry"
    __table_args__ = (Index("ix_social_registry_category", "category", "status"),)

    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    household_income: Mapped[float | None] = mapped_column()
    assistance_notes: Mapped[str | None] = mapped_column(Text)
    resident: Mapped[Resident] = relationship(back_populates="social_records")


class ResidentCorrectionRequest(StatusMixin, TimestampedModel):
    """Resident-submitted request to correct a specific personal field."""

    __tablename__ = "resident_correction_requests"
    __table_args__ = (Index("ix_correction_requests_resident_status", "resident_id", "status"),)

    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), nullable=False)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_value: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    resident: Mapped[Resident] = relationship(back_populates="correction_requests")
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])


@event.listens_for(Purok, "before_insert")
@event.listens_for(Purok, "before_update")
def normalize_purok(mapper, connection, target):
    from app.normalization import purok_identity
    target.name, target.name_key, inferred = purok_identity(target.name)
    if inferred is not None:
        if target.purok_number not in (None, inferred):
            raise ValueError("Purok number must match its name.")
        target.purok_number = inferred
    if target.purok_number is not None and not 1 <= target.purok_number <= 9999:
        raise ValueError("Purok number must be between 1 and 9999.")
