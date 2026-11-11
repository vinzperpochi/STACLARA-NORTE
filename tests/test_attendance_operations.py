from datetime import datetime, date, time, timedelta, timezone
from hashlib import sha256
import pytest
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models import User, PersonnelProfile, RFIDCard, EmployeeSchedule, AttendanceDevice, AttendanceSession, AttendanceLog, EmployeeLeave
from app.attendance.service import uid_hash, MANILA, daily_rows, session_metrics
from test_system_integrity import system, login, image_bytes


@pytest.fixture
def roster(system):
    user=db.session.scalar(db.select(User).where(User.username=='staff-test'))
    person=PersonnelProfile(user_id=user.id,employee_id='EMP-TEST',full_name='Test Official',photo_filename='test.png',position='Secretary',personnel_type='Official',department='Administration',mobile='09171234567',email=user.email,employment_status='Regular')
    db.session.add(person);db.session.flush()
    digest,suffix=uid_hash('AABBCCDD');db.session.add(RFIDCard(personnel_id=person.id,uid_hash=digest,uid_suffix=suffix))
    yesterday=datetime.now(MANILA).date()-timedelta(days=2)
    schedule=EmployeeSchedule(personnel_id=person.id,name='Day shift',start_time=time(8),end_time=time(17),weekdays=list(range(7)),effective_from=yesterday-timedelta(days=2),grace_minutes=15,cutoff_minutes=120,minimum_session_minutes=1,max_sessions=2)
    device=AttendanceDevice(name='Test reader',credential_hash=sha256(b'test-secret').hexdigest())
    db.session.add_all([schedule,device]);db.session.commit();db.session.expire(person,['schedules'])
    headers={'Authorization':f'Bearer {device.id}:test-secret'}
    return person,schedule,device,headers,yesterday


def scan_at(system,roster,at,event,uid='AABBCCDD',**extra):
    return system.test_client().post('/attendance/api/scan',json=dict(event_id=event,uid=uid,occurred_at=at.isoformat(),**extra),headers=roster[3])


def test_authenticated_clock_in_out_replay_and_rapid_duplicate(system,roster):
    person,schedule,device,headers,day=roster;start=datetime.combine(day,time(8),MANILA)
    response=scan_at(system,roster,start,'scan0001');assert response.status_code==200 and response.json['action']=='IN'
    replay=scan_at(system,roster,start,'scan0001');assert replay.json['replayed'] and db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==1
    repeat=scan_at(system,roster,start+timedelta(seconds=10),'scan0002');assert repeat.status_code==422
    result=scan_at(system,roster,start+timedelta(hours=9),'scan0003');assert result.json['action']=='OUT'
    session=db.session.scalar(db.select(AttendanceSession));assert session_metrics(session)['worked_minutes']==540 and session.late_minutes==0
    assert len(db.session.scalars(db.select(AttendanceLog)).all())==3


def test_unknown_revoked_inactive_card_and_missing_device_auth(system,roster):
    person,schedule,device,headers,day=roster;start=datetime.combine(day,time(8),MANILA)
    assert system.test_client().post('/attendance/api/scan',json={'uid':'AABBCCDD'}).status_code==401
    assert scan_at(system,roster,start,'unknown01',uid='11223344').status_code==422
    card=db.session.scalar(db.select(RFIDCard));card.active=False;db.session.commit()
    assert scan_at(system,roster,start,'revoked01').status_code==422
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0
    device.active=False;db.session.commit()
    assert scan_at(system,roster,start,'device001').status_code==401


def test_late_and_overnight_computation(system,roster):
    person,schedule,device,headers,day=roster
    schedule.start_time=time(22);schedule.end_time=time(6);db.session.commit()
    start=datetime.combine(day,time(22,45),MANILA)
    assert scan_at(system,roster,start,'night001').json['action']=='IN'
    finish=datetime.combine(day+timedelta(days=1),time(6),MANILA)
    assert scan_at(system,roster,finish,'night002').json['action']=='OUT'
    session=db.session.scalar(db.select(AttendanceSession));assert session.work_date==day and session.late_minutes==30
    metrics=session_metrics(session);assert metrics['worked_minutes']==435 and metrics['undertime_minutes']==45


