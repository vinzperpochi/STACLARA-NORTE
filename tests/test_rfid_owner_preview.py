import pytest
from app.extensions import db
from app.models import AttendanceLog,AttendanceSession
from test_system_integrity import system,login
from test_attendance_operations import roster


@pytest.mark.parametrize('case',['no_schedule','inactive_person','unknown_card'])
def test_owner_can_be_displayed_without_bypassing_attendance_rules(system,roster,case):
    person,schedule,_,headers,_=roster
    uid='AABBCCDD'
    if case=='no_schedule': schedule.active=False
    if case=='inactive_person': person.active=False
    if case=='unknown_card': uid='11223344'
    person.full_name='Juan Dela Cruz';db.session.commit()
    response=system.test_client().post('/attendance/api/preview',headers=headers,json={'uid':uid})
    assert response.status_code==422 and not response.json['success']
    assert response.json['employee']==('Juan Dela Cruz' if case!='unknown_card' else None)
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==0
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0


def test_duplicate_registration_tap_reports_saved_owner_without_reassigning_card(system,roster):
    person,_,device,headers,_=roster
    person.full_name='Juan Dela Cruz';db.session.commit()
    admin=login(system,'admin-test')
    token=admin.post('/attendance/registration/start',json={}).json['capture_id']
    result=system.test_client().post('/attendance/api/registration-tap',headers=headers,json={'capture_id':token,'uid':'AABBCCDD'})
    assert not result.json['success'] and result.json['employee']=='Juan Dela Cruz'
    assert admin.get('/attendance/registration/'+token).json['state']=='waiting'
    assert len(person.cards)==1 and person.cards[0].personnel_id==person.id
