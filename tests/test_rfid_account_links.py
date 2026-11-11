"""Optional account links preserve personnel identity and account permissions."""
import pytest
from app.extensions import db
from app.models import PersonnelProfile, RFIDCard, User, EmployeeSchedule, Role
from test_system_integrity import system, login
from test_attendance_operations import roster
from test_rfid_registration import start, FIRST_SCHEDULE


def official_account(username='unlinked-official-test'):
    account=User(username=username,email=username+'@example.com',is_active=True,status='active')
    account.set_password('Strong-test-password!')
    account.roles.append(db.session.scalar(db.select(Role).where(Role.name=='Barangay Official')))
    db.session.add(account);db.session.commit()
    return account


def capture_form(system,roster,first='Account',last='Worker'):
    admin=login(system,'admin-test');token=start(admin,roster[2])
    result=system.test_client().post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'11223344'})
    assert result.json['success']
    return admin,{**FIRST_SCHEDULE,'action':'register_card','capture_id':token,'first_name':first,'last_name':last,'barangay_role':'Barangay Staff'}


def test_existing_active_account_links_without_creating_user_or_granting_roles(system,roster):
    account=official_account()
    original_roles=[role.name for role in account.roles]
    original_count=db.session.scalar(db.select(db.func.count(User.id)))
    admin,form=capture_form(system,roster)
    result=admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':account.id})
    assert result.status_code==302
    person=db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.user_id==account.id))
    assert person.full_name=='Account Worker' and len(person.cards)==1 and len(person.schedules)==1
    assert db.session.scalar(db.select(db.func.count(User.id)))==original_count
    db.session.refresh(account)
    assert [role.name for role in account.roles]==original_roles
    assert b'System account: unlinked-official-test' in admin.get('/attendance/devices').data


def test_without_account_registers_barangay_worker_without_creating_login(system,roster):
    original_count=db.session.scalar(db.select(db.func.count(User.id)))
    admin,form=capture_form(system,roster,'Without','Account')
    # A stale hidden selection cannot override the explicit No account choice.
    result=admin.post('/attendance/devices',data={**form,'account_mode':'none','user_id':roster[0].user_id})
    assert result.status_code==302
    person=db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.full_name=='Without Account'))
    assert person.user_id is None and len(person.cards)==1 and len(person.schedules)==1
    assert db.session.scalar(db.select(db.func.count(User.id)))==original_count


def test_linking_existing_unlinked_person_keeps_profile_and_schedule(system,roster):
    account=official_account()
    person=PersonnelProfile(employee_id='EXIST-UNLINKED',full_name='Already Personnel',position='Barangay Staff',personnel_type='Staff')
    db.session.add(person);db.session.flush()
    schedule=EmployeeSchedule(personnel_id=person.id,name='Keep existing schedule',start_time=roster[1].start_time,end_time=roster[1].end_time,weekdays=[0,1],effective_from=roster[1].effective_from)
    db.session.add(schedule);db.session.commit();original_id=person.id
    admin,form=capture_form(system,roster,'Already','Personnel')
    assert admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':account.id}).status_code==302
    db.session.refresh(person)
    assert person.id==original_id and person.user_id==account.id
    assert len(person.schedules)==1 and person.schedules[0].name=='Keep existing schedule'
    assert db.session.scalar(db.select(db.func.count(PersonnelProfile.id)))==2


@pytest.mark.parametrize('mode,user_selector',[('existing','missing'),('existing','invalid'),('existing','inactive'),('invalid-mode','missing')])
def test_invalid_account_choices_do_not_save_partial_registration(system,roster,mode,user_selector):
    account=official_account()
    if user_selector=='inactive': account.is_active=False;db.session.commit()
    admin,form=capture_form(system,roster)
    value={'missing':'','invalid':'999999','inactive':str(account.id)}[user_selector]
    result=admin.post('/attendance/devices',data={**form,'account_mode':mode,'user_id':value})
    assert result.status_code==200
    assert db.session.scalar(db.select(db.func.count(PersonnelProfile.id)))==1
    assert db.session.scalar(db.select(db.func.count(RFIDCard.id)))==1
    assert admin.get('/attendance/registration/'+form['capture_id']).json['state']=='captured'


def test_existing_link_cannot_be_overwritten_or_silently_removed(system,roster):
    person=roster[0];original_user=person.user_id
    account=official_account()
    admin,form=capture_form(system,roster,'Test','Official')
    assert admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':account.id}).status_code==200
    assert admin.post('/attendance/devices',data={**form,'account_mode':'none'}).status_code==200
    db.session.refresh(person)
    assert person.user_id==original_user and len(person.cards)==1
