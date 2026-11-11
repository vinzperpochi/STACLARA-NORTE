from datetime import date
from app.extensions import db
from app.models import BlotterCase, BlotterCaseAccess, User
from test_system_integrity import system,login
from test_incident_operations import submit


def test_one_workspace_lists_owned_incidents_and_authorized_blotter(system):
    resident=login(system);item=submit(resident)
    owner=item.resident;other=db.session.scalar(db.select(User).where(User.username=='other-test')).resident
    case=BlotterCase(case_number='CASE-OWN',complainant_id=owner.id,category='Dispute',incident_date=date.today(),narrative='Test dispute',respondent_name='Test person',status='Pending')
    private=BlotterCase(case_number='CASE-PRIVATE',complainant_id=other.id,category='Dispute',incident_date=date.today(),narrative='Private dispute',respondent_name='Test person',status='Pending')
    db.session.add_all([case,private]);db.session.commit()
    response=resident.get('/resident/blotter');assert response.status_code==200
    assert item.reference.encode() in response.data and b'CASE-OWN' in response.data and b'CASE-PRIVATE' not in response.data
    assert b'href="/incidents/submit"' in response.data and b'href="/incidents/directory"' in response.data
    assert b'Complaint and emergency services' not in response.data
    assert item.reference.encode() not in resident.get('/resident/blotter?kind=blotter').data
    assert b'CASE-OWN' not in resident.get('/resident/blotter?kind=incident').data
    db.session.add(BlotterCaseAccess(case_id=private.id,resident_id=owner.id,granted_by_id=db.session.scalar(db.select(User.id).where(User.username=='admin-test'))));db.session.commit()
    assert b'CASE-PRIVATE' in resident.get('/resident/blotter').data
    assert item.reference.encode() not in login(system,'other-test').get('/resident/blotter').data
