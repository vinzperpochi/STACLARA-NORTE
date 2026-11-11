"""Existing residents can complete details without bypassing review or file privacy."""
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from app.extensions import db
from app.models import User, Resident, ResidentCorrectionRequest
from test_system_integrity import system, login, image_bytes


def owner():
    return db.session.scalar(db.select(User).where(User.username=='resident-test'))


def details(**changes):
    data = dict(profile_details_present='1', nationality='Filipino', place_of_birth='Pila, Laguna',
        religion='Roman Catholic', educational_attainment='college', household_relationship='child',
        house_no='25', street_landmark='Sample Street', residency_duration='over_10',
        emergency_contact_name='Juan Santos', emergency_contact_relationship='Sibling',
        emergency_contact_number='09171234567', special_categories=['pwd'],
        reason='Kinukumpleto ko ang aking registration details.')
    data.update(changes)
    return data


def staff_body(**changes):
    data = details(first_name='Maria',last_name='Santos',birth_date='1990-01-01',sex='Female',
        civil_status='Single',voter_status='registered',address_line='Full original address',
        purok_id='',household_id='')
    data.update(changes)
    return data


def test_staff_edit_saves_all_fields_uploads_and_keeps_existing_files(system):
    account=owner(); resident=account.resident
    client=login(system,'staff-test')
    route=f'/official/residents/{resident.id}/edit'
    response=client.post(route,data=staff_body(profile_photo=(image_bytes(),'photo.png','image/png'),
        proof_of_residency=(image_bytes(),'proof.png','image/png'),philsys_card=(image_bytes(),'id.png','image/png')))
    assert response.status_code==302
    db.session.refresh(resident)
    assert resident.place_of_birth=='Pila, Laguna' and resident.educational_attainment=='college'
    assert resident.emergency_contact_number=='09171234567' and resident.special_categories==['pwd']
    assert resident.address_line=='Full original address'
    assert account.profile_photo_filename==resident.profile_photo_filename
    originals=(resident.profile_photo_filename,resident.proof_of_residency_filename,resident.philsys_card_filename)
    assert client.post(route,data=staff_body(religion='Christian')).status_code==302
    assert originals==(resident.profile_photo_filename,resident.proof_of_residency_filename,resident.philsys_card_filename)
    assert resident.religion=='Christian'
    for kind in ('proof','philsys'):
        assert client.get(f'/official/residents/{resident.id}/registration-files/{kind}').status_code==200
        assert login(system).get('/resident/registration-files/'+kind).status_code==200
        assert login(system,'other-test').get('/resident/registration-files/'+kind).status_code==404


def test_staff_create_populates_the_extended_record(system):
    response=login(system,'staff-test').post('/official/residents/new',data=staff_body(first_name='Lina'))
    assert response.status_code==302
    resident=db.session.scalar(db.select(Resident).where(Resident.first_name=='Lina'))
    assert resident.place_of_birth=='Pila, Laguna' and resident.house_no=='25'
    assert resident.nationality=='Filipino' and resident.special_categories==['pwd']


@pytest.mark.parametrize('change', [dict(educational_attainment='forged'),dict(special_categories=['forged']),
    dict(emergency_contact_number='invalid'),dict(emergency_contact_name=''),dict(special_categories=['senior'])])
def test_invalid_details_never_change_the_registry(system, change):
    resident=owner().resident
    response=login(system,'staff-test').post(f'/official/residents/{resident.id}/edit',data=staff_body(**change))
    assert response.status_code==200
    db.session.refresh(resident)
    assert resident.place_of_birth is None and resident.special_categories is None


def test_resident_fill_up_creates_pending_changes_then_staff_approves_typed_values(system):
    resident=owner().resident
    client=login(system)
    response=client.post('/resident/profile-details',data=details())
    assert response.status_code==302
    db.session.refresh(resident)
    assert resident.place_of_birth is None and resident.special_categories is None
    pending=db.session.scalars(db.select(ResidentCorrectionRequest).where(ResidentCorrectionRequest.resident_id==resident.id)).all()
    assert len(pending)==11 and all(item.status=='pending' for item in pending)
    assert client.post('/resident/profile-details',data=details()).status_code==302
    assert db.session.scalar(db.select(db.func.count()).select_from(ResidentCorrectionRequest))==11
    html=client.get('/resident/profile-details').get_data(as_text=True)
    assert 'value="Pila, Laguna"' in html and 'value="pwd" checked' in html
    # Categories are restored as JSON arrays, not saved as a string.
    staff=login(system,'staff-test')
    for item in pending:
        assert staff.post(f'/official/correction-requests/{item.id}/approve').status_code==302
    db.session.refresh(resident)
    assert resident.place_of_birth=='Pila, Laguna'
    assert resident.special_categories==['pwd'] and isinstance(resident.special_categories,list)
    assert resident.emergency_contact_number=='09171234567'


