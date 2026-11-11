"""Retired clearance uploads must not block old requests or remove stored evidence."""
import pytest
from app.extensions import db
from app.models import DocumentType, DocumentRequirement
from app.documents.workflow import RETIRED_CLEARANCE_REQUIREMENTS, requirement_names, transition_request
from test_system_integrity import system, login
from test_original_documents import setup_resident, create_request, verified_approval


def test_clearance_checklist_retirement_is_scoped():
    assert requirement_names('BARANGAY_CLEARANCE') == ['Valid government-issued ID']
    assert requirement_names('SCN-CLR') == ['Valid government-issued ID']
    assert 'Community Tax Certificate (cedula)' in requirement_names('CERTIFICATE_RESIDENCY')
    assert '2 pcs. 1x1 recent ID photos' in requirement_names('SOLO_PARENT_ENDORSEMENT')


def test_legacy_indigency_retired_uploads_are_hidden_and_do_not_block_print(system):
    from app.documents.workflow import RETIRED_INDIGENCY_REQUIREMENTS
    resident,signatory=setup_resident()
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='CERTIFICATE_INDIGENCY'))
    assert requirement_names('SCN-IND') == ['Valid government-issued ID', 'Proof of residency']
    assert '1 pc. 1x1 recent ID photo' in requirement_names('CERTIFICATE_RESIDENCY')
    client=login(system);item=create_request(client,doc,resident)
    retired=[DocumentRequirement(request_id=item.id,requirement_name=name,is_required=True,status='pending') for name in RETIRED_INDIGENCY_REQUIREMENTS]
    db.session.add_all(retired);db.session.commit();db.session.expire(item,['requirements'])
    staff=login(system,'staff-test')
    for page in [client.get(f'/resident/documents/{item.id}'),staff.get(f'/official/document-requests/{item.id}')]:
        assert page.status_code==200
        for name in RETIRED_INDIGENCY_REQUIREMENTS: assert name.encode() not in page.data
    verified_approval(staff,item,signatory)
    response=staff.post(f'/official/document-requests/{item.id}/print')
    assert response.location.endswith('/preview?print=1')
    assert all(db.session.get(DocumentRequirement,e.id).status=='pending' for e in retired)


def test_legacy_clearance_missing_retired_uploads_can_be_approved(system):
    resident,signatory=setup_resident()
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='BARANGAY_CLEARANCE'))
    client=login(system)
    item=create_request(client,doc,resident)
    assert not RETIRED_CLEARANCE_REQUIREMENTS.intersection(e.requirement_name for e in item.requirements)
    retired=[DocumentRequirement(request_id=item.id,requirement_name=name,is_required=True,status='pending') for name in RETIRED_CLEARANCE_REQUIREMENTS]
    db.session.add_all(retired);db.session.commit();db.session.expire(item,['requirements'])
    staff=login(system,'staff-test')
    for page in [client.get(f'/resident/documents/{item.id}'),staff.get(f'/official/document-requests/{item.id}')]:
        assert page.status_code==200
        for name in RETIRED_CLEARANCE_REQUIREMENTS: assert name.encode() not in page.data
        assert b'Valid government-issued ID' in page.data
    verified_approval(staff,item,signatory)
    assert all(db.session.get(DocumentRequirement,e.id) is not None and e.status=='pending' for e in retired)


def test_retired_checklist_does_not_bypass_valid_id_or_custom_evidence(system):
    resident,signatory=setup_resident()
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='BARANGAY_CLEARANCE'))
    item=create_request(login(system),doc,resident)
    extra=DocumentRequirement(request_id=item.id,requirement_name='Supporting evidence',is_required=True,status='pending')
    db.session.add(extra);db.session.commit();db.session.expire(item,['requirements'])
    staff=login(system,'staff-test');prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    response=staff.post(prefix+'/status',data={'status':'PROCESSING'},follow_redirects=True)
    assert b'Supporting evidence' in response.data
    db.session.refresh(item);assert item.status=='UNDER_REVIEW'
    count=len(item.requirements)
    for name in RETIRED_CLEARANCE_REQUIREMENTS:
        response=staff.post(prefix+'/additional-requirement',data={'requirement_name':name},follow_redirects=True)
        assert b'no longer part of the Barangay Clearance checklist' in response.data
    db.session.expire(item,['requirements']);assert len(item.requirements)==count
    valid=next(e for e in item.requirements if e.requirement_name=='Valid government-issued ID')
    valid.filename=None;db.session.commit()
    response=staff.post(prefix+'/status',data={'status':'PROCESSING'},follow_redirects=True)
    with pytest.raises(ValueError, match='Valid government-issued ID'):
        transition_request(item,'PROCESSING',resident.user)
    db.session.refresh(item);assert item.status=='UNDER_REVIEW'
