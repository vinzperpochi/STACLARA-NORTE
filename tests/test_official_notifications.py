"""Resident activity reaches active reviewers without leaking account notifications."""
from app.extensions import db
from app.models import DocumentType, Notification, Role, User
from app.notifications import notify_officials
from test_system_integrity import system, login, image_bytes
from test_original_documents import setup_resident
from test_extended_registration import registration, body


def test_document_submission_and_upload_notify_officials_and_admin(system):
    resident,signatory=setup_resident()
    client=login(system)
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='BARANGAY_CLEARANCE'))
    response=client.post('/resident/documents/new',data={'document_type_id':doc.id,'request_stage':'initial','description':'Employment'})
    from app.models import Request
    item=db.session.scalar(db.select(Request).order_by(Request.id.desc()))
    assert response.status_code==302
    for username in ['staff-test','admin-test']:
        reviewer=login(system,username)
        payload=reviewer.get('/workspace/notifications').json['data']
        assert payload['unread']==1 and payload['items'][0]['title']=='New document request'
        assert item.request_number in payload['items'][0]['message']
    assert login(system,'other-test').get('/workspace/notifications').json['data']['unread']==0
    evidence=item.active_requirements[0]
    response=client.post(f'/resident/documents/{item.id}/requirements/{evidence.id}/upload',data={'requirement_file':(image_bytes(),'id.png','image/png')})
    assert response.status_code==302
    staff=login(system,'staff-test');payload=staff.get('/workspace/notifications').json['data']
    assert payload['unread']==2 and payload['items'][0]['title']=='Document requirement uploaded'
    notification_id=payload['items'][0]['id']
    assert login(system,'other-test').post('/workspace/notifications/read',data={'id':notification_id}).status_code==404
    assert staff.post('/workspace/notifications/read',data={'id':notification_id}).status_code==200
    assert staff.get('/workspace/notifications').json['data']['unread']==1
    assert login(system,'admin-test').get('/workspace/notifications').json['data']['unread']==2


def test_inactive_reviewers_excluded_and_multiple_roles_receive_one_notification(system):
    staff=db.session.scalar(db.select(User).where(User.username=='staff-test'))
    admin_role=db.session.scalar(db.select(Role).where(Role.name=='System Administrator'))
    staff.roles.append(admin_role)
    admin=db.session.scalar(db.select(User).where(User.username=='admin-test'));admin.is_active=False
    notify_officials('Review needed','Check the request list.');db.session.commit()
    assert db.session.scalar(db.select(db.func.count(Notification.id)).where(Notification.user_id==staff.id))==1
    assert db.session.scalar(db.select(db.func.count(Notification.id)).where(Notification.user_id==admin.id))==0


def test_account_menu_profile_link_removed_for_all_roles(system):
    for username,path in [('staff-test','/official/'),('admin-test','/admin/'),('resident-test','/resident/')]:
        page=login(system,username).get(path)
        assert page.status_code==200 and b'My profile &amp; account' not in page.data


def test_registration_notifies_reviewers_without_private_registration_values(registration):
    app,purok=registration
    response=app.test_client().post('/auth/register',data=body(purok))
    assert response.status_code==200
    payload=login(app,'staff-test').get('/workspace/notifications').json['data']
    assert payload['unread']==1 and payload['items'][0]['title']=='New resident registration'
    assert 'extended@example.com' not in payload['items'][0]['message']
