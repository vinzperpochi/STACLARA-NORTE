"""Attendance decisions use locked employee rows and replay-safe device events."""
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from hashlib import sha256
import re
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash
from app.extensions import db
from app.models import PersonnelProfile, RFIDCard, AttendanceDevice, EmployeeSchedule, AttendanceSession, AttendanceLog, EmployeeLeave, AttendanceAuditLog

MANILA=ZoneInfo('Asia/Manila')
EARLY_TIME_IN_MINUTES=5


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def uid_hash(value):
    value=re.sub(r'[ :\-]','',str(value)).upper()
    if not re.fullmatch(r'(?:[0-9A-F]{8}|[0-9A-F]{14}|[0-9A-F]{20})',value):
        raise ValueError('RFID UID must contain 4, 7 or 10 hexadecimal bytes.')
    return sha256(value.encode()).hexdigest(),value[-8:]


def bounds(schedule,work_date):
    start=datetime.combine(work_date,schedule.start_time,MANILA)
    end=datetime.combine(work_date,schedule.end_time,MANILA)
    if end<=start: end+=timedelta(days=1)
    return start.astimezone(timezone.utc),end.astimezone(timezone.utc)


def scheduled(schedule,day):
    return schedule.active and schedule.effective_from<=day and (not schedule.effective_until or day<=schedule.effective_until) and day.weekday() in schedule.weekdays


def duty_days_change_date(schedule,today):
    """Keep completed work dates attached to their original schedule version."""
    last_work_date=db.session.scalar(select(func.max(AttendanceSession.work_date)).where(AttendanceSession.schedule_id==schedule.id))
    return max(today,schedule.effective_from,last_work_date+timedelta(days=1) if last_work_date else today)


def change_duty_days(schedule,weekdays,today):
    days=sorted(set(weekdays))
    if not days or any(day not in range(7) for day in days):
        raise ValueError('Select at least one valid duty day. Multiple days are allowed.')
    if not schedule.active or (schedule.effective_until and (schedule.effective_until<today or schedule.effective_until<schedule.effective_from)):
        raise ValueError('This schedule has ended or is inactive. Add a new duty schedule.')
    if days==sorted(schedule.weekdays): return schedule,None
    effective=duty_days_change_date(schedule,today)
    if schedule.effective_until and effective>schedule.effective_until:
        raise ValueError('Attendance already covers the remaining dates. Add a new future schedule.')
    if schedule.effective_from<effective:
        # Closing the old version preserves previous attendance and absence rules.
        values={key:getattr(schedule,key) for key in ['personnel_id','name','start_time','end_time','grace_minutes','cutoff_minutes','minimum_session_minutes','max_sessions','flexible','effective_until']}
        replacement=EmployeeSchedule(**values,weekdays=days,effective_from=effective,active=True)
        schedule.effective_until=effective-timedelta(days=1)
        db.session.add(replacement);db.session.flush()
        return replacement,effective
    schedule.weekdays=days
    return schedule,effective


def schedule_for(person,occurred):
    occurred=utc(occurred)
    local=occurred.astimezone(MANILA)
    active=[schedule for schedule in person.schedules if schedule.active]
    if not active:
        raise ValueError('No active work schedule assigned.')
    effective=[(schedule,day) for schedule in active
               for day in [local.date()-timedelta(days=1),local.date()]
               if schedule.effective_from<=day and (not schedule.effective_until or day<=schedule.effective_until)]
    # An early tap for a shift just after midnight belongs to tomorrow's duty day.
    tomorrow=local.date()+timedelta(days=1)
    for schedule in active:
        start,_=bounds(schedule,tomorrow)
        if scheduled(schedule,tomorrow) and start-timedelta(minutes=EARLY_TIME_IN_MINUTES)<=occurred<start:
            effective.append((schedule,tomorrow))
    if not effective:
        raise ValueError(f'No effective schedule for {local:%a %b %d, %Y} PHT.')
    applicable=[(schedule,day) for schedule,day in effective if day.weekday() in schedule.weekdays]
    if not applicable:
        raise ValueError(f'Not a scheduled work day: {local:%a %b %d, %Y} PHT.')
    choices=[];openings=[]
    for schedule,day in applicable:
        start,end=bounds(schedule,day)
        opens=start-timedelta(minutes=EARLY_TIME_IN_MINUTES)
        if opens<=occurred<=end+timedelta(hours=4):
            choices.append((abs((occurred-start).total_seconds()),schedule,day))
        elif occurred<opens:
            openings.append(opens)
    if not choices:
        if openings:
            opens=min(openings).astimezone(MANILA)
            raise ValueError(f'Too early. Time In opens at {opens:%I:%M %p} PHT.')
        raise ValueError(f'Outside schedule scan window: {local:%a %H:%M} PHT.')
    _,schedule,day=min(choices,key=lambda value:value[0]);return schedule,day


