"""Profile persistence, image processing, authorization and protected registry data."""
from datetime import date
from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image
from app.extensions import db
from app.models import User, Official, Resident, Purok, Household, AuditLog
from app.profile_management import profile_context
from test_system_integrity import system, login, image_bytes
from test_extended_registration import registration, body


def test_webp_registration_persists_linked_profile(registration):
    app, p = registration
    result=app.test_client().post('/auth/register',data=body(p,profile_photo=(image_bytes('WEBP'),'portrait.webp','image/webp')))
    assert result.status_code==200
    user=db.session.scalar(db.select(User).where(User.email=='extended@example.com'))
    assert user and user.profile_photo_filename.endswith('.webp')
    assert user.profile_photo_filename==user.resident.profile_photo_filename
    assert (Path(app.config['STORAGE_ROOT'])/'profile_photos'/user.profile_photo_filename).is_file()


def test_account_photo_endpoint_requires_directory_permission_or_ownership(system):
    staff=db.session.scalar(db.select(User).where(User.username=='staff-test'))
    login(system,'staff-test').post('/workspace/profile',data={'photo':(image_bytes(),'portrait.png','image/png')})
    url=f'/workspace/users/{staff.id}/photo'
    assert system.test_client().get(url).status_code==302
    assert login(system,'other-test').get(url).status_code==403
    own=login(system,'staff-test').get(url);assert own.status_code==200;own.close()
    admin=login(system,'admin-test').get(url);assert admin.status_code==200;admin.close()


@pytest.mark.parametrize('username',['resident-test','staff-test','admin-test'])
def test_role_profile_photo_webp_persistence_and_removal(system,username):
    client=login(system,username)
    response=client.get('/workspace/profile')
    assert response.status_code==200 and b'Profile completeness' in response.data
    assert b'Account security' in response.data and b'photoModal' in response.data
    assert client.post('/workspace/profile',data={'photo':(image_bytes('WEBP'),'portrait.webp','image/webp')}).status_code==302
    user=db.session.scalar(db.select(User).where(User.username==username));db.session.refresh(user)
    filename=user.profile_photo_filename;assert filename.endswith('.webp')
    assert (Path(system.config['STORAGE_ROOT'])/'profile_photos'/filename).is_file()
    if user.resident: assert user.resident.profile_photo_filename==filename
    client=login(system,username)
    photo=client.get('/workspace/profile-photo');assert photo.status_code==200 and 'no-store' in photo.headers['Cache-Control']
    photo.close()  # Release send_file's Windows file handle before deletion.
    assert b'workspace/profile-photo' in client.get('/workspace/profile').data
    assert client.post('/workspace/profile',data={'remove':'1'}).status_code==302
    assert not (Path(system.config['STORAGE_ROOT'])/'profile_photos'/filename).exists()
    assert client.get('/workspace/profile-photo').status_code==404


def test_contact_updates_persist_and_identity_cannot_be_changed(system):
    client=login(system)
    body=dict(emergency_contact_name='Ana Santos',emergency_contact_relationship='Sister',emergency_contact_number='09171234567')
    assert client.post('/workspace/profile/details',data=body).status_code==302
    user=db.session.scalar(db.select(User).where(User.username=='resident-test'));db.session.refresh(user.resident)
    assert user.resident.emergency_contact_name=='Ana Santos'
    assert b'Ana Santos' in login(system).get('/workspace/profile').data
    assert client.post('/workspace/profile/details',data=dict(body,first_name='Tampered')).status_code==400
    assert user.resident.first_name=='Maria'
    assert client.post('/workspace/profile/details',data=dict(body,emergency_contact_number='invalid')).status_code==400
    db.session.refresh(user.resident);assert user.resident.emergency_contact_number=='09171234567'
    assert db.session.scalar(db.select(AuditLog.id).where(AuditLog.action=='PROFILE_CONTACT_UPDATE'))
    assert login(system,'admin-test').post('/workspace/profile/details',data=body).status_code==400


