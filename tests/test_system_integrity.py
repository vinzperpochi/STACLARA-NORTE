"""End-to-end regressions for integrity, authorization and private workflows."""
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import pytest
from PIL import Image
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage
from app import create_app
from app.extensions import db
from app.models import AuditLog, BlotterCase, BlotterCaseEvent, DocumentType, DocumentRequirement, Event, Notification, Purok, Request, Resident, Role, User, UserSession
from app.image_uploads import save_image


@pytest.fixture
def system():
    from pathlib import Path
    from uuid import uuid4
    tmp_path = Path(__file__).resolve().parents[1] / ".test-storage" / uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = create_app('testing')
    app.config.update(STORAGE_ROOT=str(tmp_path), SYSTEM_TIMEZONE='Asia/Manila')
    # The outer fixture context otherwise shares Flask-Login's g cache between clients.
    from flask import g
    def clear_login_cache():
        g.pop('_login_user', None)
    app.before_request_funcs[None].insert(0, clear_login_cache)
    with app.app_context():
        db.create_all()
        for username, role in [('admin-test', 'System Administrator'), ('staff-test', 'Barangay Official'), ('resident-test', 'Resident'), ('other-test', 'Resident')]:
            resident = Resident(first_name='Maria', last_name=username, birth_date=date(1990, 1, 1), status='active') if role == 'Resident' else None
            user = User(username=username, email=f'{username}@example.com', resident=resident, status='active', is_active=True, email_verified_at=datetime.now(timezone.utc))
            user.roles.append(Role(name=role)) if not db.session.scalar(db.select(Role).where(Role.name == role)) else user.roles.append(db.session.scalar(db.select(Role).where(Role.name == role)))
            user.set_password('Strong-test-password!')
            db.session.add(user)
            db.session.flush()
        db.session.commit()
        yield app
        db.session.remove()
        db.engine.dispose()


def login(app, username='resident-test'):
    client = app.test_client()
    response = client.post('/auth/login', data={'role': {'admin-test':'captain','staff-test':'staff'}.get(username, 'resident'), 'identifier': username, 'password': 'Strong-test-password!'})
    assert response.status_code == 302
    return client


def image_bytes(format='PNG'):
    data = BytesIO()
    Image.new('RGB', (10, 10), 'green').save(data, format)
    data.seek(0)
    return data


@pytest.mark.parametrize('variant', ['purok 1', ' PUROK   1 ', 'Purok 01', 'Purok #1'])
def test_purok_identity_and_form_duplicates(system, variant):
    client = login(system, 'admin-test')
    assert client.post('/admin/puroks', data={'name': 'Purok 1'}).status_code == 302
    response = client.post('/admin/puroks', data={'name': variant})
    assert response.status_code == 200
    assert b'already exists' in response.data
    assert db.session.scalar(db.select(db.func.count(Purok.id))) == 1


def test_purok_database_uniqueness_edit_and_archive(system):
    p = Purok(name='Purok 2')
    db.session.add(p); db.session.commit()
    db.session.add(Purok(name=' PUROK  02 '))
    with pytest.raises(IntegrityError): db.session.commit()
    db.session.rollback()
    client = login(system, 'admin-test')
    assert client.post(f'/admin/puroks/{p.id}/edit', data={'name': 'Purok 3', 'description': 'Updated'}).status_code == 302
    db.session.refresh(p); assert p.name == 'Purok 3'
    assert client.post(f'/admin/puroks/{p.id}/archive').status_code == 302
    db.session.refresh(p); assert p.status == 'inactive'
    assert login(system, 'staff-test').post('/admin/puroks', data={'name': 'Purok 9'}).status_code == 403


@pytest.mark.parametrize('ext,mime,content', [('svg','image/svg+xml',b'<svg/>'),('webp','image/webp',b'RIFF'),('gif','image/gif',b'GIF89a'),('pdf','application/pdf',b'%PDF'),('jpg','image/jpeg',b'not an image'),('png','image/jpeg',b'not an image')])
def test_image_rejects_unsupported_and_forged_files(system, ext, mime, content):
    with pytest.raises(ValueError):
        save_image(FileStorage(stream=BytesIO(content), filename='file.'+ext, content_type=mime), 'profile_photos')


@pytest.mark.parametrize('format,ext,mime', [('PNG','png','image/png'),('JPEG','jpg','image/jpeg')])
def test_image_upload_preview_replace_remove(system, format, ext, mime):
    client = login(system)
    assert client.post('/workspace/profile', data={'photo': (image_bytes(format), 'photo.'+ext, mime)}).status_code == 302
    user = db.session.scalar(db.select(User).where(User.username == 'resident-test'))
    db.session.refresh(user); assert user.profile_photo_filename
    assert client.get('/workspace/profile-photo').status_code == 200
    assert b'Selected image preview' in client.get('/workspace/profile').data
    assert login(system, 'other-test').get('/workspace/profile-photo').status_code == 404
    assert client.post('/workspace/profile', data={'photo': (image_bytes(format), 'new.'+ext, mime)}).status_code == 302
    assert client.post('/workspace/profile', data={'remove': '1'}).status_code == 302
    assert client.get('/workspace/profile-photo').status_code == 404


