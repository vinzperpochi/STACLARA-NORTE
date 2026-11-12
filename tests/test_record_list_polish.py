from datetime import date, datetime, timezone

from app.extensions import db
from app.models import DocumentType, EmergencyAlert, FeeConfiguration, Purok
from app.pagination import paginate_items
from test_system_integrity import login, system


def test_named_page_size_keeps_other_lists_independent(system):
    with system.test_request_context('/official/drrm?alerts_page=2&alerts_per_page=10&centers_per_page=999'):
        alerts = paginate_items(list(range(22)), 'alerts_page')
        centers = paginate_items(list(range(22)), 'centers_page')
    assert alerts.items == list(range(10, 20))
    assert alerts.size_parameter == 'alerts_per_page'
    assert centers.items == list(range(5))


def test_purok_archive_is_idempotent_and_restore_returns_record_to_active_list(system):
    purok = Purok(name='Purok 42', status='active')
    db.session.add(purok)
    db.session.commit()
    client = login(system, 'admin-test')
    path = f'/admin/puroks/{purok.id}/archive'

    for _ in range(2):
        assert client.post(path, data={'archive_action': 'archive'}).status_code == 302
    assert b'Purok 42' not in client.get('/admin/puroks').data
    archived = client.get('/admin/puroks?view=archived&per_page=10')
    assert b'Purok 42' in archived.data
    assert b'name="archive_action" value="restore"' in archived.data
    assert client.post(path, data={'archive_action': 'restore'}).status_code == 302
    assert b'Purok 42' in client.get('/admin/puroks').data


def test_official_can_edit_archive_and_restore_alert_as_draft(system):
    alert = EmergencyAlert(title='River advisory', message='Use alternate road',
                           issued_at=datetime.now(timezone.utc), status='PUBLISHED')
    db.session.add(alert)
    db.session.commit()
    path = f'/official/drrm/alerts/{alert.id}'
    client = login(system, 'staff-test')

    editor = client.get(path + '/edit', follow_redirects=True)
    assert b'Edit emergency alert' in editor.data and b'Use alternate road' in editor.data
    assert client.post(path + '/update', data={
        'title': 'Road advisory', 'message': 'Updated directions', 'alert_level': 'ADVISORY',
        'status': 'PUBLISHED',
    }).status_code == 302
    assert b'Road advisory' in client.get('/official/drrm').data
    assert client.post(path + '/archive').status_code == 302
    assert b'Road advisory' not in client.get('/official/drrm').data
    assert b'Road advisory' in client.get('/official/drrm?alerts_view=archived').data
    assert client.post(path + '/restore').status_code == 302
    db.session.refresh(alert)
    assert alert.status == 'DRAFT'
    assert b'Road advisory' in client.get('/official/drrm').data


def test_archived_fee_can_be_restored_only_after_its_document_type(system):
    document = DocumentType(code='ARCHIVE-QA', name='Archive QA Document', status='active')
    db.session.add(document)
    db.session.flush()
    fee = FeeConfiguration(document_type_id=document.id, amount=25,
                           effective_from=date(2026, 1, 1), status='active')
    db.session.add(fee)
    db.session.commit()
    client = login(system, 'admin-test')
    document_path = f'/admin/document-types/{document.id}'
    fee_path = f'/admin/fees/{fee.id}'

    assert client.post(fee_path + '/delete').status_code == 302
    assert client.post(document_path + '/delete').status_code == 302
    assert b'Archive QA Document' in client.get('/admin/document-types?view=archived').data
    assert b'Archive QA Document' in client.get('/admin/fees?view=archived').data
    assert client.post(fee_path + '/restore').status_code == 302
    db.session.refresh(fee)
    assert fee.status == 'inactive'
    assert client.post(document_path + '/restore').status_code == 302
    assert client.post(fee_path + '/restore').status_code == 302
    db.session.refresh(fee)
    assert fee.status == 'active'
