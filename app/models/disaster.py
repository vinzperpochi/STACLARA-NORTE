"""Disaster risk reduction and management models."""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import StatusMixin, TimestampedModel

class EvacuationCenter(StatusMixin, TimestampedModel):
    __tablename__ = "evacuation_centers"
    __table_args__ = (UniqueConstraint("name", name="uq_evacuation_centers_name"),)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    facilities: Mapped[str | None] = mapped_column(Text)
    current_status: Mapped[str] = mapped_column(String(40), nullable=False, default="AVAILABLE")
    contact_person: Mapped[str | None] = mapped_column(String(200))
    contact_number: Mapped[str | None] = mapped_column(String(30))
    incidents: Mapped[list[DRRMIncident]] = relationship(back_populates="evacuation_center")
    relief_records: Mapped[list[ReliefRecord]] = relationship(back_populates="evacuation_center")

class DRRMIncident(StatusMixin, TimestampedModel):
    __tablename__ = "drrm_incidents"
    __table_args__ = (Index("ix_drrm_incidents_type_status_started", "incident_type", "status", "started_at"),)
    incident_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    incident_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    affected_households: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    injuries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    damage_assessment: Mapped[str | None] = mapped_column(Text)
    response_actions: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evacuation_center_id: Mapped[int | None] = mapped_column(ForeignKey("evacuation_centers.id", ondelete="SET NULL"))
    reported_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    evacuation_center: Mapped[EvacuationCenter | None] = relationship(back_populates="incidents")
    reported_by: Mapped["User | None"] = relationship()
    relief_records: Mapped[list[ReliefRecord]] = relationship(back_populates="incident")

class ReliefRecord(StatusMixin, TimestampedModel):
    __tablename__ = "relief_records"
    __table_args__ = (Index("ix_relief_records_incident_distributed", "incident_id", "distributed_at"),)
    incident_id: Mapped[int] = mapped_column(ForeignKey("drrm_incidents.id", ondelete="CASCADE"), nullable=False)
    evacuation_center_id: Mapped[int | None] = mapped_column(ForeignKey("evacuation_centers.id", ondelete="SET NULL"))
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id", ondelete="SET NULL"))
    item_description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    distributed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distributed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    incident: Mapped[DRRMIncident] = relationship(back_populates="relief_records")
    evacuation_center: Mapped[EvacuationCenter | None] = relationship(back_populates="relief_records")
    household: Mapped["Household | None"] = relationship()
    distributed_by: Mapped["User | None"] = relationship()

class HazardZone(StatusMixin, TimestampedModel):
    __tablename__ = "hazard_zones"
    __table_args__ = (Index("ix_hazard_zones_type_status", "hazard_type", "status"),)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    hazard_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    purok_id: Mapped[int | None] = mapped_column(ForeignKey("puroks.id", ondelete="SET NULL"))
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False, default="medium")
    purok: Mapped["Purok | None"] = relationship(back_populates="hazard_zones")

class EmergencyContact(StatusMixin, TimestampedModel):
    __tablename__ = "emergency_contacts"
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    agency: Mapped[str | None] = mapped_column(String(150))
    contact_number: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    availability_notes: Mapped[str | None] = mapped_column(Text)

class DRRMEquipment(StatusMixin, TimestampedModel):
    __tablename__ = "drrm_equipment"
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    condition: Mapped[str] = mapped_column(String(50), nullable=False, default="GOOD")
    storage_location: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

class ReliefSupply(StatusMixin, TimestampedModel):
    __tablename__ = "relief_supplies"
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    quantity_on_hand: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="units")
    storage_location: Mapped[str | None] = mapped_column(String(200))
    expiry_date: Mapped[date | None] = mapped_column(Date)

class DamageReport(StatusMixin, TimestampedModel):
    __tablename__ = "drrm_damage_reports"
    incident_id: Mapped[int] = mapped_column(ForeignKey("drrm_incidents.id", ondelete="CASCADE"), nullable=False)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id", ondelete="SET NULL"))
    property_description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 2))
    assessment_notes: Mapped[str | None] = mapped_column(Text)
    incident: Mapped[DRRMIncident] = relationship()
    household: Mapped["Household | None"] = relationship()

class EmergencyAlert(StatusMixin, TimestampedModel):
    __tablename__ = "emergency_alerts"
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    alert_level: Mapped[str] = mapped_column(String(30), nullable=False, default="ADVISORY")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    issued_by: Mapped["User | None"] = relationship()
