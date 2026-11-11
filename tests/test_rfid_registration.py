"""Registration reserves a reader and never creates attendance events."""
from unittest.mock import Mock
from urllib.error import URLError
import pytest
from app.attendance import capture
from app.extensions import db
from app.models import RFIDCard, AttendanceLog, AttendanceSession
from datetime import date
from test_system_integrity import system, login
from test_attendance_operations import roster
from test_hardware_bridge import bridge

FIRST_SCHEDULE={'start_time':'08:00','end_time':'17:00','effective_from':date.today().isoformat(),'weekdays':['0','1','2','3','4'],'grace_minutes':'15'}


def unregistered_person(person):
    """Use the shared attendance roster as a first-enrollment personnel fixture."""
    for card in list(person.cards): db.session.delete(card)
    db.session.commit();db.session.expire(person,['cards'])


def start(admin, device):
    response=admin.post('/attendance/registration/start',json={'device_id':device.id})
    assert response.status_code==200
    return response.json['capture_id']


def test_scan_and_register_links_card_without_attendance(system,roster):
    person,_,device,headers,_=roster
    unregistered_person(person)
    admin=login(system,'admin-test')
    page=admin.get('/attendance/devices')
    assert page.status_code==200 and b'Scan RFID Card/Tag' in page.data and b'name="rfid_uid"' not in page.data
    token=start(admin,device)
    assert not admin.get('/attendance/registration/'+token).json['ready']
    hardware=system.test_client()
    assert hardware.post('/attendance/api/registration-mode',headers=headers).json['capture_id']==token
    assert admin.get('/attendance/registration/'+token).json['ready']
    assert hardware.post('/attendance/api/registration-tap',headers=headers,json={'capture_id':token,'uid':'11223344'}).json['success']
    status=admin.get('/attendance/registration/'+token).json
    assert status['state']=='captured' and status['suffix']=='11223344' and 'digest' not in status
    result=admin.post('/attendance/devices',data={'action':'register_card','account_mode':'existing','user_id':person.user_id,'first_name':'Test','last_name':'Official','barangay_role':'Barangay Secretary','capture_id':token})
    assert result.status_code==302, result.get_data(as_text=True)[-5000:]
    db.session.refresh(person)
    assert person.full_name=='Test Official' and person.position=='Barangay Secretary'
    assert db.session.scalar(db.select(db.func.count(RFIDCard.id)))==1
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==0
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0
    assert admin.get('/attendance/registration/'+token).json['state']=='consumed'
    # The same captured token cannot register a second card.
    assert admin.post('/attendance/devices',data={'action':'register_card','personnel_id':person.id,'capture_id':token}).status_code==200


def test_duplicate_card_keeps_waiting_for_another_tap(system,roster):
    admin=login(system,'admin-test');token=start(admin,roster[2]);hardware=system.test_client()
    # An outdated bridge's live attendance submission is blocked too.
    assert hardware.post('/attendance/api/scan',headers=roster[3],json={'event_id':'legacy-live-tap','uid':'AABBCCDD'}).status_code==409
    response=hardware.post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'AABBCCDD'})
    assert not response.json['success']
    status=admin.get('/attendance/registration/'+token).json
    assert status['state']=='waiting' and 'already' in status['message']
    assert hardware.post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'22334455'}).json['success']
    assert admin.get('/attendance/registration/'+token).json['state']=='captured'
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==0


def test_cancel_expiry_ownership_and_reader_lock(system,roster,monkeypatch):
    admin=login(system,'admin-test');token=start(admin,roster[2])
    assert admin.post('/attendance/registration/start',json={'device_id':roster[2].id}).status_code==409
    with pytest.raises(ValueError): capture.get(token,999999)
    with pytest.raises(ValueError): capture.receive(token,999999,'digest','suffix')
    assert admin.post('/attendance/registration/'+token+'/cancel').status_code==200
    assert system.test_client().post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'11223344'}).status_code==400
    token=start(admin,roster[2]);now=capture.time.time()
    monkeypatch.setattr(capture.time,'time',lambda:now+61)
    assert admin.get('/attendance/registration/'+token).json['state']=='expired'
    assert system.test_client().post('/attendance/api/registration-mode',headers=roster[3]).json['capture_id'] is None


def test_capture_requires_admin_csrf_and_device_credentials(system,roster):
    staff=login(system,'staff-test')
    assert staff.post('/attendance/registration/start',json={'device_id':roster[2].id}).status_code==403
    assert system.test_client().post('/attendance/api/registration-mode').status_code==401
    admin=login(system,'admin-test');system.config['WTF_CSRF_ENABLED']=True
    assert admin.post('/attendance/registration/start',json={'device_id':roster[2].id}).status_code==400
    system.config['WTF_CSRF_ENABLED']=False


