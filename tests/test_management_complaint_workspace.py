from datetime import date
from app.extensions import db
from app.models import BlotterCase, User
from test_system_integrity import system, login
from test_incident_operations import submit

def test_management_workspace_combines_records_and_filters(system):
    incident=submit(login(system), 'NOISE', 'Ordinary noise concern')
    resident=db.session.scalar(db.select(User).where(User.username=='resident-test')).resident
    case=BlotterCase(case_number='BLT-HUB-TEST',complainant_id=resident.id,respondent_name='Test respondent',category='Formal noise case',incident_date=date.today(),narrative='Synthetic case',status='OPEN')
    db.session.add(case);db.session.commit()
    for username in ['staff-test','admin-test']:
        client=login(system,username);page=client.get('/incidents/workspace')
        assert page.status_code==200
        assert incident.reference.encode() in page.data and b'BLT-HUB-TEST' in page.data
        assert f'/incidents/{incident.id}'.encode() in page.data
        assert f'/official/blotter/{case.id}'.encode() in page.data
        filtered=client.get('/incidents/workspace?kind=blotter&q=BLT-HUB')
        assert b'BLT-HUB-TEST' in filtered.data and incident.reference.encode() not in filtered.data
    assert login(system).get('/incidents/workspace').status_code==403

def test_management_workspace_retains_sensitive_incident_access(system):
    incident=submit(login(system), 'CHILD', 'Sensitive child protection concern')
    staff=login(system,'staff-test');admin=login(system,'admin-test')
    assert incident.reference.encode() not in staff.get('/incidents/workspace').data
    assert incident.reference.encode() in admin.get('/incidents/workspace').data
    user=db.session.scalar(db.select(User).where(User.username=='staff-test'))
    admin.post(f'/incidents/{incident.id}/assign',data={'user_id':user.id})
    assert incident.reference.encode() in staff.get('/incidents/workspace').data
