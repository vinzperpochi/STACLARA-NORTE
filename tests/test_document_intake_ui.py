"""Simplified intake must preserve evidence and approval requirements."""
import pytest
from app.extensions import db
from app.models import DocumentType, Request
from app.documents.engine import TEMPLATE_CODES
from test_system_integrity import system, login
from test_original_documents import setup_resident, details


@pytest.mark.parametrize('code',list(TEMPLATE_CODES))
def test_initial_request_without_removed_fields_stays_pending(system,code):
    resident,signatory=setup_resident()
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code==code))
    client=login(system)
    page=client.get('/resident/documents/new?document_type_id='+str(doc.id)).data
    assert b'data-document-intake' in page
    for removed in [b'Load document fields',b'name="detail_',b'id="document_type_id"']:
        assert removed not in page
    assert page.count(b'name="document_type_id"')==1
    assert b'Purpose of document' in page and b'name="description"' in page
    response=client.post('/resident/documents/new',data={'document_type_id':doc.id,'request_stage':'initial','resident_id':'999'})
    assert response.status_code==302
    item=db.session.scalar(db.select(Request).order_by(Request.id.desc()))
    assert item.resident_id==resident.id and item.document_type_id==doc.id
    assert item.status=='PENDING' and item.description is None and item.additional_data=={}
    assert item.requirements and len(item.status_history)==1
    staff=login(system,'staff-test')
    staff.post(f'/official/document-requests/{item.id}/status',data={'status':'UNDER_REVIEW'})
    staff.post(f'/official/document-requests/{item.id}/status',data={'status':'APPROVED'})
    db.session.refresh(item)
    assert item.status=='UNDER_REVIEW' and item.issued_document is None


def test_initial_intake_can_complete_existing_correction_workflow(system):
    resident,signatory=setup_resident()
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='BARANGAY_CLEARANCE'))
    client=login(system)
    client.post('/resident/documents/new',data={'document_type_id':doc.id,'request_stage':'initial'})
    item=db.session.scalar(db.select(Request).order_by(Request.id.desc()))
    staff=login(system,'staff-test');prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/status',data={'status':'UNDER_REVIEW'})
    staff.post(prefix+'/status',data={'status':'NEEDS_CORRECTION','notes':'Please complete the document information.'})
    assert client.post(f'/resident/documents/{item.id}/correction',data=dict(description='Employment requirement',**details(resident,doc.template_code))).status_code==302
    db.session.refresh(item)
    assert item.status=='PENDING' and item.description=='Employment requirement'
    assert item.additional_data['cedula_number']=='CTC-123'


def test_invalid_document_and_csrf_cannot_create_initial_request(system):
    client=login(system)
    assert client.post('/resident/documents/new',data={'document_type_id':'999999','request_stage':'initial'}).status_code==200
    assert db.session.scalar(db.select(db.func.count(Request.id)))==0
    system.config['WTF_CSRF_ENABLED']=True
    assert client.post('/resident/documents/new',data={'document_type_id':'1','request_stage':'initial'}).status_code==400
    assert db.session.scalar(db.select(db.func.count(Request.id)))==0


@pytest.mark.parametrize('code',list(TEMPLATE_CODES))
def test_initial_purpose_is_saved_and_included_in_direct_print(system,code):
    from app.documents.engine import CHECKLISTS
    from test_system_integrity import image_bytes
    resident,signatory=setup_resident()
    resident.is_verified=True;db.session.commit()
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code==code))
    client=login(system);purpose='Employment & school enrollment'
    response=client.post('/resident/documents/new',data={'document_type_id':doc.id,'request_stage':'initial','description':purpose})
    assert response.status_code==302
    item=db.session.scalar(db.select(Request).order_by(Request.id.desc()))
    assert item.description==purpose and item.additional_data=={}
    for evidence in item.active_requirements:
        client.post(f'/resident/documents/{item.id}/requirements/{evidence.id}/upload',data={'requirement_file':(image_bytes(),'id.png','image/png')})
    checks={'check_'+str(i):'yes' for i in range(len(CHECKLISTS[doc.template_code])+1)}
    checks.update({'evidence_'+str(e.id):'yes' for e in item.active_requirements})
    staff=login(system,'staff-test');prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/approve',data=dict(checks,signatory_id=signatory.id))
    response=staff.post(prefix+'/print');assert response.location.endswith('/preview?print=1')
    db.session.refresh(item);assert item.issued_document.snapshot['purpose']==purpose
    from html import escape
    assert escape(purpose).encode() in staff.get(prefix+'/certificate').data


def test_initial_purpose_length_limit_preserves_input_without_creating_request(system):
    setup_resident();doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='BARANGAY_CLEARANCE'))
    client=login(system)
    response=client.post('/resident/documents/new',data={'document_type_id':doc.id,'request_stage':'initial','description':'x'*501})
    assert response.status_code==200 and b'Description cannot exceed 500 characters' in response.data
    assert db.session.scalar(db.select(db.func.count(Request.id)))==0
