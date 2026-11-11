"""Public contact details share one editable source without exposing secret settings."""
from app.extensions import db
from app.models import SystemSetting
from app.site_information import public_information
from test_system_integrity import system,login


def information(**changes):
    values=dict(action='barangay_information',barangay_name='Barangay Sta. Clara Norte',
        municipality='Pila',province='Laguna',country='Philippines',zip_code='4010',
        hall_address='Sample Barangay Office, Pila, Laguna',contact_phone='09171234567',
        contact_email='office@example.com',office_hours='Confirmed test schedule',
        dpo_name='Test Designated Officer',dpo_email='privacy@example.com',dpo_phone='09181234567',
        help_note='Test walk-in assistance',charter_note='Test approved service charter',
        fees_note='Test fee instructions',foi_note='Test receiving-office instructions')
    values.update(changes)
    return values


def test_admin_saves_details_and_all_public_views_update_without_restart(system):
    client=login(system,'admin-test')
    assert client.post('/admin/settings',data=information()).status_code==302
    pages=[(system.test_client(),'/auth/login'),(system.test_client(),'/privacy'),
           (login(system,'staff-test'),'/official/'),(login(system),'/resident/')]
    for reader,path in pages:
        response=reader.get(path)
        assert response.status_code==200
        assert b'Test Designated Officer' in response.data and b'privacy@example.com' in response.data
        assert b'not been configured' not in response.data
    help_page=system.test_client().get('/help')
    assert b'Sample Barangay Office' in help_page.data and b'Confirmed test schedule' in help_page.data
    assert b'office@example.com' in help_page.data and b'0403422016' in help_page.data
    assert b'Official Pila LGU contact directory' in help_page.data
    assert client.post('/admin/settings',data=information(dpo_name='Updated Officer')).status_code==302
    assert b'Updated Officer' in system.test_client().get('/privacy').data


def test_public_contact_values_support_legacy_keys_but_exclude_secret_rows(system):
    db.session.add_all([SystemSetting(setting_key='DPO_NAME',setting_value='Legacy Officer',is_secret=False),
        SystemSetting(setting_key='site.dpo_email',setting_value='PRIVATE-CONTACT-SECRET',is_secret=True),
        SystemSetting(setting_key='UNRELATED_SECRET',setting_value='OTHER-SECRET',is_secret=True)])
    db.session.commit()
    response=system.test_client().get('/auth/login')
    assert b'Legacy Officer' in response.data and b'PRIVATE-CONTACT-SECRET' not in response.data
    assert b'OTHER-SECRET' not in response.data


def test_missing_officer_is_not_replaced_with_an_unrelated_person_or_municipal_contact(system):
    with system.test_request_context('/privacy'):
        values=public_information()
        assert values['dpo_name']==values['dpo_email']==values['dpo_phone']==''
        assert values['contact_phone']==values['contact_email']==''
        assert values['municipality']=='Pila' and values['province']=='Laguna'
    source=system.test_client().get('/privacy').data
    assert b'not been configured' not in source
    assert b'554-6451' not in source  # Municipal number is not published as a DPO contact.


def test_invalid_information_never_partially_publishes(system):
    client=login(system,'admin-test')
    assert client.post('/admin/settings',data=information()).status_code==302
    response=client.post('/admin/settings',data=information(dpo_email='invalid',dpo_name='Should not save'))
    assert response.status_code==200
    saved=db.session.scalar(db.select(SystemSetting).where(SystemSetting.setting_key=='site.dpo_name'))
    assert saved.setting_value=='Test Designated Officer'
    assert b'Should not save' not in system.test_client().get('/privacy').data


def test_only_admin_can_publish_and_generic_settings_keep_working(system):
    assert login(system,'staff-test').post('/admin/settings',data=information()).status_code==403
    assert login(system).post('/admin/settings',data=information()).status_code==403
    client=login(system,'admin-test')
    assert client.post('/admin/settings',data={'setting_key':'existing.setting','setting_value':'kept','description':'Existing workflow'}).status_code==302
    assert db.session.scalar(db.select(SystemSetting).where(SystemSetting.setting_key=='existing.setting')).setting_value=='kept'
    system.config['WTF_CSRF_ENABLED']=True
    assert client.post('/admin/settings',data=information()).status_code==400
