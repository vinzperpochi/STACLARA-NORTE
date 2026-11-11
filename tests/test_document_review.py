from pathlib import Path
from werkzeug.datastructures import FileStorage
from app.extensions import db
from app.models import DocumentType, Request, Payment
from app.documents.engine import CHECKLISTS
from app.documents.workflow import evidence_available
from app.image_uploads import save_image
from test_system_integrity import system, login, image_bytes
from test_original_documents import setup_resident, details


def initial_request(system):
    resident,signatory=setup_resident();resident.is_verified=True
    resident.philsys_card_filename=save_image(FileStorage(stream=image_bytes(),filename='registration-id.png',content_type='image/png'),'registration_documents')
    doc=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='BARANGAY_CLEARANCE'));doc.base_fee=25
    db.session.commit()
    from app.models import FeeConfiguration
    for fee in db.session.scalars(db.select(FeeConfiguration).where(FeeConfiguration.document_type_id==doc.id)): fee.amount=25
    db.session.commit()
    client=login(system);client.post('/resident/documents/new',data={'document_type_id':doc.id,'request_stage':'initial'})
    item=db.session.scalar(db.select(Request).order_by(Request.id.desc()))
    checks={'check_'+str(i):'yes' for i in range(len(CHECKLISTS[doc.template_code])+1)}
    checks.update({'evidence_'+str(e.id):'yes' for e in item.active_requirements})
    checks['signatory_id']=signatory.id
    return resident,item,client,login(system,'staff-test'),checks


def test_registration_id_preview_is_private_and_scoped(system):
    resident,item,client,staff,checks=initial_request(system)
    evidence=item.active_requirements[0];assert evidence.filename is None and evidence_available(evidence)
    prefix=f'/official/document-requests/{item.id}'
    url=prefix+f'/requirements/{evidence.id}/view'
    page=staff.get(prefix);assert page.status_code==200 and b'From registration' in page.data and url.encode() in page.data
    image=staff.get(url);assert image.status_code==200 and image.mimetype=='image/png' and 'no-store' in image.headers['Cache-Control']
    assert client.get(url).status_code==403
    own=f'/resident/documents/{item.id}/requirements/{evidence.id}/view'
    assert client.get(own).status_code==200
    assert login(system,'other-test').get(own).status_code==404
    assert staff.get(prefix+f'/requirements/{evidence.id+999}/view').status_code==404
    assert b'ID / evidence submitted during registration' in client.get(f'/resident/documents/{item.id}').data


def test_one_step_approval_precedes_in_person_payment_and_certificate(system):
    resident,item,client,staff,checks=initial_request(system);prefix=f'/official/document-requests/{item.id}'
    response=staff.post(prefix+'/approve',data=checks,follow_redirects=True)
    db.session.refresh(item)
    assert item.status=='APPROVED' and item.issued_document is None and not item.payments
    assert b'Request approved' in response.data and b'Record in-person payment' in response.data
    assert [event.to_status for event in item.status_history if event.from_status!=event.to_status]==['PENDING','UNDER_REVIEW','APPROVED']
    assert staff.post(prefix+'/approve',data=checks).status_code==302
    assert len(item.status_history)==4
    form=dict(details(resident,'SCN-CLR'),description='Employment',confirm_details='yes')
    assert staff.post(prefix+'/prepare',data=form).status_code==302
    staff.post(prefix+'/generate');db.session.refresh(item)
    assert item.status=='APPROVED' and item.issued_document is None
    staff.post(prefix+'/receipt',data={'amount':'25','receipt_number':'FTF-TEST-001'})
    payment=db.session.scalar(db.select(Payment));assert payment.payment_method=='Cash (in person)' and payment.amount==25
    staff.post(prefix+'/generate');db.session.refresh(item)
    assert item.status=='READY_FOR_PRINTING' and item.issued_document.snapshot['receipt_number']=='FTF-TEST-001'
    assert item.issued_document.snapshot['fee']=='25.00'


def test_approval_cannot_skip_id_checks_or_authorization(system):
    resident,item,client,staff,checks=initial_request(system);prefix=f'/official/document-requests/{item.id}'
    assert client.post(prefix+'/approve',data=checks).status_code==403
    staff.post(prefix+'/approve',data={'signatory_id':checks['signatory_id']});db.session.refresh(item);assert item.status=='PENDING'
    filename=resident.philsys_card_filename;resident.philsys_card_filename=None;db.session.commit()
    staff.post(prefix+'/approve',data=checks);db.session.refresh(item);assert item.status=='PENDING'
    resident.philsys_card_filename='../'+filename;db.session.commit()
    staff.post(prefix+'/approve',data=checks);db.session.refresh(item);assert item.status=='PENDING'
    resident.philsys_card_filename=filename;db.session.commit();staff.post(prefix+'/approve',data=checks)
    db.session.refresh(item);assert item.status=='APPROVED'
    resident.philsys_card_filename=None;db.session.commit()
    response=staff.post(prefix+'/prepare',data=dict(details(resident,'SCN-CLR'),description='Employment',confirm_details='yes'),follow_redirects=True)
    assert b'changed after verification' in response.data and item.additional_data=={}
    resident.philsys_card_filename=filename;resident.address_line='Updated verified address';db.session.commit()
    staff.post(prefix+'/approve',data=dict(checks,reverify='yes'));db.session.refresh(item)
    assert item.status=='APPROVED'
    response=staff.post(prefix+'/prepare',data=dict(details(resident,'SCN-CLR'),description='Employment',confirm_details='yes'),follow_redirects=True)
    assert b'Certificate information saved' in response.data


