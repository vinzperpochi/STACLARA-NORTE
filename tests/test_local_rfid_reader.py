"""Credential-free scanner pairing is limited to an opted-in local test host."""
from datetime import datetime, timezone
from app.extensions import db
from app.models import AttendanceDevice, AttendanceLog, RFIDCard
from test_system_integrity import system, login
from test_rfid_registration import FIRST_SCHEDULE

HEADERS={'X-RFID-Local-Test':'1','X-RFID-Reader':'AABBCCDDEEFF','Accept':'application/json'}
LAN={'REMOTE_ADDR':'192.168.1.50'}


def test_automatic_pair_capture_and_registration(system):
    system.config['ATTENDANCE_LOCAL_TEST_MODE']=True
    admin=login(system,'admin-test');scanner=system.test_client()
    page=admin.get('/attendance/devices')
    assert page.status_code==200
    assert b'Reader setup and device health' not in page.data and b'Enroll reader' not in page.data
    # Merely polling cannot pair a scanner without an administrator's modal.
    assert scanner.post('/attendance/api/registration-mode',headers=HEADERS,environ_overrides=LAN).status_code==409
    result=admin.post('/attendance/registration/start',json={})
    assert result.status_code==200
    token=result.json['capture_id']
    assert db.session.scalar(db.select(db.func.count(AttendanceDevice.id)))==1
    result=scanner.post('/attendance/api/registration-mode',headers=HEADERS,environ_overrides=LAN)
    assert result.status_code==200 and result.json['capture_id']==token
    assert datetime.fromisoformat(result.json['time']).tzinfo is not None
    assert admin.get('/attendance/registration/'+token).json['ready']
    assert scanner.post('/attendance/api/registration-tap',headers=HEADERS,environ_overrides=LAN,json={'capture_id':token,'uid':'12345678'}).json['success']
    assert admin.post('/attendance/devices',data={**FIRST_SCHEDULE,'action':'register_card','first_name':'Local','last_name':'Official','barangay_role':'Barangay Captain','capture_id':token}).status_code==302
    assert db.session.scalar(db.select(db.func.count(RFIDCard.id)))==1
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==0
    # Pairing persists after the modal is consumed and DHCP changes the IP.
    result=scanner.post('/attendance/api/registration-mode',headers=HEADERS,environ_overrides={'REMOTE_ADDR':'192.168.1.51'})
    assert result.status_code==200 and result.json['capture_id'] is None
    different={**HEADERS,'X-RFID-Reader':'112233445566'}
    assert scanner.post('/attendance/api/registration-mode',headers=different,environ_overrides=LAN).status_code==403
    # A second modal reuses the same internal reader.
    assert admin.post('/attendance/registration/start',json={}).status_code==200
    assert db.session.scalar(db.select(db.func.count(AttendanceDevice.id)))==1


def test_local_mode_is_opt_in_and_rejects_public_or_proxied_requests(system):
    scanner=system.test_client()
    assert scanner.post('/attendance/api/registration-mode',headers=HEADERS,environ_overrides=LAN).status_code==403
    system.config['ATTENDANCE_LOCAL_TEST_MODE']=True
    admin=login(system,'admin-test');admin.post('/attendance/registration/start',json={})
    assert scanner.post('/attendance/api/registration-mode',headers=HEADERS,environ_overrides={'REMOTE_ADDR':'8.8.8.8'}).status_code==403
    assert scanner.post('/attendance/api/registration-mode',headers=HEADERS,environ_overrides=LAN,base_url='http://public.example').status_code==403
    assert scanner.post('/attendance/api/registration-mode',headers={**HEADERS,'X-Forwarded-For':'192.168.1.50'},environ_overrides=LAN).status_code==403
    assert scanner.post('/attendance/api/registration-mode',headers={**HEADERS,'X-RFID-Reader':'bad-id'},environ_overrides=LAN).status_code==400
    # Unmarked requests still require the existing Bearer credential.
    assert scanner.post('/attendance/api/registration-mode',environ_overrides=LAN).status_code==403
    system.config['ATTENDANCE_LOCAL_TEST_ALLOWED']=False
    assert scanner.post('/attendance/api/registration-mode',headers=HEADERS,environ_overrides=LAN).status_code==403


def test_production_refuses_local_scanner_mode(monkeypatch):
    import config
    import pytest
    monkeypatch.setattr(config.ProductionConfig,'ATTENDANCE_LOCAL_TEST_MODE',True)
    with pytest.raises(RuntimeError,match='disabled in production'):
        config.ProductionConfig.validate()
