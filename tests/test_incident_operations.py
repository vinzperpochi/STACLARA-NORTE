from datetime import datetime, date, timedelta
import pytest
from app.extensions import db
from app.models import ResidentComplaint, ComplaintReferral, GovernmentAgency, AgencyHotline, ComplaintAssignment, User
from app.incidents.service import ensure_directory, classify
from app.attendance.service import MANILA
from test_system_integrity import system, login, image_bytes


def submit(client,category='NOISE',description='A recurring noise concern',**changes):
    data={'title':'Test incident','category':category,'description':description,'incident_at':(datetime.now(MANILA)-timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M'),'location':'Test landmark','urgency':'normal'};data.update(changes)
    response=client.post('/incidents/submit',data=data)
    assert response.status_code==302
    return db.session.scalar(db.select(ResidentComplaint).order_by(ResidentComplaint.id.desc()))


@pytest.mark.parametrize('category,description,danger,classification,agency',[
 ('UNKNOWN','May nasusunog na bahay malapit sa amin.',False,'EMERGENCY','BFP'),
 ('ROBBERY','May nangholdap sa amin at armado ang suspect.',False,'EMERGENCY','PNP'),
 ('UNKNOWN','May nahimatay at hindi humihinga.',False,'EMERGENCY','911'),
 ('NOISE','Videoke after midnight',False,'BARANGAY','BARANGAY'),
 ('UNKNOWN','Unknown concern',False,'REVIEW','BARANGAY'),
 ('UNKNOWN','Unknown emergency',True,'EMERGENCY','911'),
])
def test_deterministic_emergency_routing(system,category,description,danger,classification,agency):
    ensure_directory();db.session.commit();result=classify(category,description,danger=danger)
    assert result['classification']==classification and agency in result['agency_codes']
    if classification=='EMERGENCY': assert any(c['tel']=='911' for c in result['contacts'])
    assert result['requires_human_review']


def test_unverified_stale_hotlines_hidden_and_verified_local_used(system):
    ensure_directory();db.session.commit();agency=db.session.scalar(db.select(GovernmentAgency).where(GovernmentAgency.code=='BFP'))
    hotline=AgencyHotline(agency_id=agency.id,number='0123456789',availability='Office',coverage='Test only',active=True)
    db.session.add(hotline);db.session.commit()
    assert not any(c['code']=='BFP' for c in classify('FIRE')['contacts'])
    hotline.verified_on=date.today()-timedelta(days=181);hotline.verification_source='https://example.test/verified';db.session.commit()
    assert not any(c['code']=='BFP' for c in classify('FIRE')['contacts'])
    hotline.verified_on=date.today();db.session.commit()
    assert any(c['code']=='BFP' and c['tel']=='0123456789' for c in classify('FIRE')['contacts'])


def test_private_report_evidence_and_role_pages(system):
    resident=login(system);item=submit(resident,'FIRE','Fire emergency',evidence=(image_bytes(),'incident.png','image/png'))
    assert item.classification=='EMERGENCY' and item.response_status=='NOT_CONFIRMED'
    url=f'/incidents/{item.id}';assert resident.get(url).status_code==200
    assert login(system,'other-test').get(url).status_code==404
    evidence_url=f'/incidents/evidence/{item.evidence[0].id}'
    response=resident.get(evidence_url);assert response.status_code==200 and 'no-store' in response.headers['Cache-Control'];response.close()
    assert login(system,'other-test').get(evidence_url).status_code==404
    for username in ['resident-test','staff-test','admin-test']:
        client=login(system,username)
        for path in ['/incidents/','/incidents/directory']:
            assert client.get(path).status_code==200
    admin=login(system,'admin-test');assert admin.get('/incidents/rules').status_code==200
    assert login(system).post('/incidents/directory',data={'action':'agency'}).status_code==403


def test_sensitive_report_only_owner_admin_and_assigned_official(system):
    item=submit(login(system),'CHILD','Child protection concern')
    staff=login(system,'staff-test');assert staff.get(f'/incidents/{item.id}').status_code==404
    admin=login(system,'admin-test');user=db.session.scalar(db.select(User).where(User.username=='staff-test'))
    admin.post(f'/incidents/{item.id}/assign',data={'user_id':user.id})
    assert staff.get(f'/incidents/{item.id}').status_code==200
    assert login(system,'other-test').get(f'/incidents/{item.id}').status_code==404


def test_external_referral_approval_handoff_and_resident_timeline(system):
    resident=login(system);item=submit(resident,'NOISE','Cannot resolve through available barangay procedures',external_review='yes')
    assert item.classification=='REFERRAL' and item.status=='SUBMITTED'
    staff=login(system,'staff-test');agency=db.session.scalar(db.select(GovernmentAgency).where(GovernmentAgency.code=='PNP'))
    response=staff.post(f'/incidents/{item.id}/referral',data={'agency_id':agency.id,'reason':'For authorized assessment; visit the receiving office.'})
    assert response.status_code==302
    referral=db.session.scalar(db.select(ComplaintReferral));assert referral.approved_by_id and not referral.transmitted_at
    assert item.status=='FOR_EXTERNAL_REFERRAL'
    assert staff.get(f'/incidents/referrals/{referral.id}/print').status_code==200
    staff.post(f'/incidents/{item.id}/status',data={'status':'REFERRED_TO_EXTERNAL_AGENCY','public_response':'Referred'})
    assert item.status=='FOR_EXTERNAL_REFERRAL'
    staff.post(f'/incidents/referrals/{referral.id}/handoff',data={'confirmed':'yes','handoff_source':'Test receiving officer acknowledgment'})
    assert referral.transmitted_at and item.status=='REFERRED_TO_EXTERNAL_AGENCY'
    page=resident.get(f'/incidents/{item.id}');assert b'Documented referral handoff' in page.data and b'Private administrative notes' not in page.data
    assert item.status not in {'RESOLVED','CLOSED'}
    for kind,signature in [('csv',b'\xef\xbb\xbf'),('xlsx',b'PK'),('pdf',b'%PDF')]:
        result=staff.get('/incidents/reports?format='+kind);assert result.status_code==200 and result.data.startswith(signature);result.close()


def test_server_validation_and_csrf_do_not_create_reports(system):
    client=login(system)
    assert client.post('/incidents/submit',data={'category':'FIRE'}).status_code==200
    assert db.session.scalar(db.select(db.func.count(ResidentComplaint.id)))==0
    system.config['WTF_CSRF_ENABLED']=True
    assert client.post('/incidents/classify',json={'category':'FIRE'}).status_code==400


def test_pdf_evidence_follow_up_and_confirmed_response(system):
    from pypdf import PdfWriter
    from io import BytesIO
    writer=PdfWriter();writer.add_blank_page(width=100,height=100)
    data=BytesIO();writer.write(data);data.seek(0)
    resident=login(system);item=submit(resident,'MEDICAL','Serious medical emergency',evidence=(data,'test.pdf','application/pdf'))
    response=resident.get(f'/incidents/evidence/{item.evidence[0].id}')
    assert response.status_code==200 and 'attachment' in response.headers['Content-Disposition'];response.close()
    resident.post(f'/incidents/{item.id}/follow-up',data={'message':'Development test follow-up'})
    assert b'Development test follow-up' in resident.get(f'/incidents/{item.id}').data
    admin=login(system,'admin-test')
    admin.post(f'/incidents/{item.id}/response-status',data={'response_status':'COMPLETED','confirmation_source':'Test reference'})
    assert item.response_status=='NOT_CONFIRMED'
    admin.post(f'/incidents/{item.id}/response-status',data={'response_status':'RESPONDER_ACKNOWLEDGED','confirmation_source':'Test responder reference'})
    assert item.response_status=='RESPONDER_ACKNOWLEDGED' and item.status=='SUBMITTED'
    assert b'Test responder reference' not in resident.get(f'/incidents/{item.id}').data


def test_official_resident_owner_cannot_bypass_sensitive_review_assignment(system):
    from app.models import Role
    resident=login(system);item=submit(resident,'CHILD','Child protection concern')
    user=item.resident.user;user.roles.append(db.session.scalar(db.select(Role).where(Role.name=='Barangay Official')));db.session.commit()
    assert resident.get(f'/incidents/{item.id}').status_code==200
    assert resident.post(f'/incidents/{item.id}/status',data={'status':'UNDER_INITIAL_REVIEW','public_response':'Invalid owner review'}).status_code==403
    assert item.status=='SUBMITTED'
