import pytest
from app.extensions import db
from app.models import User
from test_system_integrity import system, login

def test_staff_insights_keep_workspace_and_identity(system):
    client=login(system,'staff-test')
    with client.session_transaction() as session: identity=session['_user_id']
    for path in ['/official/analytics','/official/report-center','/official/reports']:
        response=client.get(path)
        assert response.status_code==200
        html=response.get_data(as_text=True)
        assert 'workspace-official' in html
        assert 'workspace-admin' not in html
        assert 'href="/official/analytics"' in html
        assert 'href="/official/report-center"' in html
        assert 'href="/admin/analytics"' not in html
        assert 'href="/admin/reports"' not in html
    with client.session_transaction() as session: assert session['_user_id']==identity
    user=db.session.get(User,int(identity))
    assert [r.name for r in user.roles]==['Barangay Official']
    analytics=client.get('/official/analytics').get_data(as_text=True)
    assert 'fetch("/official/analytics-data")' in analytics
    assert client.get('/official/analytics-data').is_json
    reports=client.get('/official/report-center').get_data(as_text=True)
    assert '/official/report-center/export/' in reports
    assert 'href="/official/reports"' in reports

def test_staff_export_and_invalid_filters_stay_official(system):
    client=login(system,'staff-test')
    response=client.get('/official/report-center/export/population/csv')
    assert response.status_code==200 and response.mimetype=='text/csv'
    assert 'attachment;' in response.headers['Content-Disposition']
    response=client.get('/official/report-center/export/population/pdf')
    assert response.status_code==200 and response.data.startswith(b'%PDF')
    for query in ['start=invalid','start=2026-10-09&end=2026-10-01']:
        response=client.get('/official/report-center/export/population/csv?'+query)
        assert response.status_code==302
        assert response.location.endswith('/official/report-center')

@pytest.mark.parametrize('path',['/official/analytics','/official/analytics-data','/official/report-center','/official/report-center/export/population/csv'])
def test_staff_insights_deny_residents_and_anonymous(system,path):
    assert system.test_client().get(path).status_code==302
    assert login(system).get(path).status_code==403

def test_admin_insights_retain_admin_workspace(system):
    client=login(system,'admin-test')
    for path in ['/admin/analytics','/admin/reports']:
        response=client.get(path)
        assert response.status_code==200
        assert b'workspace-admin' in response.data
    assert client.get('/admin/reports/export/population/csv?start=invalid').location.endswith('/admin/reports')
