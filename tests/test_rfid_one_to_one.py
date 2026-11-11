"""RFID ownership persists and cannot be duplicated through registration."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import PersonnelProfile,RFIDCard,User,AttendanceSession
from app.attendance.service import uid_hash
from test_system_integrity import system,login
from test_attendance_operations import roster
from test_rfid_account_links import capture_form,official_account


def test_registration_persists_after_redirect_and_database_readback(system,roster):
    account=official_account()
    admin,form=capture_form(system,roster)
    result=admin.post('/attendance/devices',data={**form,'account_mode':'existing','user_id':account.id})
    assert result.status_code==302 and 'registered=' in result.location
    person=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.user_id==account.id))
    person_id=person.id;account_id=account.id
    # Read the actual table rows, rather than relying on an ORM relationship cache.
    with db.engine.connect() as connection:
        saved=connection.execute(select(RFIDCard.__table__.c.personnel_id,PersonnelProfile.__table__.c.user_id).join(PersonnelProfile.__table__,RFIDCard.__table__.c.personnel_id==PersonnelProfile.__table__.c.id).where(PersonnelProfile.__table__.c.id==person_id)).one()
        assert tuple(saved)==(person_id,account_id)
    page=admin.get(result.location).get_data(as_text=True)
    assert 'Saved RFID assignment' in page and '11223344' in page and 'unlinked-official-test' in page
    again=admin.get('/attendance/devices').get_data(as_text=True)
    assert 'data-rfid-registered="yes"' in again and 'data-rfid-suffix="11223344"' in again


@pytest.mark.parametrize('mode',['existing','none'])
def test_second_registration_for_same_person_cannot_add_or_replace_card(system,roster,mode):
    person=roster[0];original=person.cards[0].uid_hash
    admin,form=capture_form(system,roster,'Test','Official')
    result=admin.post('/attendance/devices',data={**form,'account_mode':mode,'user_id':person.user_id})
    assert result.status_code==200 and b'already has an RFID registration' in result.data
    assert b'Registration was not saved' in result.data
    db.session.refresh(person)
    assert len(person.cards)==1 and person.cards[0].uid_hash==original
    assert person.cards[0].active and person.user_id is not None
    assert db.session.scalar(select(db.func.count(PersonnelProfile.id)))==1


def test_card_cannot_be_registered_for_another_person_even_after_revocation(system,roster):
    card=roster[0].cards[0];old_owner=card.personnel_id
    card.active=False;db.session.commit()
    admin=login(system,'admin-test')
    token=admin.post('/attendance/registration/start',json={}).json['capture_id']
    result=system.test_client().post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'AABBCCDD'})
    assert not result.json['success']
    assert admin.get('/attendance/registration/'+token).json['state']=='waiting'
    assert db.session.get(RFIDCard,card.id).personnel_id==old_owner


def test_database_rejects_second_active_card_and_second_profile_for_same_user(system,roster):
    person=roster[0];digest,suffix=uid_hash('11223344')
    with pytest.raises(IntegrityError):
        with db.session.begin_nested():
            db.session.add(RFIDCard(personnel_id=person.id,uid_hash=digest,uid_suffix=suffix,active=True));db.session.flush()
    with pytest.raises(IntegrityError):
        with db.session.begin_nested():
            db.session.add(PersonnelProfile(user_id=person.user_id,employee_id='DUPLICATE-USER',full_name='Different Name',position='Staff',personnel_type='Staff'));db.session.flush()
    assert db.session.scalar(select(db.func.count(RFIDCard.id)))==1


def test_explicit_replacement_preserves_old_uid_owner_and_enforces_one_active(system,roster):
    person=roster[0];old_id=person.cards[0].id
    admin=login(system,'admin-test')
    result=admin.post(f'/attendance/personnel/{person.id}',data={'action':'card','rfid_uid':'11223344'})
    assert result.status_code==302
    db.session.expire(person,['cards'])
    assert len(person.cards)==2 and sum(card.active for card in person.cards)==1
    old=db.session.get(RFIDCard,old_id)
    assert not old.active and old.revoked_at and old.personnel_id==person.id


def test_linking_account_keeps_existing_saved_card_and_prevents_account_reuse(system,roster):
    person=roster[0];person.user=None;db.session.commit()
    card_id=person.cards[0].id;old_count=db.session.scalar(select(db.func.count(RFIDCard.id)))
    account=official_account()
    admin=login(system,'admin-test')
    result=admin.post(f'/attendance/personnel/{person.id}',data={'action':'link_account','user_id':account.id})
    assert result.status_code==302
    db.session.refresh(person)
    assert person.user_id==account.id and person.cards[0].id==card_id
    assert db.session.scalar(select(db.func.count(RFIDCard.id)))==old_count
    other=PersonnelProfile(employee_id='OTHER-PERSON',full_name='Another Person',position='Staff',personnel_type='Staff')
    db.session.add(other);db.session.commit()
    admin.post(f'/attendance/personnel/{other.id}',data={'action':'link_account','user_id':account.id})
    db.session.refresh(other);assert other.user_id is None
    assert person.user_id==account.id