def test_multiple_sessions_do_not_double_count_undertime(system,roster):
    day=roster[4]
    for number,hour in enumerate([8,12,13,17]):
        assert scan_at(system,roster,datetime.combine(day,time(hour),MANILA),f'session{number}').status_code==200
    row=daily_rows(day,[roster[0]])[0]
    assert row['worked_minutes']==480 and row['undertime_minutes']==60 and row['early_minutes']==0


def test_absence_cutoff_and_approved_leave(system,roster):
    person,schedule,device,headers,day=roster
    today=datetime.now(MANILA).date();schedule.start_time=time(23,50);schedule.end_time=time(6);db.session.commit()
    assert daily_rows(today,[person])[0]['status']=='Awaiting scan'
    assert daily_rows(day,[person])[0]['status']=='Absent'
    db.session.add(EmployeeLeave(personnel_id=person.id,start_date=day,end_date=today,status='approved',reason='Approved leave'));db.session.commit()
    assert daily_rows(today,[person])[0]['status']=='On leave'
    assert scan_at(system,roster,datetime.combine(day,time(23,50),MANILA),'leave001').status_code==422


def test_stronger_pin_and_transport_enforced(system,roster):
    person,schedule,device,headers,day=roster;device.require_pin=True;person.pin_hash=generate_password_hash('123456');db.session.commit()
    start=datetime.combine(day,time(8),MANILA)
    assert scan_at(system,roster,start,'pin00001').status_code==422
    assert scan_at(system,roster,start,'pin00002',pin='123456').status_code==200
    assert system.test_client().post('/attendance/api/heartbeat',headers=headers,environ_overrides={'REMOTE_ADDR':'192.0.2.2'}).status_code==403
    assert system.test_client().post('/attendance/api/heartbeat',headers=headers,base_url='https://localhost').status_code==200


def test_staff_own_history_export_and_admin_authorization(system,roster):
    staff=login(system,'staff-test');resident=login(system)
    assert resident.get('/attendance/').status_code==403
    assert staff.get('/attendance/personnel').status_code==403
    assert staff.get('/attendance/devices').status_code==403
    assert staff.get('/attendance/').status_code==200
    for kind,signature in [('csv',b'\xef\xbb\xbf'),('xlsx',b'PK'),('pdf',b'%PDF')]:
        response=staff.get('/attendance/reports?format='+kind+'&start_date='+str(roster[4]))
        assert response.status_code==200 and response.data.startswith(signature)
        response.close()
    admin=login(system,'admin-test')
    for path in ['/attendance/','/attendance/devices',f'/attendance/personnel/{roster[0].id}']:
        assert admin.get(path).status_code==200
    legacy=admin.get('/attendance/personnel')
    assert legacy.status_code==302 and legacy.location.endswith('/attendance/devices')
    assert admin.get('/attendance/personnel',follow_redirects=True).status_code==200
    csrf=system.config['WTF_CSRF_ENABLED'];system.config['WTF_CSRF_ENABLED']=True
    assert admin.post('/attendance/devices',data={'name':'x','hardware':'Arduino Uno'}).status_code==400
    system.config['WTF_CSRF_ENABLED']=csrf


def test_old_personnel_form_redirects_to_combined_registration(system):
    user=db.session.scalar(db.select(User).where(User.username=='staff-test'))
    response=login(system,'admin-test').post('/attendance/personnel',data={'user_id':user.id,'employee_id':'EMP-002','full_name':'Registered Official','position':'Tanod','department':'Peace & Order','mobile':'09171234567','email':'staff@example.com','employment_status':'Regular','personnel_type':'Official','rfid_uid':'12345678','start_time':'08:00','end_time':'17:00','weekdays':['0','1','2','3','4'],'effective_from':date.today().isoformat(),'photo':(image_bytes(),'portrait.png','image/png')})
    assert response.status_code==303 and response.location.endswith('/attendance/devices')
    assert db.session.scalar(db.select(PersonnelProfile)) is None
    assert db.session.get(User,user.id).username=='staff-test'