def test_registration_bridge_never_falls_through_to_attendance_on_failure(monkeypatch):
    module=bridge();device=Mock()
    def offline(*args): raise URLError('offline')
    monkeypatch.setattr(module,'registration_request',offline)
    assert module.route_registration_tap('server','secret','capture-token','11223344',device)
    assert b'registration offline' in device.write.call_args.args[0]
    assert not module.route_registration_tap('server','secret',None,'11223344',device)


def test_no_dropdowns_new_person_and_correct_navigation(system,roster):
    from app.models import PersonnelProfile
    import re
    admin=login(system,'admin-test')
    page=admin.get('/attendance/devices').get_data(as_text=True)
    assert 'name="personnel_id"' not in page and 'id="rfidReader"' not in page
    assert re.search(r'<a[^>]*href="/attendance/devices"[^>]*aria-current="page"',page)
    assert not re.search(r'<a[^>]*href="/attendance/"[^>]*aria-current="page"',page)
    token=admin.post('/attendance/registration/start',json={}).json['capture_id']
    system.test_client().post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'10203040'})
    result=admin.post('/attendance/devices',data={**FIRST_SCHEDULE,'action':'register_card','first_name':'New','last_name':'Tanod','barangay_role':'Barangay Tanod','capture_id':token})
    assert result.status_code==302, result.get_data(as_text=True)[-5000:]
    person=db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.full_name=='New Tanod'))
    assert person and person.user_id is None and person.position=='Barangay Tanod'
    assert len(person.cards)==1 and person.cards[0].uid_suffix=='10203040'
    assert len(person.schedules)==1
    assert b'New Tanod' in admin.get('/attendance/devices').data
    assert admin.get(f'/attendance/personnel/{person.id}/photo').status_code==200
    # No missing-user crash when a registered person has no web account yet.
    with capture.connection() as store:
        store.execute('DELETE FROM captures')
    from datetime import time
    person.schedules[0].start_time=time(0);person.schedules[0].end_time=time(23,59)
    person.schedules[0].weekdays=list(range(7));db.session.commit()
    response=system.test_client().post('/attendance/api/scan',headers=roster[3],json={'uid':'10203040','event_id':'unlinked-test'})
    assert response.status_code==200 and response.json['action']=='IN'


def test_single_reader_missing_and_multiple_readers(system,roster):
    from app.models import AttendanceDevice
    admin=login(system,'admin-test');device=roster[2]
    device.active=False;db.session.commit()
    assert admin.post('/attendance/registration/start',json={}).status_code==409
    device.active=True
    db.session.add(AttendanceDevice(name='extra reader',credential_hash='0'*64))
    db.session.commit()
    assert admin.post('/attendance/registration/start',json={}).status_code==409


def test_wifi_preview_is_read_only_and_final_action_is_revalidated(system,roster):
    from datetime import datetime, time, timedelta, timezone
    from app.models import AttendanceSession
    from app.attendance.service import MANILA
    person,schedule,device,headers,_=roster
    schedule.start_time=time(0);schedule.end_time=time(23,59);schedule.max_sessions=10
    db.session.commit()
    hardware=system.test_client()
    response=hardware.post('/attendance/api/preview',headers=headers,json={'uid':'AABBCCDD'})
    assert response.status_code==200 and response.json['action']=='IN'
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==0
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0
    now=datetime.now(timezone.utc)
    opened=AttendanceSession(personnel_id=person.id,schedule_id=schedule.id,work_date=now.astimezone(MANILA).date(),time_in=now-timedelta(minutes=2))
    db.session.add(opened);db.session.commit()
    assert hardware.post('/attendance/api/preview',headers=headers,json={'uid':'AABBCCDD'}).json['action']=='OUT'
    response=hardware.post('/attendance/api/scan',headers=headers,json={'uid':'AABBCCDD','event_id':'explicit-in-check','action':'IN'})
    assert response.status_code==422 and 'Already clocked in' in response.json['message']
    db.session.refresh(opened);assert opened.time_out is None
    device.require_pin=True;db.session.commit()
    assert hardware.post('/attendance/api/preview',headers=headers,json={'uid':'AABBCCDD'}).status_code==422
    assert hardware.post('/attendance/api/preview',json={'uid':'AABBCCDD'}).status_code==401
