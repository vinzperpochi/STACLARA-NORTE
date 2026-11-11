"""New registration fields, real persistence and private evidence authorization."""
from datetime import date
from io import BytesIO
from pathlib import Path
import pytest
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import Resident, User, Purok, AuditLog
from test_system_integrity import system, login, image_bytes

@pytest.fixture
def registration(system, monkeypatch):
    system.config['REGISTRATION_REQUIRE_COMPLETE_PROFILE'] = True
    monkeypatch.setattr('app.auth.routes.send_verification_email', lambda **kwargs: None)
    p = Purok(name='Purok 30')
    db.session.add(p);db.session.commit()
    return system, p

def body(purok, **changes):
    data = dict(first_name='Lina', last_name='Santos', birth_date='1960-05-01', sex='Female', civil_status='Single', nationality='Filipino', email='extended@example.com', privacy_consent='y', terms_consent='y', voter_status='registered', purok_id=str(purok.id), place_of_birth='Pila, Laguna', religion='Roman Catholic', occupation='Retired', educational_attainment='college', household_relationship='head', house_no='25', street_landmark='Main Street', residency_duration='over_10', special_categories=['senior','registered_voter'], emergency_contact_name='Juan Santos', emergency_contact_relationship='Child', emergency_contact_number='09171234567', proof_of_residency=(image_bytes(),'residency.png','image/png'), philsys_card=(image_bytes('JPEG'),'card.jpg','image/jpeg'), profile_photo=(image_bytes(),'portrait.png','image/png'))
    data.update(changes)
    return data

def test_extended_registration_saves_profile_images_and_audit(registration):
    app, p = registration
    response = app.test_client().post('/auth/register',data=body(p))
    assert response.status_code == 200 and b'extended@example.com' in response.data
    user = db.session.scalar(db.select(User).where(User.email=='extended@example.com'))
    assert user is not None and user.status=='pending' and not user.is_active
    resident = user.resident
    assert resident.place_of_birth=='Pila, Laguna'
    assert resident.religion=='Roman Catholic'
    assert resident.educational_attainment=='college'
    assert resident.household_relationship=='head'
    assert resident.address_line=='25, Main Street'
    assert resident.residency_duration=='over_10'
    assert resident.special_categories==['senior','registered_voter']
    assert resident.emergency_contact_number=='09171234567'
    assert user.profile_photo_filename==resident.profile_photo_filename
    root=Path(app.config['STORAGE_ROOT'])
    assert (root/'registration_documents'/resident.proof_of_residency_filename).is_file()
    assert (root/'registration_documents'/resident.philsys_card_filename).is_file()
    assert (root/'profile_photos'/resident.profile_photo_filename).is_file()
    assert db.session.scalar(db.select(AuditLog).where(AuditLog.action=='REGISTER',AuditLog.entity_id==resident.id))

@pytest.mark.parametrize('field',['place_of_birth','house_no','street_landmark','residency_duration','purok_id','proof_of_residency'])
def test_registration_required_new_fields_are_enforced(registration,field):
    app,p=registration;data=body(p);data.pop(field)
    response=app.test_client().post('/auth/register',data=data)
    assert response.status_code==200
    assert not db.session.scalar(db.select(User).where(User.email=='extended@example.com'))

@pytest.mark.parametrize('field,value',[('educational_attainment','forged'),('household_relationship','forged'),('residency_duration','forged'),('special_categories',['unknown']),('religion','forged'),('emergency_contact_number','not-a-phone')])
def test_registration_invalid_values_do_not_save(registration,field,value):
    app,p=registration
    assert app.test_client().post('/auth/register',data=body(p,**{field:value})).status_code==200
    assert not db.session.scalar(db.select(User).where(User.email=='extended@example.com'))


def test_registration_forged_image_rolls_back_and_cleans_earlier_upload(registration):
    app,p=registration
    response=app.test_client().post('/auth/register',data=body(p,philsys_card=(BytesIO(b'forged'),'id.jpg','image/jpeg')))
    assert response.status_code==200 and b'valid JPEG or PNG' in response.data
    assert not db.session.scalar(db.select(User).where(User.email=='extended@example.com'))
    assert not list((Path(app.config['STORAGE_ROOT'])/'registration_documents').glob('*'))


def test_registration_private_evidence_staff_view_and_resident_ownership(registration):
    app,p=registration
    app.test_client().post('/auth/register',data=body(p))
    user=db.session.scalar(db.select(User).where(User.email=='extended@example.com'))
    user.status='active';user.is_active=True;user.set_password('Strong-test-password!');db.session.commit()
    mine=app.test_client()
    assert mine.post('/auth/login',data={'identifier':user.email,'password':'Strong-test-password!'}).status_code==302
    assert mine.get('/resident/registration-files/proof').status_code==200
    other=login(app,'other-test')
    assert other.get('/resident/registration-files/proof').status_code==404
    staff=login(app,'staff-test')
    assert staff.get(f'/official/residents/{user.resident_id}/registration-files/proof').status_code==200
    assert staff.get(f'/official/residents/{user.resident_id}/registration-files/philsys').status_code==200
    assert other.get(f'/official/residents/{user.resident_id}/registration-files/proof').status_code==403
    assert staff.get(f'/official/residents/{user.resident_id}').status_code==200
    assert b'Pila, Laguna' in staff.get(f'/official/residents/{user.resident_id}').data
    assert b'College' in mine.get('/resident/profile').data


def test_optional_fields_can_be_left_empty(registration):
    app,p=registration;data=body(p)
    for key in ['religion','occupation','educational_attainment','household_relationship','special_categories','emergency_contact_name','emergency_contact_relationship','emergency_contact_number','philsys_card','profile_photo']:data.pop(key,None)
    response=app.test_client().post('/auth/register',data=data)
    assert response.status_code==200
    user=db.session.scalar(db.select(User).where(User.email=='extended@example.com'))
    assert user is not None and user.resident.special_categories==[]


def test_registration_optional_fields_are_not_marked_required(registration):
    from html.parser import HTMLParser
    app,p=registration
    class Fields(HTMLParser):
        def __init__(self):super().__init__();self.fields={}
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag in ['input','select'] and 'id' in attrs:self.fields[attrs['id']]=attrs
    parser=Fields();parser.feed(app.test_client().get('/auth/register').get_data(as_text=True))
    assert 'data-required' in parser.fields['proof_of_residency']
    for key in ['religion','educational_attainment','profile_photo','philsys_card','emergency_contact_name']:
        assert 'data-required' not in parser.fields[key]