def session_metrics(session):
    start,end=bounds(session.schedule,session.work_date)
    finish=utc(session.time_out) if session.time_out else None
    worked=max(0,int((finish-utc(session.time_in)).total_seconds()/60)) if finish else 0
    required=max(0,int((end-start).total_seconds()/60))
    return {'worked_minutes':worked,'hours':round(worked/60,2),'late_minutes':session.late_minutes,
            'short_session':bool(finish and worked<session.schedule.minimum_session_minutes),
            'early_minutes':max(0,int((end-finish).total_seconds()/60)) if finish else 0,
            'undertime_minutes':max(0,required-worked) if finish else 0,
            'overtime_minutes':max(0,worked-required) if session.overtime_approved else 0,
            'overtime_pending_minutes':max(0,worked-required) if not session.overtime_approved else 0}


def scan(device,event_id,uid,occurred=None,pin=None,action='AUTO'):
    now=datetime.now(timezone.utc)
    if not re.fullmatch(r'[A-Za-z0-9_\-]{8,64}',str(event_id)): raise ValueError('A unique event ID of 8–64 characters is required.')
    # Serialize calls from the same device and from different devices sharing a card.
    device=db.session.scalar(select(AttendanceDevice).where(AttendanceDevice.id==device.id).with_for_update())
    replay=db.session.scalar(select(AttendanceLog).where(AttendanceLog.device_id==device.id,AttendanceLog.event_id==event_id))
    if replay: return replay,True
    occurred=utc(occurred or now)
    if occurred>now+timedelta(minutes=2) or occurred<now-timedelta(days=__import__('flask').current_app.config.get('ATTENDANCE_OFFLINE_WINDOW_DAYS',7)): raise ValueError('Scan time is outside the allowed offline window.')
    device.last_seen_at=now
    personnel=None;session=None;accepted=False;result_action='REJECTED'
    try:
        if not device.active: raise ValueError('Device is inactive.')
        digest,_=uid_hash(uid)
        card=db.session.scalar(select(RFIDCard).where(RFIDCard.uid_hash==digest,RFIDCard.active.is_(True)))
        if not card: raise ValueError('Unregistered or revoked RFID card.')
        personnel=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.id==card.personnel_id).with_for_update())
        if not personnel.active or (personnel.user and (not personnel.user.is_active or personnel.user.status!='active')): raise ValueError('Personnel account is inactive.')
        if device.require_pin and (not personnel.pin_hash or not check_password_hash(personnel.pin_hash,str(pin or ''))): raise ValueError('PIN verification required or incorrect.')
        last=db.session.scalar(select(AttendanceLog).where(AttendanceLog.personnel_id==personnel.id,AttendanceLog.accepted.is_(True)).order_by(AttendanceLog.occurred_at.desc()).limit(1))
        if last and (occurred-utc(last.occurred_at)).total_seconds()<30: raise ValueError('Repeated or out-of-order scan ignored. Wait 30 seconds.')
        session=db.session.scalar(select(AttendanceSession).where(AttendanceSession.personnel_id==personnel.id,AttendanceSession.time_out.is_(None)).order_by(AttendanceSession.time_in.desc()).limit(1))
        if action not in {'AUTO','IN','OUT'}: raise ValueError('Invalid attendance action.')
        if session:
            if action=='IN': raise ValueError('Already clocked in.')
            if occurred<=utc(session.time_in): raise ValueError('Time Out must follow Time In.')
            if occurred>utc(session.time_in)+timedelta(hours=24): raise ValueError('Open session exceeds 24 hours. Administrator correction required.')
            session.time_out=occurred;result_action='OUT'
            _,scheduled_end=bounds(session.schedule,session.work_date)
            early=max(0,int((scheduled_end-occurred).total_seconds()/60))
            message=f'Early Time Out recorded ({early} min before shift end)' if early else 'Time Out recorded'
        else:
            if action=='OUT': raise ValueError('No open session to clock out.')
            schedule,day=schedule_for(personnel,occurred)
            leave=db.session.scalar(select(EmployeeLeave).where(EmployeeLeave.personnel_id==personnel.id,EmployeeLeave.status=='approved',EmployeeLeave.start_date<=day,EmployeeLeave.end_date>=day))
            if leave: raise ValueError('Approved leave applies to this work date.')
            previous=db.session.scalars(select(AttendanceSession).where(AttendanceSession.personnel_id==personnel.id,AttendanceSession.schedule_id==schedule.id,AttendanceSession.work_date==day)).all()
            if len(previous)>=schedule.max_sessions: raise ValueError('Maximum authorized work sessions reached.')
            start,_=bounds(schedule,day)
            late=0 if schedule.flexible or previous else max(0,int((occurred-start).total_seconds()/60)-schedule.grace_minutes)
            session=AttendanceSession(personnel_id=personnel.id,schedule_id=schedule.id,work_date=day,time_in=occurred,late_minutes=late)
            db.session.add(session);db.session.flush();result_action='IN';message='Late Time In recorded' if late else 'Time In recorded'
        accepted=True;device.last_error=None
    except ValueError as error:
        message=str(error);device.last_error=message[:200]
    event=AttendanceLog(device_id=device.id,event_id=event_id,personnel_id=personnel.id if personnel else None,session_id=session.id if session and accepted else None,occurred_at=occurred,action=result_action,accepted=accepted,message=message,offline=(now-occurred).total_seconds()>120)
    db.session.add(event);db.session.flush()
    db.session.add(AttendanceAuditLog(device_id=device.id,entity_id=event.id,action='SCAN_ACCEPTED' if accepted else 'SCAN_REJECTED',details=message))
    return event,False