def test_image_size_limit(system):
    with pytest.raises(ValueError, match='5 MB'):
        save_image(FileStorage(stream=BytesIO(b'x' * (5*1024*1024+1)), filename='large.jpg', content_type='image/jpeg'), 'profile_photos')


def requirement_fixture():
    user = db.session.scalar(db.select(User).where(User.username == 'resident-test'))
    dt = DocumentType(name='Barangay Clearance', code='SCN-CLR', template_code='SCN-CLR', base_fee=0)
    item = Request(request_number='REQ-test', resident_id=user.resident_id, document_type=dt, service_type='Certificate', status='PENDING')
    req = DocumentRequirement(request=item, requirement_name='Valid government-issued ID', status='pending')
    db.session.add(req); db.session.commit()
    return item, req


def test_private_id_upload_view_replace_remove_and_ownership(system):
    item, req = requirement_fixture()
    client = login(system)
    url = f'/resident/documents/{item.id}/requirements/{req.id}'
    assert client.post(url+'/upload', data={'requirement_file': (image_bytes(), 'id.png', 'image/png')}).status_code == 302
    assert client.get(url+'/view').status_code == 200
    assert login(system, 'other-test').get(url+'/view').status_code == 404
    assert login(system, 'other-test').post(url+'/remove').status_code == 404
    assert client.post(url+'/upload', data={'requirement_file': (image_bytes('JPEG'), 'id.jpg', 'image/jpeg')}).status_code == 302
    assert b'View uploaded requirement' in client.get(f'/resident/documents/{item.id}').data
    assert client.post(url+'/remove').status_code == 302
    assert client.get(url+'/view').status_code == 404
    assert db.session.scalar(db.select(db.func.count(AuditLog.id)).where(AuditLog.action == 'DOCUMENT_REMOVE')) == 1


def test_id_processing_lock_and_pdf_rejection(system):
    item, req = requirement_fixture()
    client = login(system); url = f'/resident/documents/{item.id}/requirements/{req.id}'
    client.post(url+'/upload', data={'requirement_file': (BytesIO(b'%PDF-fake'), 'id.pdf', 'application/pdf')})
    db.session.refresh(req); assert req.filename is None
    item.status = 'PROCESSING'; db.session.commit()
    client.post(url+'/upload', data={'requirement_file': (image_bytes(), 'id.png', 'image/png')})
    db.session.refresh(req); assert req.filename is None
    assert client.post(url+'/remove').status_code == 403


def test_notifications_are_user_scoped_and_read_count_updates(system):
    user = db.session.scalar(db.select(User).where(User.username == 'resident-test'))
    other = db.session.scalar(db.select(User).where(User.username == 'other-test'))
    mine = Notification(user_id=user.id, title='Update', message='Real notification')
    theirs = Notification(user_id=other.id, title='Private', message='Private message')
    db.session.add_all([mine, theirs]); db.session.commit()
    client = login(system)
    payload = client.get('/workspace/notifications').json['data']
    assert payload['unread'] == 1 and len(payload['items']) == 1
    assert client.post('/workspace/notifications/read', data={'id': theirs.id}).status_code == 404
    assert client.post('/workspace/notifications/read', data={'id': mine.id}).json['success']
    assert client.get('/workspace/notifications').json['data']['unread'] == 0
    assert login(system, 'staff-test').get('/workspace/notifications').status_code == 200


def test_calendar_timezone_month_and_only_published_events(system):
    db.session.add_all([Event(title='Public meeting', starts_at=datetime(2026,10,8,16,tzinfo=timezone.utc), status='active'), Event(title='Private draft', starts_at=datetime(2026,10,9,tzinfo=timezone.utc), status='draft')]); db.session.commit()
    client = login(system)
    payload = client.get('/workspace/calendar?year=2026&month=10').json['data']
    assert payload['timezone'] == 'Asia/Manila'
    assert len(payload['events']) == 1
    assert payload['events'][0]['starts_at'].startswith('2026-10-09T00:00')
    assert client.get('/workspace/calendar?month=13').status_code == 400
    assert client.get('/workspace/calendar?year=2026&month=11').json['data']['events'] == []