def test_approval_requires_csrf(system):
    resident,item,client,staff,checks=initial_request(system)
    system.config['WTF_CSRF_ENABLED']=True
    assert staff.post(f'/official/document-requests/{item.id}/approve',data=checks).status_code==400
    db.session.refresh(item);assert item.status=='PENDING'


def test_print_approved_request_without_prepare_fields(system):
    resident,item,client,staff,checks=initial_request(system);prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/approve',data=checks)
    page=staff.get(prefix).data
    assert b'Print document' in page and b'Prepare certificate' not in page and b'name="detail_' not in page
    staff.post(prefix+'/receipt',data={'amount':'25','receipt_number':'FTF-PRINT-001'})
    response=staff.post(prefix+'/print')
    assert response.status_code==302 and response.location.endswith('/preview?print=1')
    db.session.refresh(item);assert item.status=='READY_FOR_PRINTING' and item.additional_data=={} and item.description is None
    snapshot=item.issued_document.snapshot
    assert snapshot['full_name'].startswith('Maria') and resident.last_name in snapshot['full_name']
    assert snapshot['purpose']=='' and snapshot['signatory_name']==item.signatory.full_name
    certificate=staff.get(prefix+'/certificate');assert certificate.status_code==200
    assert resident.first_name.encode() in certificate.data
    assert "frame-ancestors 'self'" in certificate.headers['Content-Security-Policy']
    assert certificate.headers['X-Frame-Options']=='SAMEORIGIN'
    assert "frame-ancestors 'none'" in staff.get(prefix).headers['Content-Security-Policy']
    assert b'CTC-123' not in certificate.data
    number=item.issued_document.document_number
    staff.post(prefix+'/print');db.session.refresh(item)
    assert item.issued_document.document_number==number and item.status=='READY_FOR_PRINTING'
    assert client.post(prefix+'/print').status_code==403
    assert login(system,'other-test').post(prefix+'/print').status_code==403


def test_direct_print_still_requires_approved_and_unchanged_review(system):
    resident,item,client,staff,checks=initial_request(system);prefix=f'/official/document-requests/{item.id}'
    assert staff.post(prefix+'/print').status_code==404
    db.session.refresh(item);assert item.status=='PENDING' and item.issued_document is None
    staff.post(prefix+'/approve',data=checks)
    resident.address_line='Changed after approval';db.session.commit()
    response=staff.post(prefix+'/print',follow_redirects=True)
    assert b'changed after verification' in response.data
    db.session.refresh(item);assert item.status=='APPROVED' and item.issued_document is None


def test_direct_print_with_unconfirmed_fee_has_blank_payment_and_release_waits(system):
    from app.models import FeeConfiguration
    resident,item,client,staff,checks=initial_request(system);prefix=f'/official/document-requests/{item.id}'
    item.document_type.base_fee=0
    db.session.execute(db.delete(FeeConfiguration).where(FeeConfiguration.document_type_id==item.document_type_id));db.session.commit()
    staff.post(prefix+'/approve',data=checks)
    response=staff.post(prefix+'/print');assert response.location.endswith('/preview?print=1')
    db.session.refresh(item);assert item.status=='READY_FOR_PRINTING'
    snapshot=item.issued_document.snapshot
    assert snapshot['fee']=='' and snapshot['receipt_number']=='' and snapshot['receipt_date']=='' and snapshot['payment_pending']
    assert b'Confirm the actual document fee before printing' not in staff.get(prefix).data
    assert b'Record in-person payment' in staff.get(prefix).data
    staff.post(prefix+'/printed')
    response=staff.post(prefix+'/release',follow_redirects=True);assert b'Confirm the actual fee before release' in response.data
    db.session.refresh(item);assert item.status=='PRINTED' and item.issued_document.status=='printed'
    from datetime import date
    db.session.add(FeeConfiguration(document_type_id=item.document_type_id,amount=25,effective_from=date(2020,1,1),status='active'));db.session.commit()
    response=staff.post(prefix+'/release',follow_redirects=True);assert b'actual in-person payment' in response.data
    staff.post(prefix+'/receipt',data={'amount':'25','receipt_number':'LATE-FTF-001'})
    staff.post(prefix+'/release');db.session.refresh(item);assert item.status=='RELEASED'
    assert snapshot['receipt_number']==''  # The already printed paper remains unchanged.


def test_direct_print_with_confirmed_fee_can_precede_cash_payment(system):
    resident,item,client,staff,checks=initial_request(system);prefix=f'/official/document-requests/{item.id}'
    staff.post(prefix+'/approve',data=checks);response=staff.post(prefix+'/print')
    assert response.location.endswith('/preview?print=1')
    db.session.refresh(item);assert item.status=='READY_FOR_PRINTING' and not item.payments
    assert item.issued_document.snapshot['fee']=='' and item.issued_document.snapshot['payment_pending']