def attendance_dataset(start,end,personnel):
    ids=[person.id for person in personnel]
    sessions=db.session.scalars(select(AttendanceSession).where(AttendanceSession.personnel_id.in_(ids),AttendanceSession.work_date>=start,AttendanceSession.work_date<=end).options(selectinload(AttendanceSession.schedule)).order_by(AttendanceSession.time_in)).all()
    leaves=db.session.scalars(select(EmployeeLeave).where(EmployeeLeave.personnel_id.in_(ids),EmployeeLeave.status=='approved',EmployeeLeave.start_date<=end,EmployeeLeave.end_date>=start)).all()
    grouped={}
    for session in sessions: grouped.setdefault((session.personnel_id,session.work_date),[]).append(session)
    return {'sessions':grouped,'leaves':leaves}


def daily_rows(day,personnel,cache=None):
    now=datetime.now(timezone.utc);rows=[]
    for person in personnel:
        schedules=[s for s in person.schedules if scheduled(s,day)]
        sessions=cache['sessions'].get((person.id,day),[]) if cache is not None else db.session.scalars(select(AttendanceSession).where(AttendanceSession.personnel_id==person.id,AttendanceSession.work_date==day).order_by(AttendanceSession.time_in)).all()
        leave=next((v for v in cache['leaves'] if v.personnel_id==person.id and v.start_date<=day<=v.end_date),None) if cache is not None else db.session.scalar(select(EmployeeLeave).where(EmployeeLeave.personnel_id==person.id,EmployeeLeave.status=='approved',EmployeeLeave.start_date<=day,EmployeeLeave.end_date>=day))
        status='Off duty'
        if sessions: status='Clocked in' if any(not s.time_out for s in sessions) else ('Late' if any(s.late_minutes for s in sessions) else 'Present')
        elif leave: status='On leave'
        elif schedules: status='Absent' if all(now>bounds(s,day)[0]+timedelta(minutes=s.cutoff_minutes) for s in schedules) else 'Awaiting scan'
        undertime=overtime=early=0
        for schedule_id in {s.schedule_id for s in sessions}:
            group=[s for s in sessions if s.schedule_id==schedule_id]
            start,end=bounds(group[0].schedule,day)
            worked=sum(session_metrics(s)['worked_minutes'] for s in group)
            required=int((end-start).total_seconds()/60)
            if all(s.time_out for s in group):
                undertime+=max(0,required-worked)
                early+=max(0,int((end-max(utc(s.time_out) for s in group)).total_seconds()/60))
            if all(s.overtime_approved for s in group): overtime+=max(0,worked-required)
        rows.append({'person':person,'date':day,'sessions':sessions,'status':status,'scheduled':bool(schedules),'worked_minutes':sum(session_metrics(s)['worked_minutes'] for s in sessions),'late_minutes':sum(s.late_minutes for s in sessions),'overtime_minutes':overtime,'undertime_minutes':undertime,'early_minutes':early})
    return rows