def complaint(**changes):
    data = dict(incident_date='2026-10-01', respondent_name='Juan Santos', category='Noise complaint', incident_location='Main Street', narrative='Loud music continued all night near our house.', purok_id='')
    data.update(changes); return data


def test_blotter_duplicate_association_queue_and_audit(system):
    client = login(system)
    first = client.post('/resident/blotter/new', data=complaint()); assert first.status_code == 302
    again = client.post('/resident/blotter/new', data=complaint()); assert again.headers['Location'] == first.headers['Location']
    client.post('/resident/blotter/new', data=complaint(narrative='A different disturbance occurred at the same address.'))
    cases = db.session.scalars(db.select(BlotterCase).order_by(BlotterCase.id)).all()
    assert len(cases) == 2
    assert cases[0].case_number == f'BLT-{cases[0].id:08d}'
    assert db.session.scalar(db.select(db.func.count(BlotterCaseEvent.id))) == 3
    assert db.session.scalar(db.select(db.func.count(AuditLog.id)).where(AuditLog.action == 'BLOTTER_ASSOCIATE')) == 1
    from app.blotter.submissions import queue_position
    assert [queue_position(c) for c in cases] == [1,2]
    staff = login(system, 'staff-test')
    body = staff.get('/official/blotter').data
    assert body.index(cases[0].case_number.encode()) < body.index(cases[1].case_number.encode())
    assert login(system,'other-test').get(first.headers['Location']).status_code == 404


def test_uncertain_incidents_are_not_merged(system):
    client = login(system)
    for _ in range(2): assert client.post('/resident/blotter/new', data=complaint(incident_location='')).status_code == 302
    assert db.session.scalar(db.select(db.func.count(BlotterCase.id))) == 2


def test_expired_session_cannot_access_messaging_or_workspace(system):
    client = login(system)
    sessions = db.session.scalars(db.select(UserSession)).all()
    for session in sessions: session.expires_at = datetime.now(timezone.utc)-timedelta(minutes=1)
    db.session.commit()
    assert client.get('/messaging/api/thread', headers={'Accept':'application/json'}).status_code == 401
    assert client.get('/workspace/notifications', headers={'Accept':'application/json'}).status_code == 401


@pytest.mark.parametrize('username,path', [('admin-test','/admin/'),('staff-test','/official/'),('resident-test','/resident/')])
def test_workspace_dashboard_renders_shared_calendar_notifications(system, username, path):
    response = login(system, username).get(path)
    assert response.status_code == 200
    assert b'data-calendar' in response.data and b'data-notification-trigger' in response.data
    assert b'Gemini' not in response.data


def test_chatbot_identity_and_api_reply(system):
    client = login(system)
    response = client.post('/messaging/api/thread/messages', data={'body':'How do I request a certificate?', 'mode':'chatbot'})
    assert response.status_code == 200
    messages = client.get('/messaging/api/thread').json['messages']
    bots = [m for m in messages if m['sender_type']=='BOT']
    assert bots and bots[-1]['sender_name'] == 'Barangay Sta. Clara Norte Assistant'

@pytest.mark.parametrize('role,path', [('admin-test','/admin/users?sort=roles'),('staff-test','/official/residents?sort=household'),('staff-test','/official/residents/new'),('admin-test','/admin/roles'),('admin-test','/admin/permissions'),('admin-test','/admin/settings'),('staff-test','/official/households'),('staff-test','/official/blotter'),('staff-test','/official/documents'),('staff-test','/official/business'),('resident-test','/resident/profile')])
def test_registry_pages_and_safe_sort(system, role, path):
    response = login(system, role).get(path)
    assert response.status_code in (200, 302, 404), (path, response.status_code)


def test_admin_account_form_and_self_protection(system):
    client = login(system, 'admin-test')
    role = db.session.scalar(db.select(Role).where(Role.name == 'Resident'))
    response = client.post('/admin/users', data={'username':'created-user','email':'created@example.com','password':'Secure-created-password!','confirm_password':'Secure-created-password!','role_id':role.id,'is_active':'y'})
    assert response.status_code == 302
    user = db.session.scalar(db.select(User).where(User.username == 'created-user'))
    assert user is not None and user.is_active
    admin = db.session.scalar(db.select(User).where(User.username == 'admin-test'))
    assert client.post(f'/admin/users/{admin.id}/toggle').status_code == 302
    db.session.refresh(admin)
    assert admin.is_active


def test_csrf_is_enforced_when_enabled(system):
    client = login(system, 'admin-test')
    system.config['WTF_CSRF_ENABLED'] = True
    response = client.post('/admin/puroks', data={'name':'Purok 99'})
    assert response.status_code == 400
    assert not db.session.scalar(db.select(Purok).where(Purok.name == 'Purok 99'))