def test_resident_upload_failure_rolls_back_requests_and_new_images(system):
    resident=owner().resident
    root=Path(system.config['STORAGE_ROOT'])/'registration_documents'
    response=login(system).post('/resident/profile-details',data=details(
        proof_of_residency=(image_bytes(),'proof.png','image/png'),
        philsys_card=(BytesIO(b'forged'),'id.png','image/png')))
    assert response.status_code==200
    assert not db.session.scalar(db.select(ResidentCorrectionRequest))
    assert resident.proof_of_residency_filename is None and not list(root.glob('*'))


def test_resident_upload_replaces_only_owned_images_and_staff_form_rolls_back(system):
    resident=owner().resident; client=login(system)
    assert client.post('/resident/profile-details',data=details(proof_of_residency=(image_bytes(),'proof.png','image/png'))).status_code==302
    old=resident.proof_of_residency_filename
    root=Path(system.config['STORAGE_ROOT'])/'registration_documents'
    assert client.post('/resident/profile-details',data=details(proof_of_residency=(image_bytes(),'proof.png','image/png'))).status_code==302
    assert not (root/old).exists() and (root/resident.proof_of_residency_filename).is_file()
    assert login(system,'other-test').get('/resident/registration-files/proof').status_code==404
    before=set(root.iterdir())
    response=login(system,'staff-test').post(f'/official/residents/{resident.id}/edit',data=staff_body(
        proof_of_residency=(image_bytes(),'proof.png','image/png'),philsys_card=(BytesIO(b'forged'),'id.png','image/png')))
    assert response.status_code==200 and set(root.iterdir())==before
    db.session.refresh(resident)
    assert resident.place_of_birth is None


def test_correction_approval_converts_dates_and_blocks_unlisted_fields(system):
    resident=owner().resident
    for field,value in [('birth_date','1980-05-01'),('is_verified','true')]:
        item=ResidentCorrectionRequest(resident_id=resident.id,requested_by_id=owner().id,
            field_name=field,proposed_value=value,reason='Verified correction request',status='pending')
        db.session.add(item);db.session.commit()
        assert login(system,'staff-test').post(f'/official/correction-requests/{item.id}/approve').status_code==302
        db.session.refresh(item)
        assert item.status==('approved' if field=='birth_date' else 'pending')
    assert resident.birth_date==date(1980,5,1) and not resident.is_verified


def test_fill_up_owner_permissions_and_csrf(system):
    assert system.test_client().get('/resident/profile-details').status_code==302
    assert login(system,'staff-test').get('/resident/profile-details').status_code==403
    client=login(system)
    assert b'/resident/profile-details' in client.get('/workspace/profile').data
    system.config['WTF_CSRF_ENABLED']=True
    assert client.post('/resident/profile-details',data=details()).status_code==400


def test_legacy_staff_post_preserves_unsubmitted_registration_details(system):
    resident=owner().resident
    resident.place_of_birth='Existing birthplace'
    resident.nationality='Existing nationality'
    resident.special_categories=['pwd']
    db.session.commit()
    data=dict(first_name='Maria',last_name='Santos',voter_status='unknown',purok_id='',household_id='')
    assert login(system,'staff-test').post(f'/official/residents/{resident.id}/edit',data=data).status_code==302
    db.session.refresh(resident)
    assert resident.place_of_birth=='Existing birthplace'
    assert resident.nationality=='Existing nationality' and resident.special_categories==['pwd']


def test_resident_incomplete_emergency_contact_is_not_submitted(system):
    response=login(system).post('/resident/profile-details',data=details(emergency_contact_number=''))
    assert response.status_code==200 and b'Enter the emergency contact number.' in response.data
    assert not db.session.scalar(db.select(ResidentCorrectionRequest))
