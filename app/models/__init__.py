"""SQLAlchemy model registry.

Importing this module imports every model class and association table, which is
required for Flask-Migrate/Alembic metadata discovery.
"""

from .auth import AuditLog, LoginAttempt, Notification, Permission, Role, User, UserSession
from .base import Base, BaseModelMixin, StatusMixin, TimestampedModel
from .disaster import DamageReport, DRRMEquipment, DRRMIncident, EmergencyAlert, EmergencyContact, EvacuationCenter, HazardZone, ReliefRecord, ReliefSupply
from .governance import Announcement, Event
from .people import (
    HealthRegistry,
    Household,
    Official,
    Purok,
    Resident,
    ResidentCorrectionRequest,
    SocialWelfareRegistry,
)
from .services import (
    BlotterCase,
    BlotterCaseAccess,
    BlotterCaseEvent,
    BlotterEndorsement,
    BlotterHearing,
    BlotterMediation,
    BlotterParty,
    BlotterSettlement,
    BusinessPermit,
    DocumentRequestEvent,
    DocumentRequirement,
    DocumentType,
    DocumentSignatory,
    DocumentSequence,
    IssuedDocument,
    Payment,
    Request,
)
from .system import FeeConfiguration, SystemSetting
from .phase9 import AssistanceRecord, BeneficiaryRegistry, BusinessClearanceRequest, BusinessRecord
from .phase12 import CollectionEntry, QueueRequest
from .messaging import Message, MessageThread
from .attendance import PersonnelProfile, RFIDCard, AttendanceDevice, EmployeeSchedule, AttendanceSession, AttendanceLog, AttendanceAdjustment, EmployeeLeave, AttendanceAuditLog
from .incidents import GovernmentAgency, AgencyHotline, HotlineVerification, IncidentCategory, IncidentRoutingRule, ResidentComplaint, EmergencyIncident, ComplaintAssignment, ComplaintReferral, ComplaintStatusHistory, ComplaintEvidence, ComplaintNotification, ComplaintAuditLog

__all__ = [
    "Announcement",
    "AssistanceRecord",
    "AuditLog",
    "Base",
    "BaseModelMixin",
    "BeneficiaryRegistry",
    "BlotterCase",
    "BlotterCaseAccess",
    "BlotterCaseEvent",
    "BlotterEndorsement",
    "BlotterHearing",
    "BlotterMediation",
    "BlotterParty",
    "BlotterSettlement",
    "BusinessPermit",
    "BusinessClearanceRequest",
    "BusinessRecord",
    "CollectionEntry",
    "DamageReport",
    "DRRMEquipment",
    "DocumentType",
    "DocumentRequestEvent",
    "DocumentRequirement",
    "DRRMIncident",
    "Event",
    "EmergencyAlert",
    "EmergencyContact",
    "FeeConfiguration",
    "EvacuationCenter",
    "HazardZone",
    "HealthRegistry",
    "Household",
    "IssuedDocument",
    "LoginAttempt",
    "Notification",
    "Official",
    "Payment",
    "Permission",
    "Purok",
    "QueueRequest",
    "ReliefSupply",
    "ReliefRecord",
    "Request",
    "Resident",
    "ResidentCorrectionRequest",
    "Role",
    "SocialWelfareRegistry",
    "StatusMixin",
    "SystemSetting",
    "TimestampedModel",
    "User",
    "UserSession",
    "Message",
    "MessageThread",
]