def test_official_can_only_update_own_contact(system):
    staff=db.session.scalar(db.select(User).where(User.username=='staff-test'))
    staff.official=Official(full_name='Test Official',position='Secretary',term_start=date(2025,1,1),status='active');db.session.commit()
    client=login(system,'staff-test')
    assert b'Official details' in client.get('/workspace/profile').data
    assert client.post('/workspace/profile/details',data={'contact_number':'09171234567'}).status_code==302
    db.session.refresh(staff.official);assert staff.official.contact_number=='09171234567'
    assert client.post('/workspace/profile/details',data={'contact_number':'09171234567','position':'Captain'}).status_code==400
    assert staff.official.position=='Secretary'


def test_private_household_photo_access_and_unrelated_resident_denial(system):
    owner=db.session.scalar(db.select(User).where(User.username=='resident-test')).resident
    other=db.session.scalar(db.select(User).where(User.username=='other-test')).resident
    p=Purok(name='Purok 1');h=Household(household_number='HH-PHOTO',address_line='Main Street',purok=p);owner.household=h;db.session.add(h);db.session.commit()
    login(system).post('/workspace/profile',data={'photo':(image_bytes(),'photo.png','image/png')})
    url=f'/workspace/residents/{owner.id}/photo'
    assert system.test_client().get(url).status_code==302
    assert login(system,'other-test').get(url).status_code==403
    other.household=h;db.session.commit()
    assert login(system,'other-test').get(url).status_code==200
    assert login(system,'staff-test').get(url).status_code==200


def test_photo_crop_is_saved_and_invalid_crop_preserves_previous_image(system):
    data=BytesIO();Image.new('RGB',(160,80),'green').save(data,'PNG');data.seek(0)
    client=login(system)
    assert client.post('/workspace/profile',data={'photo':(data,'photo.png','image/png'),'crop_enabled':'1','crop_zoom':'2','crop_x':'0.8','crop_y':'0.5'}).status_code==302
    user=db.session.scalar(db.select(User).where(User.username=='resident-test'));db.session.refresh(user)
    path=Path(system.config['STORAGE_ROOT'])/'profile_photos'/user.profile_photo_filename
    with Image.open(path) as im: assert im.size==(40,40)
    old=user.profile_photo_filename
    result=client.post('/workspace/profile',data={'photo':(image_bytes(),'photo.png','image/png'),'crop_enabled':'1','crop_zoom':'nan','crop_x':'0.5','crop_y':'0.5'})
    assert b'Invalid photo crop' in result.data
    db.session.refresh(user);assert user.profile_photo_filename==old and path.exists()


def test_completeness_uses_saved_fields_only(system):
    user=db.session.scalar(db.select(User).where(User.username=='resident-test'))
    before=profile_context(user)['profile_completeness']
    user.resident.sex='Female';db.session.commit()
    assert profile_context(user)['profile_completeness']>before
    assert 'Profile photo' in profile_context(user)['profile_missing']


def test_profile_posts_require_csrf_when_enabled(system):
    client=login(system);system.config['WTF_CSRF_ENABLED']=True
    assert client.post('/workspace/profile/details',data={'emergency_contact_name':'Ana'}).status_code==400
    assert client.post('/workspace/profile',data={'remove':'1'}).status_code==400


def test_registration_and_document_templates_keep_correct_asset_boundaries(system):
    assert b'image/jpeg,image/png,image/webp' in system.test_client().get('/auth/register').data
    assert b'Remove selected photo' in system.test_client().get('/auth/register').data
    for layout in ['admin/_admin_base.html','official/_official_base.html','resident/_portal_base.html','layouts/auth_base.html','base.html']:
        source=system.jinja_loader.get_source(system.jinja_env,layout)[0]
        assert 'civic-premium.css' in source and 'bootstrap/bootstrap.min.css' in source
    assert 'civic-premium.css' not in system.jinja_loader.get_source(system.jinja_env,'documents/original/base.html')[0]