def test_rollback_discards_record_and_audit(system):
    client = login(system, 'admin-test')
    with system.test_request_context('/admin/puroks'):
        from flask_login import login_user
        login_user(db.session.scalar(db.select(User).where(User.username == 'admin-test')))
        item = Purok(name='Purok 88')
        db.session.add(item)
        db.session.flush()
        identifier = item.id
        db.session.rollback()
    assert db.session.get(Purok, identifier) is None
    assert not db.session.scalar(db.select(AuditLog).where(AuditLog.entity_type == 'Purok', AuditLog.entity_id == identifier))


def test_all_static_portal_get_routes_render_without_server_errors(system):
    clients = {prefix:login(system,user) for prefix,user in [('/admin','admin-test'),('/official','staff-test'),('/resident','resident-test'),('/workspace','resident-test')]}
    system.config["WTF_CSRF_ENABLED"] = True
    checked = 0
    for rule in system.url_map.iter_rules():
        if rule.arguments or 'GET' not in rule.methods:
            continue
        prefix = next((p for p in clients if rule.rule.startswith(p+'/')),None)
        if prefix is None:
            continue
        response = clients[prefix].get(rule.rule)
        assert response.status_code < 500, (rule.rule,response.status_code,response.data[:250])
        if response.status_code == 200 and response.mimetype == "text/html":
            from html.parser import HTMLParser
            class FormTokens(HTMLParser):
                def __init__(self):
                    super().__init__(); self.forms=[]; self.current=None
                def handle_starttag(self, tag, attrs):
                    attrs=dict(attrs)
                    if tag == "form":
                        self.current={"post":attrs.get("method", "get").lower()=="post", "csrf":False};self.forms.append(self.current)
                    if tag == "input" and self.current and attrs.get("name")=="csrf_token": self.current["csrf"]=True
                def handle_endtag(self,tag):
                    if tag == "form": self.current=None
            parser=FormTokens();parser.feed(response.get_data(as_text=True))
            assert all(not f["post"] or f["csrf"] for f in parser.forms), rule.rule
        checked += 1
    assert checked >= 40

@pytest.mark.parametrize('value',['garbage','NaN','Infinity','1e999'])
def test_numeric_inputs_reject_invalid_values(system,value):
    from app.form_values import strict_form_value
    with system.test_request_context('/admin/fees',method='POST',data={'amount':value}):
        with pytest.raises(ValueError): strict_form_value('amount',0,type=float)


def test_dashboard_api_returns_real_counts(system):
    response = login(system,'admin-test').get('/admin/dashboard-data')
    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['metrics']['residents'] == 2


def test_staff_can_view_but_not_change_puroks(system):
    client = login(system, 'staff-test')
    assert client.get('/official/puroks').status_code == 200
    assert client.post('/admin/puroks', data={'name':'Purok 42'}).status_code == 403


def test_unmapped_legacy_type_and_unverified_upload_cannot_issue(system):
    item, req = requirement_fixture()
    resident = login(system)
    staff = login(system,'staff-test')
    base = f'/official/document-requests/{item.id}'
    staff.post(base+'/status',data={'status':'UNDER_REVIEW'})
    resident.post(f'/resident/documents/{item.id}/requirements/{req.id}/upload',data={'requirement_file':(image_bytes(),'id.png','image/png')})
    for status in ['PROCESSING','APPROVED']:
        assert staff.post(base+'/status',data={'status':status}).status_code == 302
        db.session.refresh(item);assert item.status == 'UNDER_REVIEW'
    staff.post(base+'/generate')
    db.session.refresh(item);assert item.issued_document is None
    assert resident.get(f'/resident/documents/{item.id}/download').status_code == 404
    assert login(system,'other-test').get(f'/resident/documents/{item.id}/download').status_code == 404


def test_resident_create_edit_and_household_assignment(system):
    from app.models import Household
    p = Purok(name='Purok 25')
    household = Household(household_number='HH-25',address_line='Main Road',purok=p)
    db.session.add(household);db.session.commit()
    client = login(system,'staff-test')
    data = {'first_name':'Ana','last_name':'Santos','birth_date':'1950-01-01','sex':'Female','civil_status':'Single','voter_status':'registered','purok_id':p.id,'household_id':household.id,'household_member_no':'2'}
    response = client.post('/official/residents/new',data=data)
    assert response.status_code == 302
    resident = db.session.scalar(db.select(Resident).where(Resident.first_name=='Ana'))
    assert resident.household_id == household.id
    assert client.get(f'/official/residents/{resident.id}/edit').status_code == 200
    data['first_name']='Anna'
    assert client.post(f'/official/residents/{resident.id}/edit',data=data).status_code == 302
    db.session.refresh(resident);assert resident.first_name == 'Anna'
