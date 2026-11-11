"""Inactive personnel can be reactivated explicitly in the combined form."""
from app.extensions import db
from app.models import PersonnelProfile,RFIDCard,AttendanceAuditLog,AttendanceSession
from test_system_integrity import system,login
from test_attendance_operations import roster
from test_rfid_account_links import capture_form
from test_rfid_registration import unregistered_person


def count(model):
    return db.session.scalar(db.select(db.func.count(model.id)))


def test_inactive_existing_account_personnel_can_reactivate_without_duplicate_profile(system,roster):
    from datetime import datetime,time,timezone
    from app.attendance.service import MANILA
    person,schedule,_,_,day=roster
    unregistered_person(person)
    person.active=False
    history=AttendanceSession(personnel_id=person.id,schedule_id=schedule.id,work_date=day,time_in=datetime.combine(day,time(8),MANILA).astimezone(timezone.utc),time_out=datetime.combine(day,time(17),MANILA).astimezone(timezone.utc))
    db.session.add(history);db.session.commit()
    original_id=person.id;original_user=person.user_id;history_id=history.id
    admin,form=capture_form(system,roster,'Test','Official')
    form.update(account_mode='existing',user_id=original_user)
    result=admin.post('/attendance/devices',data=form)
    assert result.status_code==200
    html=result.get_data(as_text=True)
    assert 'Reactivate this personnel record' in html
    assert 'data-personnel-active="no"' in html
    assert f'id="rfidCaptureId" value="{form["capture_id"]}"' in html
    assert 'disabled' not in html.split('id="rfidSaveButton"',1)[1].split('>',1)[0]
    db.session.refresh(person);assert not person.active
    assert count(RFIDCard)==0
    result=admin.post('/attendance/devices',data={**form,'reactivate_personnel':'yes','reactivate_personnel_id':str(original_id)})
    assert result.status_code==302
    db.session.refresh(person)
    assert person.active and person.id==original_id and person.user_id==original_user and person.user.is_active
    assert len(person.cards)==1 and len(person.schedules)==1
    assert count(PersonnelProfile)==1 and db.session.get(AttendanceSession,history_id).time_out is not None
    assert db.session.scalar(db.select(db.func.count(AttendanceAuditLog.id)).where(AttendanceAuditLog.action=='PERSONNEL_REACTIVATED'))==1
    assert admin.get('/attendance/registration/'+form['capture_id']).json['state']=='consumed'


def test_reactivation_requires_matching_record_and_rolls_back_on_validation_error(system,roster):
    person=roster[0];person.active=False;db.session.commit()
    unregistered_person(person)
    admin,form=capture_form(system,roster,'Test','Official')
    form.update(account_mode='existing',user_id=person.user_id,reactivate_personnel='yes')
    assert admin.post('/attendance/devices',data={**form,'reactivate_personnel_id':person.id+999}).status_code==200
    db.session.refresh(person);assert not person.active
    result=admin.post('/attendance/devices',data={**form,'reactivate_personnel_id':person.id,'email':'not-an-email'})
    assert result.status_code==200
    db.session.refresh(person);assert not person.active and count(RFIDCard)==0
    assert count(AttendanceAuditLog)==0
    assert admin.get('/attendance/registration/'+form['capture_id']).json['state']=='captured'


def test_reactivation_does_not_enable_a_disabled_login_account(system,roster):
    person=roster[0];person.active=False;person.user.is_active=False;db.session.commit()
    unregistered_person(person)
    admin,form=capture_form(system,roster,'Test','Official')
    result=admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':person.user_id,'reactivate_personnel':'yes','reactivate_personnel_id':person.id})
    assert result.status_code==200
    assert b'Select an active system account' in result.data
    db.session.refresh(person)
    assert not person.active and not person.user.is_active and count(RFIDCard)==0


def test_unlinked_inactive_person_also_uses_explicit_reactivation(system,roster):
    person=PersonnelProfile(employee_id='UNLINKED-INACTIVE',full_name='Unlinked Worker',personnel_type='Staff',position='Barangay Staff',active=False)
    db.session.add(person);db.session.commit()
    admin,form=capture_form(system,roster,'Unlinked','Worker')
    form['account_mode']='none'
    assert admin.post('/attendance/devices',data=form).status_code==200
    assert admin.post('/attendance/devices',data={**form,'reactivate_personnel':'yes','reactivate_personnel_id':person.id}).status_code==302
    db.session.refresh(person)
    assert person.active and person.user_id is None and len(person.cards)==1 and len(person.schedules)==1
