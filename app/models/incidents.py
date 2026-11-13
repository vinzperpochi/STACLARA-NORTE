"""Incident routing records complement, rather than replace, existing blotter cases."""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Date, Text, JSON, Float, ForeignKey, LargeBinary
from sqlalchemy.orm import deferred, relationship
from .base import TimestampedModel


class GovernmentAgency(TimestampedModel):
    __tablename__='government_agencies'
    code=Column(String(30),unique=True,nullable=False)
    name=Column(String(180),nullable=False)
    service_area=Column(String(180),nullable=False,default='Pila, Laguna')
    jurisdiction=Column(Text,nullable=False,default='Review by authorized personnel required')
    active=Column(Boolean,nullable=False,default=True)


class AgencyHotline(TimestampedModel):
    __tablename__='agency_hotlines'
    agency_id=Column(ForeignKey('government_agencies.id',ondelete='RESTRICT'),nullable=False,index=True)
    number=Column(String(30),nullable=False)
    availability=Column(String(150),nullable=False)
    coverage=Column(String(180),nullable=False)
    verified_on=Column(Date)
    verification_source=Column(String(500))
    active=Column(Boolean,nullable=False,default=True)
    emergency=Column(Boolean,nullable=False,default=False)
    agency=relationship('GovernmentAgency')


class HotlineVerification(TimestampedModel):
    __tablename__='hotline_verifications'
    hotline_id=Column(ForeignKey('agency_hotlines.id',ondelete='RESTRICT'),nullable=False)
    actor_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    source=Column(String(500),nullable=False)
    verified_on=Column(Date,nullable=False)


class IncidentCategory(TimestampedModel):
    __tablename__='incident_categories'
    code=Column(String(40),nullable=False,unique=True)
    name=Column(String(150),nullable=False)
    sensitive=Column(Boolean,nullable=False,default=False)
    active=Column(Boolean,nullable=False,default=True)


class IncidentRoutingRule(TimestampedModel):
    __tablename__='incident_routing_rules'
    category_id=Column(ForeignKey('incident_categories.id',ondelete='RESTRICT'),nullable=False,unique=True)
    agency_codes=Column(JSON,nullable=False)
    keywords=Column(JSON,nullable=False)
    classification=Column(String(30),nullable=False)
    priority=Column(Integer,nullable=False,default=50)
    active=Column(Boolean,nullable=False,default=True)
    version=Column(Integer,nullable=False,default=1)
    category=relationship('IncidentCategory')


class ResidentComplaint(TimestampedModel):
    __tablename__='resident_complaints'
    resident_id=Column(ForeignKey('residents.id',ondelete='RESTRICT'),nullable=False,index=True)
    blotter_case_id=Column(ForeignKey('blotter_cases.id',ondelete='RESTRICT'))
    reference=Column(String(50),nullable=False,unique=True)
    title=Column(String(200),nullable=False)
    category_id=Column(ForeignKey('incident_categories.id',ondelete='RESTRICT'),nullable=False)
    description=Column(Text,nullable=False)
    incident_at=Column(DateTime(timezone=True),nullable=False)
    location=Column(String(255),nullable=False)
    latitude=Column(Float)
    longitude=Column(Float)
    urgency=Column(String(20),nullable=False)
    immediate_danger=Column(Boolean,nullable=False,default=False)
    classification=Column(String(30),nullable=False)
    routing_snapshot=Column(JSON,nullable=False)
    restricted=Column(Boolean,nullable=False,default=False)
    status=Column(String(40),nullable=False,default='SUBMITTED',index=True)
    response_status=Column(String(40),nullable=False,default='NOT_CONFIRMED')
    resolved_at=Column(DateTime(timezone=True))
    resident=relationship('Resident')
    category=relationship('IncidentCategory')
    evidence=relationship('ComplaintEvidence',back_populates='complaint')
    history=relationship('ComplaintStatusHistory',back_populates='complaint',order_by='ComplaintStatusHistory.created_at')
    referrals=relationship('ComplaintReferral',back_populates='complaint')
    assignments=relationship('ComplaintAssignment',back_populates='complaint')


class EmergencyIncident(TimestampedModel):
    __tablename__='emergency_incidents'
    complaint_id=Column(ForeignKey('resident_complaints.id',ondelete='RESTRICT'),nullable=False,unique=True)
    priority=Column(String(20),nullable=False,default='URGENT')
    response_status=Column(String(40),nullable=False,default='NOT_CONFIRMED')
    confirmation_source=Column(String(255))


class ComplaintAssignment(TimestampedModel):
    __tablename__='complaint_assignments'
    complaint_id=Column(ForeignKey('resident_complaints.id',ondelete='RESTRICT'),nullable=False,index=True)
    user_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    assigned_by_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    user=relationship('User',foreign_keys=[user_id])
    complaint=relationship('ResidentComplaint',back_populates='assignments')


class ComplaintReferral(TimestampedModel):
    __tablename__='complaint_referrals'
    complaint_id=Column(ForeignKey('resident_complaints.id',ondelete='RESTRICT'),nullable=False,index=True)
    agency_id=Column(ForeignKey('government_agencies.id',ondelete='RESTRICT'),nullable=False)
    approved_by_id=Column(ForeignKey('users.id',ondelete='RESTRICT'))
    reason=Column(Text,nullable=False)
    status=Column(String(30),nullable=False,default='APPROVED_FOR_REFERRAL')
    response=Column(Text)
    transmitted_at=Column(DateTime(timezone=True))
    handoff_source=Column(String(255))
    agency=relationship('GovernmentAgency')
    complaint=relationship('ResidentComplaint',back_populates='referrals')


class ComplaintStatusHistory(TimestampedModel):
    __tablename__='complaint_status_history'
    complaint_id=Column(ForeignKey('resident_complaints.id',ondelete='RESTRICT'),nullable=False,index=True)
    actor_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    from_status=Column(String(40))
    to_status=Column(String(40),nullable=False)
    public_response=Column(Text,nullable=False)
    private_notes=Column(Text)
    complaint=relationship('ResidentComplaint',back_populates='history')


class ComplaintEvidence(TimestampedModel):
    __tablename__='complaint_evidence'
    complaint_id=Column(ForeignKey('resident_complaints.id',ondelete='RESTRICT'),nullable=False,index=True)
    filename=Column(String(255),nullable=False)
    file_data=deferred(Column(LargeBinary))
    original_name=Column(String(200),nullable=False)
    mime_type=Column(String(80),nullable=False)
    uploaded_by_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    complaint=relationship('ResidentComplaint',back_populates='evidence')


class ComplaintNotification(TimestampedModel):
    __tablename__='complaint_notifications'
    complaint_id=Column(ForeignKey('resident_complaints.id',ondelete='RESTRICT'),nullable=False)
    notification_id=Column(ForeignKey('notifications.id',ondelete='RESTRICT'),nullable=False)


class ComplaintAuditLog(TimestampedModel):
    __tablename__='complaint_audit_logs'
    complaint_id=Column(ForeignKey('resident_complaints.id',ondelete='RESTRICT'))
    actor_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    action=Column(String(60),nullable=False)
    details=Column(Text,nullable=False)
