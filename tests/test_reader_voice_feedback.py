from datetime import datetime, time, timedelta
import pytest
from app.extensions import db
from app.models import AttendanceSession, AttendanceLog, EmployeeLeave
from app.attendance.service import MANILA
from test_system_integrity import system, login
from test_attendance_operations import roster, scan_at


@pytest.mark.parametrize('case,expected', [
    ('unknown', 'UNKNOWN_CARD'), ('inactive', 'INACTIVE_ACCOUNT'),
    ('no_schedule', 'NO_SCHEDULE'), ('not_duty', 'NOT_DUTY_DAY'),
    ('early', 'TOO_EARLY'), ('outside', 'OUTSIDE_SCHEDULE'),
    ('old_session', 'REVIEW_REQUIRED'), ('leave', 'ON_LEAVE'),
    ('limit', 'SESSION_LIMIT'),
])
def test_rejected_scan_explains_existing_rule_without_success_voice(system, roster, case, expected):
    person,schedule,device,headers,day=roster
    at=datetime.combine(day,time(8),MANILA)
    uid='AABBCCDD'
    if case=='unknown': uid='11223344'
    elif case=='inactive': person.active=False
    elif case=='no_schedule': schedule.active=False
    elif case=='not_duty': schedule.weekdays=[(day.weekday()+1)%7]
    elif case=='early': at=at.replace(hour=4)
    elif case=='outside': at=at.replace(hour=22)
    elif case=='old_session':
        db.session.add(AttendanceSession(personnel_id=person.id,schedule_id=schedule.id,
            work_date=day-timedelta(days=2),time_in=at-timedelta(days=2)))
    elif case=='leave':
        db.session.add(EmployeeLeave(personnel_id=person.id,start_date=day,end_date=day,status='approved',reason='Test'))
    elif case=='limit':
        schedule.max_sessions=1
        db.session.add(AttendanceSession(personnel_id=person.id,schedule_id=schedule.id,
            work_date=day,time_in=at-timedelta(hours=1),time_out=at-timedelta(minutes=30)))
    db.session.commit()
    before=db.session.scalar(db.select(db.func.count(AttendanceSession.id)))
    response=scan_at(system,roster,at,'voice-reject-01',uid=uid)
    assert response.status_code==422
    assert response.json['success'] is False and response.json['voice_code']==expected
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==before


def test_voice_codes_preserve_multiple_sessions_replays_and_rapid_tap_rules(system, roster):
    day=roster[4]
    for index,hour in enumerate([8,12,13,17]):
        at=datetime.combine(day,time(hour),MANILA)
        event=f'voice-session-{index}'
        result=scan_at(system,roster,at,event)
        assert result.status_code==200
        assert result.json['voice_code']==('TIME_IN_VOICE' if index%2==0 else 'TIME_OUT_VOICE')
        replay=scan_at(system,roster,at,event)
        assert replay.json['replayed'] and replay.json['voice_code']==result.json['voice_code']
        if index==0:
            repeated=scan_at(system,roster,at+timedelta(seconds=10),'voice-rapid-01')
            assert repeated.status_code==422 and repeated.json['voice_code']=='REPEAT_TAP'
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==2


def test_registration_capture_voice_does_not_claim_saved_registration(system, roster):
    admin=login(system,'admin-test')
    token=admin.post('/attendance/registration/start',json={}).json['capture_id']
    reader=system.test_client()
    duplicate=reader.post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'AABBCCDD'})
    assert duplicate.json['voice_code']=='DUPLICATE_CARD' and not duplicate.json['success']
    result=reader.post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'11223344'})
    assert result.json['success'] and result.json['voice_code']=='CAPTURED'
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==0


def test_preview_and_auth_codes_do_not_create_attendance(system, roster):
    reader=system.test_client()
    result=reader.post('/attendance/api/preview',headers=roster[3],json={'uid':'11223344'})
    assert result.status_code==422 and result.json['voice_code']=='UNKNOWN_CARD'
    denied=reader.post('/attendance/api/registration-mode',headers={'Accept':'application/json'},json={})
    assert denied.status_code==401 and denied.json['voice_code']=='READER_SETUP'
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==0
