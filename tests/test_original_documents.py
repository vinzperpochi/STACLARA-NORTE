"""Original-template approval, ownership, expiry, numbering and verification."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite import insert
from app.extensions import db
from app.models import DocumentType, DocumentSignatory, DocumentSequence, DocumentRequirement, IssuedDocument, Request, Resident, User, FeeConfiguration
from app.documents.engine import TEMPLATE_CODES, DETAIL_FIELDS, CHECKLISTS, fields_for, next_number, expiry, render_original, pdf_bytes
from app.documents.workflow import ensure_catalog, transition_request, generate_document
from test_system_integrity import system, login, image_bytes

def setup_resident():
    user=db.session.scalar(db.select(User).where(User.username=='resident-test'))
    r=user.resident;r.middle_name='Dela';r.suffix='Jr.';r.sex='Female';r.civil_status='Single';r.address_line='123 Main Street, Purok 2';r.contact_number='09171234567';r.residency_duration='5';r.occupation='Teacher';r.educational_attainment='College Graduate'
    admin=db.session.scalar(db.select(User).where(User.username=='admin-test'))
    signatory=DocumentSignatory(full_name='Authorized Test Official',designation='Punong Barangay',authorized_by_id=admin.id,effective_from=date(2020,1,1),status='active')
    db.session.add(signatory);types=ensure_catalog()
    for dt in types: db.session.add(FeeConfiguration(document_type_id=dt.id,amount=0,effective_from=date(2020,1,1),status='active'))
    db.session.commit();return r,signatory

def details(resident,code):
    specific=dict(valid_id='Government ID 1234',monthly_income='1000',dependents='2',residency_since='2020',tenure='Owner',business_name='Test Grocery',application_type='New',business_nature='Retail',business_area='40',employees='2',business_address='123 Main Street, Purok 2',business_registration='DTI-123',capital='10000',cedula_number='CTC-123',cedula_issued='01/01/2026, Pila',requesting_agency='Test agency',solo_reason='Death of spouse',child_1_name='Child One',child_1_birth_date='2015-01-01',child_1_relationship='Son',school_graduated='Test School 2025')
    return {'detail_'+k:specific.get(k,'') for k in fields_for(resident,code)}

def create_request(client,dt,resident):
    response=client.post('/resident/documents/new',data=dict(document_type_id=dt.id,description='Employment requirement',**details(resident,dt.template_code)))
    assert response.status_code==302
    item=db.session.scalar(db.select(Request).order_by(Request.id.desc()))
    assert item and response.location.endswith('/'+str(item.id))
    for evidence in item.requirements:
        response=client.post(f'/resident/documents/{item.id}/requirements/{evidence.id}/upload',data={'requirement_file':(image_bytes(),'id.png','image/png')})
        assert response.status_code==302
    return item

def verified_approval(staff,item,signatory):
    prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    checks={'check_'+str(i):'yes' for i in range(len(CHECKLISTS[item.document_type.template_code])+1)}
    checks.update({'evidence_'+str(e.id):'yes' for e in item.requirements})
    staff.post(prefix+'/verify',data=dict(signatory_id=signatory.id,verification_notes='Official records and supporting evidence checked.',**checks))
    db.session.refresh(item);assert item.verified_at
    review_page=staff.get(prefix).data.decode()
    assert 'Approve request' in review_page
    assert 'disabled aria-disabled="true"' not in review_page
    result=staff.post(prefix+'/status',data={'status':'APPROVED'},follow_redirects=True)
    db.session.refresh(item)
    assert item.status=='READY_FOR_PRINTING',result.data.decode()[-2000:]
    return prefix

@pytest.mark.parametrize('old,code',list(TEMPLATE_CODES.items()))
def test_all_seven_original_forms_certificates_and_workflow(system,old,code):
    resident,signatory=setup_resident();client=login(system);dt=db.session.scalar(db.select(DocumentType).where(DocumentType.code==old))
    assert client.get('/resident/documents').status_code==200
    page=client.get('/resident/documents/new?document_type_id='+str(dt.id))
    assert page.status_code==200 and b'Registered information' in page.data
    item=create_request(client,dt,resident)
    assert item.resident_id==resident.id and item.status=='PENDING'
    staff=login(system,'staff-test');prefix=verified_approval(staff,item,signatory)
    certificate=staff.get(prefix+'/certificate');assert certificate.status_code==200
    text=certificate.data.decode();assert code+'-' in text
    assert ('Maria Dela resident-test Jr.' in text) and '123 Main Street, Purok 2' in text
    assert 'Authorized Test Official' in text and 'Punong Barangay' in text
    assert 'data:image/png;base64,' in text and 'generic' not in text
    assert staff.get(prefix+'/application').status_code==200
    assert staff.get(prefix+'/preview').status_code==200
    assert client.get(prefix+'/certificate').status_code==403
    assert client.get(prefix+'/pdf').status_code==403
    assert client.post(prefix+'/printed').status_code==403
    assert client.get(f'/resident/documents/{item.id}/download').status_code in {403,404}
    doc=item.issued_document
    assert doc.document_number==code+'-'+str(doc.issued_at.year)+'-000001'
    token=doc.verification_token
    assert b'Not issued' in system.test_client().get('/verify/'+token).data
    assert system.test_client().get('/verify/'+doc.document_number).status_code==404
    staff.post(prefix+'/printed');db.session.refresh(item);assert item.status=='PRINTED'
    staff.post(prefix+'/release');db.session.refresh(item);assert item.status=='RELEASED'
    public=system.test_client().get('/verify/'+token)
    assert b'Valid official document' in public.data and resident.first_name.encode() not in public.data
    assert len(item.status_history)>=6 and all(e.changed_by_id and e.created_at for e in item.status_history)

def test_unverified_pending_rejected_and_cross_resident_requests(system):
    resident,signatory=setup_resident();client=login(system);dt=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='CERTIFICATE_RESIDENCY'));item=create_request(client,dt,resident)
    staff=login(system,'staff-test');prefix=f'/official/document-requests/{item.id}'
    assert staff.get(prefix+'/certificate').status_code==404
    pending_page=staff.get(prefix).data
    assert b'Begin review' in pending_page
    assert b'value="APPROVED"' not in pending_page
    assert b'value="REJECTED"' not in pending_page
    stale=staff.post(prefix+'/status',data={'status':'APPROVED'},follow_redirects=True)
    assert b'Begin review and save verification before approving' in stale.data
    db.session.refresh(item);assert item.status=='PENDING'
    staff.post(prefix+'/generate');db.session.refresh(item);assert item.issued_document is None
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    staff.post(prefix+'/status',data={'status':'APPROVED'});db.session.refresh(item);assert item.status=='UNDER_REVIEW' and item.issued_document is None
    review_page=staff.get(prefix).data
    assert b'View the ID, confirm the checks below, then approve.' in review_page
    assert b'name="check_0"' in review_page
    assert b'/approve"' in review_page
    assert b'value="UNDER_REVIEW"' not in review_page
    assert login(system,'other-test').get(f'/resident/documents/{item.id}').status_code==404
    assert login(system,'other-test').get(f'/resident/documents/{item.id}/correction').status_code==404
    staff.post(prefix+'/status',data={'status':'REJECTED','notes':'Not eligible'})
    staff.post(prefix+'/generate');db.session.refresh(item);assert item.status=='REJECTED' and item.issued_document is None

def test_corrections_invalidate_verification_and_reupload(system):
    r,s=setup_resident();client=login(system);dt=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='BARANGAY_CLEARANCE'));item=create_request(client,dt,r)
    staff=login(system,'staff-test');prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    staff.post(prefix+'/status',data={'status':'NEEDS_CORRECTION','notes':'Correct cedula details'})
    db.session.refresh(item);assert item.status=='NEEDS_CORRECTION'
    assert client.get(f'/resident/documents/{item.id}/correction').status_code==200
    client.post(f'/resident/documents/{item.id}/correction',data=dict(description='Employment',**details(r,'SCN-CLR')))
    db.session.refresh(item);assert item.status=='PENDING' and not item.verified_at

def test_valid_expired_revoked_nonexistent_and_admin_permissions(system):
    r,s=setup_resident();item=create_request(login(system),db.session.scalar(db.select(DocumentType).where(DocumentType.code=='CERTIFICATE_RESIDENCY')),r)
    staff=login(system,'staff-test');prefix=verified_approval(staff,item,s);staff.post(prefix+'/printed');staff.post(prefix+'/release')
    doc=item.issued_document;public=system.test_client();url='/verify/'+doc.verification_token
    doc.expires_at=datetime.now(timezone.utc)-timedelta(days=1);db.session.commit();assert b'Expired' in public.get(url).data
    assert staff.post(prefix+'/revoke',data={'notes':'Unauthorized'}).status_code==403
    login(system,'admin-test').post(prefix+'/revoke',data={'notes':'Incorrect certified information'})
    assert b'Revoked' in public.get(url).data
    assert staff.get(prefix+'/certificate').status_code==403
    assert public.get('/verify/nonexistent-token').status_code==404
    assert staff.get('/official/document-settings').status_code==403
    assert login(system,'admin-test').get('/official/document-settings').status_code==200

def test_calendar_expiry_leap_year_and_number_rollover(system):
    assert expiry('SCN-IND',date(2026,8,31))==date(2027,2,28)
    assert expiry('SCN-SPE',date(2024,2,29))==date(2025,2,28)
    assert expiry('SCN-BIZ',date(2026,10,9))==date(2026,12,31)
    assert next_number('SCN-RSD',2026).endswith('000001')
    assert next_number('SCN-RSD',2026).endswith('000002')
    assert next_number('SCN-RSD',2027).endswith('000001')

def test_concurrent_atomic_control_numbers(system):
    path=Path(system.config['STORAGE_ROOT'])/'numbering.sqlite'
    engine=create_engine('sqlite:///'+path.as_posix(),connect_args={'timeout':30})
    DocumentSequence.__table__.create(engine)
    def allocate(_):
        now=datetime.now(timezone.utc)
        stmt=insert(DocumentSequence).values(template_code='SCN-RSD',year=2026,last_number=1,created_at=now,updated_at=now)
        stmt=stmt.on_conflict_do_update(index_elements=['template_code','year'],set_={'last_number':DocumentSequence.last_number+1}).returning(DocumentSequence.last_number)
        with engine.begin() as conn: return conn.execute(stmt).scalar_one()
    with ThreadPoolExecutor(max_workers=6) as pool: numbers=list(pool.map(allocate,range(20)))
    assert sorted(numbers)==list(range(1,21));engine.dispose()

def test_fee_schedule_receipt_and_free_ftj(system):
    r,s=setup_resident();dt=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='CERTIFICATE_RESIDENCY'))
    db.session.add(FeeConfiguration(document_type_id=dt.id,amount=75,effective_from=date.today(),status='active'));db.session.commit()
    item=create_request(login(system),dt,r);staff=login(system,'staff-test');prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    payload={'check_0':'yes','check_1':'yes','verification_notes':'All official records verified','signatory_id':s.id,**{'evidence_'+str(e.id):'yes' for e in item.requirements}}
    staff.post(prefix+'/verify',data=payload);staff.post(prefix+'/status',data={'status':'APPROVED'});db.session.refresh(item)
    assert item.status=='UNDER_REVIEW' and not item.issued_document
    staff.post(prefix+'/receipt',data={'amount':'75','receipt_number':'OR-123'})
    staff.post(prefix+'/status',data={'status':'APPROVED'});db.session.refresh(item)
    assert item.issued_document.snapshot['fee']=='75.00' and item.issued_document.snapshot['receipt_number']=='OR-123'
    from app.documents.engine import configured_fee
    ftj=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='FIRST_TIME_JOBSEEKER'));ftj.base_fee=100
    assert configured_fee(ftj,date.today())==0

def test_verified_data_change_requires_fresh_review(system):
    r,s=setup_resident();item=create_request(login(system),db.session.scalar(db.select(DocumentType).where(DocumentType.code=='CERTIFICATE_RESIDENCY')),r)
    staff=login(system,'staff-test');prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    staff.post(prefix+'/verify',data={'check_0':'yes','check_1':'yes','verification_notes':'Records checked','signatory_id':s.id,**{'evidence_'+str(e.id):'yes' for e in item.requirements}})
    r.address_line='Changed after review';db.session.commit()
    staff.post(prefix+'/status',data={'status':'APPROVED'});db.session.refresh(item)
    assert item.status=='UNDER_REVIEW' and not item.issued_document

def test_first_time_benefit_cannot_be_issued_twice(system):
    r,s=setup_resident();dt=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='FIRST_TIME_JOBSEEKER'))
    client=login(system);staff=login(system,'staff-test');first=create_request(client,dt,r)
    verified_approval(staff,first,s)
    second=create_request(client,dt,r);prefix=f'/official/document-requests/{second.id}'
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    staff.post(prefix+'/verify',data={'check_0':'yes','check_1':'yes','check_2':'yes','verification_notes':'Records checked','signatory_id':s.id,**{'evidence_'+str(e.id):'yes' for e in second.requirements}})
    staff.post(prefix+'/status',data={'status':'APPROVED'});db.session.refresh(second)
    assert second.status=='UNDER_REVIEW' and not second.issued_document

def test_issued_snapshot_and_artifact_do_not_change_after_profile_edit(system):
    r,s=setup_resident();item=create_request(login(system),db.session.scalar(db.select(DocumentType).where(DocumentType.code=='CERTIFICATE_RESIDENCY')),r)
    staff=login(system,'staff-test');prefix=verified_approval(staff,item,s)
    original=staff.get(prefix+'/certificate').data
    r.first_name='Later profile name';r.address_line='Later profile address';s.full_name='Later authorized name';db.session.commit()
    assert staff.get(prefix+'/certificate').data==original
    assert item.issued_document.snapshot['full_name']=='Maria Dela resident-test Jr.'

def test_control_number_transaction_rollback_reuses_unissued_number(system):
    assert next_number('SCN-CLR',2030).endswith('000001')
    db.session.rollback()
    assert next_number('SCN-CLR',2030).endswith('000001')

def test_original_pdf_a4_and_long_data(system):
    r,s=setup_resident();r.first_name='Alexandria '+('Verylongname '*5);r.address_line=('Long residential street and landmark '*5)+'Purok 2';db.session.commit()
    item=create_request(login(system),db.session.scalar(db.select(DocumentType).where(DocumentType.code=='CERTIFICATE_RESIDENCY')),r)
    staff=login(system,'staff-test');prefix=verified_approval(staff,item,s)
    pdf=staff.get(prefix+'/pdf');assert pdf.status_code==200 and pdf.data.startswith(b'%PDF')
