"""Personnel and immutable RFID event records; all dates are stored in UTC."""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Date, Time, Text, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from .base import TimestampedModel


class PersonnelProfile(TimestampedModel):
    __tablename__='personnel_profiles'
    user_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),unique=True,nullable=True)
    employee_id=Column(String(50),unique=True,nullable=False)
    full_name=Column(String(200),nullable=False)
    photo_filename=Column(String(255),nullable=True)
    position=Column(String(100),nullable=False)
    personnel_type=Column(String(20),nullable=False)
    department=Column(String(100),nullable=True,index=True)
    mobile=Column(String(30),nullable=True)
    email=Column(String(255),nullable=True)
    employment_status=Column(String(40),nullable=True,default='Regular')
    active=Column(Boolean,nullable=False,default=True)
    pin_hash=Column(String(255))
    user=relationship('User')
    schedules=relationship('EmployeeSchedule',back_populates='personnel')
    cards=relationship('RFIDCard',back_populates='personnel')


class RFIDCard(TimestampedModel):
    __tablename__='rfid_cards'
    personnel_id=Column(ForeignKey('personnel_profiles.id',ondelete='RESTRICT'),nullable=False,index=True)
    uid_hash=Column(String(64),unique=True,nullable=False)
    uid_suffix=Column(String(8),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    __table_args__=(Index('uq_rfid_one_active_personnel','personnel_id',unique=True,postgresql_where=active.is_(True),sqlite_where=active.is_(True)),)
    revoked_at=Column(DateTime(timezone=True))
    personnel=relationship('PersonnelProfile',back_populates='cards')


class AttendanceDevice(TimestampedModel):
    __tablename__='attendance_devices'
    name=Column(String(100),nullable=False)
    hardware=Column(String(30),nullable=False,default='Arduino Uno')
    credential_hash=Column(String(64),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    require_pin=Column(Boolean,nullable=False,default=False)
    last_seen_at=Column(DateTime(timezone=True))
    last_error=Column(String(200))


class EmployeeSchedule(TimestampedModel):
    __tablename__='employee_schedules'
    personnel_id=Column(ForeignKey('personnel_profiles.id',ondelete='RESTRICT'),nullable=False,index=True)
    name=Column(String(80),nullable=False)
    start_time=Column(Time,nullable=False)
    end_time=Column(Time,nullable=False)
    weekdays=Column(JSON,nullable=False,default=lambda:[0,1,2,3,4])
    grace_minutes=Column(Integer,nullable=False,default=15)
    cutoff_minutes=Column(Integer,nullable=False,default=120)
    minimum_session_minutes=Column(Integer,nullable=False,default=1)
    max_sessions=Column(Integer,nullable=False,default=1)
    flexible=Column(Boolean,nullable=False,default=False)
    active=Column(Boolean,nullable=False,default=True)
    effective_from=Column(Date,nullable=False)
    effective_until=Column(Date)
    personnel=relationship('PersonnelProfile',back_populates='schedules')


class AttendanceSession(TimestampedModel):
    __tablename__='attendance_sessions'
    personnel_id=Column(ForeignKey('personnel_profiles.id',ondelete='RESTRICT'),nullable=False,index=True)
    schedule_id=Column(ForeignKey('employee_schedules.id',ondelete='RESTRICT'),nullable=False)
    work_date=Column(Date,nullable=False,index=True)
    time_in=Column(DateTime(timezone=True),nullable=False)
    time_out=Column(DateTime(timezone=True))
    late_minutes=Column(Integer,nullable=False,default=0)
    overtime_approved=Column(Boolean,nullable=False,default=False)
    personnel=relationship('PersonnelProfile')
    schedule=relationship('EmployeeSchedule')


class AttendanceLog(TimestampedModel):
    __tablename__='attendance_logs'
    __table_args__=(UniqueConstraint('device_id','event_id',name='uq_attendance_device_event'),)
    device_id=Column(ForeignKey('attendance_devices.id',ondelete='RESTRICT'),nullable=False,index=True)
    event_id=Column(String(64),nullable=False)
    personnel_id=Column(ForeignKey('personnel_profiles.id',ondelete='RESTRICT'),index=True)
    session_id=Column(ForeignKey('attendance_sessions.id',ondelete='RESTRICT'))
    occurred_at=Column(DateTime(timezone=True),nullable=False,index=True)
    action=Column(String(20),nullable=False)
    accepted=Column(Boolean,nullable=False)
    message=Column(String(255),nullable=False)
    offline=Column(Boolean,nullable=False,default=False)
    personnel=relationship('PersonnelProfile')


class AttendanceAdjustment(TimestampedModel):
    __tablename__='attendance_adjustments'
    session_id=Column(ForeignKey('attendance_sessions.id',ondelete='RESTRICT'),nullable=False,index=True)
    actor_id=Column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    reason=Column(Text,nullable=False)
    before=Column(JSON,nullable=False)
    after=Column(JSON,nullable=False)


class EmployeeLeave(TimestampedModel):
    __tablename__='employee_leaves'
    personnel_id=Column(ForeignKey('personnel_profiles.id',ondelete='RESTRICT'),nullable=False,index=True)
    start_date=Column(Date,nullable=False)
    end_date=Column(Date,nullable=False)
    status=Column(String(20),nullable=False,default='pending')
    reason=Column(String(255),nullable=False)
    approved_by_id=Column(ForeignKey('users.id',ondelete='RESTRICT'))
    personnel=relationship('PersonnelProfile')


class AttendanceAuditLog(TimestampedModel):
    __tablename__='attendance_audit_logs'
    actor_id=Column(ForeignKey('users.id',ondelete='RESTRICT'))
    device_id=Column(ForeignKey('attendance_devices.id',ondelete='RESTRICT'))
    entity_id=Column(Integer)
    action=Column(String(50),nullable=False)
    details=Column(Text,nullable=False)
