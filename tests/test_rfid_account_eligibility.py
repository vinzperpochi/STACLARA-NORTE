from html.parser import HTMLParser

import pytest

from app.extensions import db
from app.models import User, Resident, PersonnelProfile, RFIDCard, EmployeeSchedule
from test_system_integrity import system, login
from test_attendance_operations import roster
from test_rfid_account_links import capture_form, official_account


def options(html,registration=False):
    class Picker(HTMLParser):
        def __init__(self):
            super().__init__();self.active=False;self.ids=[]

        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='select':
                self.active=attrs.get('id')=='rfidUserAccount' if registration else attrs.get('name')=='user_id'
            if tag=='option' and self.active and attrs.get('value'):
                self.ids.append(int(attrs['value']))

        def handle_endtag(self,tag):
            if tag=='select': self.active=False

    picker=Picker();picker.feed(html)
    return set(picker.ids)


def count(model):
    return db.session.scalar(db.select(db.func.count(model.id)))


def test_resident_accounts_are_excluded_from_both_attendance_pickers(system,roster):
    eligible=official_account()
    resident_ids=set(db.session.scalars(db.select(User.id).where(User.username.in_(['resident-test','other-test']))).all())
    admin=login(system,'admin-test')
    registration=options(admin.get('/attendance/devices').get_data(as_text=True),registration=True)
    admin_id=db.session.scalar(db.select(User.id).where(User.username=='admin-test'))
    assert {eligible.id,roster[0].user_id,admin_id}<=registration
    assert not registration.intersection(resident_ids)
    person=roster[0];person.user=None;db.session.commit()
    linking=options(admin.get(f'/attendance/personnel/{person.id}').get_data(as_text=True))
    assert eligible.id in linking and not linking.intersection(resident_ids)


@pytest.mark.parametrize('username',['resident-test','other-test'])
def test_forged_resident_registration_cannot_create_personnel_schedule_or_card(system,roster,username):
    account=db.session.scalar(db.select(User).where(User.username==username))
    identity=(account.resident_id,account.is_active,account.status,tuple(role.id for role in account.roles))
    before={model:count(model) for model in [User,Resident,PersonnelProfile,RFIDCard,EmployeeSchedule]}
    admin,form=capture_form(system,roster)
    result=admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':account.id})
    assert result.status_code==200 and b'Resident accounts are not eligible' in result.data
    assert all(count(model)==total for model,total in before.items())
    assert db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.user_id==account.id)) is None
    db.session.refresh(account)
    assert identity==(account.resident_id,account.is_active,account.status,tuple(role.id for role in account.roles))
    assert admin.get('/attendance/registration/'+form['capture_id']).json['state']=='captured'


def test_forged_resident_link_cannot_reassign_an_existing_personnel_card(system,roster):
    person=roster[0];person.user=None;db.session.commit()
    card_id=person.cards[0].id
    account=db.session.scalar(db.select(User).where(User.username=='resident-test'))
    roles=tuple(role.id for role in account.roles)
    result=login(system,'admin-test').post(f'/attendance/personnel/{person.id}',data={'action':'link_account','user_id':account.id},follow_redirects=True)
    assert result.status_code==200 and b'Resident accounts are not eligible' in result.data
    db.session.refresh(person)
    assert person.user_id is None and person.cards[0].id==card_id
    assert tuple(role.id for role in account.roles)==roles


def test_inactive_official_role_cannot_be_used_to_enroll_an_account(system,roster):
    account=official_account()
    account.roles[0].status='inactive';db.session.commit()
    admin,form=capture_form(system,roster)
    assert account.id not in options(admin.get('/attendance/devices').get_data(as_text=True),registration=True)
    result=admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':account.id})
    assert result.status_code==200 and b'Select an active system account' in result.data
    assert count(PersonnelProfile)==1 and count(RFIDCard)==1


def test_super_admin_account_is_eligible_without_becoming_a_resident_or_changing_roles(system,roster):
    account=db.session.scalar(db.select(User).where(User.username=='admin-test'))
    original_roles=tuple(role.id for role in account.roles)
    admin,form=capture_form(system,roster)
    result=admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':account.id})
    assert result.status_code==302
    person=db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.user_id==account.id))
    assert len(person.cards)==1 and account.resident_id is None
    assert tuple(role.id for role in account.roles)==original_roles
