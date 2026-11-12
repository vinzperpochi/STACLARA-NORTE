"""Authorized review, original document output and administration routes."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from sqlalchemy import select
from app.extensions import db
from app.auth.decorators import official_account_required, roles_required, resident_owner_required
from app.models import DocumentSignatory, DocumentType, DocumentRequirement, DocumentRequestEvent, IssuedDocument, Payment, Request, Resident
from app.official import official_bp
from app.resident import resident_bp, current_user_resident
from .engine import DETAIL_FIELDS, CHECKLISTS, active_signatories, template_code, resident_data, fields_for, validate_details, render_original, pdf_bytes, configured_fee, verification_digest
from .workflow import transition_request, generate_document, evidence_available


def verify_review(item):
    code=template_code(item.document_type)
    if not all(request.form.get('check_'+str(i))=='yes' for i in range(len(CHECKLISTS[code])+1)):
        raise ValueError('Confirm resident information and each eligibility check before approval.')
    for evidence in item.active_requirements:
        checked=request.form.get('evidence_'+str(evidence.id))=='yes'
        if evidence.is_required and (not evidence_available(evidence) or not checked):
            raise ValueError('View and confirm each required ID or supporting image before approval.')
        if evidence_available(evidence) and checked: evidence.status='verified'
    item.signatory_id=request.form.get('signatory_id',type=int)
    db.session.flush();db.session.expire(item,['signatory'])
    if item.signatory not in active_signatories(): raise ValueError('Select an active authorized issuing signatory.')
    notes=request.form.get('verification_notes','').strip() or 'Resident records, uploaded ID and eligibility reviewed by the approving official.'
    if len(notes)>2000: raise ValueError('Verification notes must not exceed 2000 characters.')
    item.verified_by_id=current_user.id;item.verified_at=datetime.now(timezone.utc);item.verification_notes=notes
    item.verification_digest=verification_digest(item)


@official_bp.post('/document-requests/<int:request_id>/approve')
@official_account_required
def document_approve(request_id):
    item=locked_request(request_id)
    try:
        reverify=item.status=='APPROVED' and request.form.get('reverify')=='yes'
        if item.status not in {'PENDING','UNDER_REVIEW','PROCESSING'} and not reverify: raise ValueError('This request is no longer awaiting approval.')
        verify_review(item)
        if item.status=='PENDING': transition_request(item,'UNDER_REVIEW',current_user,'Review completed during approval.')
        if not reverify: transition_request(item,'APPROVED',current_user,item.verification_notes,approval_only=True)
        else:
            from .workflow import validate_approval
            validate_approval(item,require_complete=False)
        audit(item,'DOCUMENT_APPROVED','ID and eligibility reviewed; payment is in person at the barangay.');db.session.commit()
        flash('Request approved. Payment is in person at the barangay before certificate issuance.','success')
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('official.document_request_detail',request_id=request_id))


@official_bp.post('/document-requests/<int:request_id>/print')
@official_account_required
def document_print(request_id):
    item=locked_request(request_id)
    try:
        if item.status=='APPROVED':
            generate_document(item,current_user,allow_blank_fields=True)
            audit(item,'DOCUMENT_PRINT_PREVIEW','Approved certificate prepared from saved resident information; missing supplemental fields remain blank.')
            db.session.commit()
        issued_request(request_id)
        return redirect(url_for('official.document_preview',request_id=request_id,print=1))
    except ValueError as error:
        db.session.rollback();flash(str(error),'danger')
        return redirect(url_for('official.document_request_detail',request_id=request_id))


@official_bp.post('/document-requests/<int:request_id>/prepare')
@official_account_required
def document_prepare(request_id):
    item=locked_request(request_id)
    try:
        if item.status!='APPROVED': raise ValueError('Approve this request before preparing the certificate.')
        from .workflow import validate_approval
        validate_approval(item, require_complete=False)
        if request.form.get('confirm_details')!='yes': raise ValueError('Confirm the certificate information against the records.')
        values=validate_details(item.resident,template_code(item.document_type),request.form)
        purpose=request.form.get('description','').strip()
        if len(purpose)>2000 or (not purpose and template_code(item.document_type) not in {'SCN-BIZ','SCN-SPE'}): raise ValueError('Enter the actual purpose (up to 2000 characters).')
        item.additional_data=values;item.description=purpose or None
        item.verified_by_id=current_user.id;item.verified_at=datetime.now(timezone.utc)
        item.verification_digest=verification_digest(item)
        audit(item,'DOCUMENT_PREPARED','Certificate details confirmed by the official.');db.session.commit();flash('Certificate information saved.','success')
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('official.document_request_detail',request_id=request_id))

def locked_request(identity):
    item=db.session.scalar(select(Request).where(Request.id==identity,Request.document_type_id.is_not(None)).with_for_update())
    if item is None: abort(404)
    return item

def audit(item,action,notes):
    db.session.add(DocumentRequestEvent(request_id=item.id,from_status=item.status,to_status=item.status,changed_by_id=current_user.id,notes=action+': '+notes))
    from app.audit import record
    record(action,'documents','Request',item.id,notes)

@official_bp.post('/document-requests/<int:request_id>/verify')
@official_account_required
def document_verify(request_id):
    item=locked_request(request_id)
    try:
        if item.status not in {'UNDER_REVIEW','PROCESSING'}: raise ValueError('Begin review before verifying this request.')
        code=template_code(item.document_type)
        if not all(request.form.get('check_'+str(i))=='yes' for i in range(len(CHECKLISTS[code])+1)): raise ValueError('Confirm registered information and every document-specific verification check.')
        for evidence in item.active_requirements:
            if evidence.is_required and (not evidence_available(evidence) or request.form.get('evidence_'+str(evidence.id))!='yes'): raise ValueError('View and verify every required uploaded image.')
            if evidence_available(evidence) and request.form.get('evidence_'+str(evidence.id))=='yes': evidence.status='verified'
        validate_details(item.resident,code,{'detail_'+k:v for k,v in (item.additional_data or {}).items()})
        notes=request.form.get('verification_notes','').strip()
        if not notes or len(notes)>2000: raise ValueError('Enter verification findings (up to 2000 characters).')
        item.signatory_id=request.form.get('signatory_id',type=int)
        db.session.flush();db.session.expire(item,['signatory'])
        if item.signatory not in active_signatories(): raise ValueError('Select an active authorized issuing signatory.')
        item.verified_by_id=current_user.id;item.verified_at=datetime.now(timezone.utc);item.verification_notes=notes
        item.verification_digest=verification_digest(item)
        audit(item,'DOCUMENT_VERIFIED',notes);db.session.commit();flash('Information, requirements and eligibility verified. You can now approve.','success')
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('official.document_request_detail',request_id=request_id))

def issued_request(identity):
    item=db.get_or_404(Request,identity)
    if not item.issued_document or not item.generated_filename: abort(404)
    if item.status not in {'READY_FOR_PRINTING','PRINTED','RELEASED','READY_FOR_RELEASE'} or item.issued_document.status=='revoked': abort(403)
    return item

def artifact_content(item):
    filename=item.generated_filename
    if Path(filename).name!=filename: abort(404)
    path=Path(current_app.config['STORAGE_ROOT'])/'generated_documents'/filename
    if path.is_file():
        return path.read_text(encoding='utf-8')
    if item.issued_document.snapshot:
        return render_original(template_code(item.document_type), item.issued_document.snapshot)
    abort(404)

@official_bp.get('/document-requests/<int:request_id>/preview')
@official_account_required
def document_preview(request_id):
    item=issued_request(request_id)
    return render_template('documents/preview.html', item=item,
        title=item.issued_document.document_number,
        frame_url=url_for('official.document_certificate', request_id=item.id),
        browser_pdf=current_app.config.get('DOCUMENT_BROWSER_PDF'),
        download_now=request.args.get('pdf')=='1', print_now=request.args.get('print')=='1')

@official_bp.get('/document-requests/<int:request_id>/certificate')
@official_account_required
def document_certificate(request_id):
    item=issued_request(request_id)
    response=current_app.response_class(artifact_content(item),mimetype='text/html');response.headers['Cache-Control']='private, no-store'
    return response

@official_bp.get('/document-requests/<int:request_id>/pdf')
@official_account_required
def document_pdf(request_id):
    item=issued_request(request_id)
    if current_app.config.get('DOCUMENT_BROWSER_PDF'):
        return redirect(url_for('official.document_preview', request_id=item.id, pdf=1))
    try:
        directory=Path(current_app.config['STORAGE_ROOT'])/'generated_documents'
        doc=item.issued_document
        if doc.pdf_filename and Path(doc.pdf_filename).name==doc.pdf_filename and (directory/doc.pdf_filename).is_file():
            result=(directory/doc.pdf_filename).read_bytes()
        else:
            result=pdf_bytes(artifact_content(item))
            doc.pdf_filename=doc.document_number+'-'+uuid4().hex+'.pdf'
            (directory/doc.pdf_filename).write_bytes(result)
        audit(item,'DOCUMENT_PDF','Official A4 PDF exported');db.session.commit()
        response=send_file(BytesIO(result),mimetype='application/pdf',as_attachment=True,download_name=item.issued_document.document_number+'.pdf')
        response.headers['Cache-Control']='private, no-store';return response
    except ValueError as error:
        db.session.rollback();flash(str(error),'danger');return redirect(url_for('official.document_request_detail',request_id=request_id))

@official_bp.get('/document-requests/<int:request_id>/application')
@official_account_required
def document_application(request_id):
    item=db.get_or_404(Request,request_id);code=template_code(item.document_type)
    if item.issued_document and item.issued_document.snapshot: data=item.issued_document.snapshot
    else:
        data=resident_data(item.resident);data.update({k:v for k,v in (item.additional_data or {}).items() if not data.get(k)});data.update(purpose=item.description or '',date_received=item.created_at.strftime('%m/%d/%Y'))
    return current_app.response_class(render_original(code,data,'application'),mimetype='text/html',headers={'Cache-Control':'private, no-store'})


@official_bp.get('/document-requests/<int:request_id>/application-preview')
@official_account_required
def document_application_preview(request_id):
    item = db.get_or_404(Request, request_id)
    if not item.document_type:
        abort(404)
    return render_template('documents/preview.html', item=item, application=True,
        title=f'{item.request_number}-application',
        frame_url=url_for('official.document_application', request_id=item.id),
        browser_pdf=True)

@official_bp.post('/document-requests/<int:request_id>/printed')
@official_account_required
def document_printed(request_id):
    item=locked_request(request_id)
    try:
        issued_request(request_id)
        if item.status=='RELEASED': audit(item,'DOCUMENT_REPRINT','Official confirmed reprinting of the released certificate.')
        else:
            transition_request(item,'PRINTED',current_user,'Official confirmed printing of the certificate.');item.issued_document.status='printed'
        db.session.commit();flash('Printing recorded.','success')
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('official.document_request_detail',request_id=request_id))

@official_bp.post('/document-requests/<int:request_id>/receipt')
@official_account_required
def document_receipt(request_id):
    item=locked_request(request_id)
    try:
        if item.status not in {'UNDER_REVIEW','PROCESSING','APPROVED','READY_FOR_PRINTING','PRINTED','READY_FOR_RELEASE'}: raise ValueError('Record the actual in-person payment before release.')
        amount=Decimal(request.form.get('amount',''))
        number=request.form.get('receipt_number','').strip()
        if not amount.is_finite() or amount<0 or amount>999999999 or not number or len(number)>50: raise ValueError('Enter a valid amount and actual official receipt number.')
        payment=Payment(receipt_number=number,resident_id=item.resident_id,request_id=item.id,amount=amount,payment_method='Cash (in person)',paid_at=datetime.now(timezone.utc),status='paid')
        db.session.add(payment);audit(item,'DOCUMENT_PAYMENT','Actual official receipt recorded');db.session.commit();flash('Payment recorded.','success')
    except (ValueError,InvalidOperation) as error: db.session.rollback();flash(str(error),'danger')
    except Exception:
        db.session.rollback();flash('Receipt could not be saved. Check whether the receipt number is already recorded.','danger')
    return redirect(url_for('official.document_request_detail',request_id=request_id))

@official_bp.post('/document-requests/<int:request_id>/revoke')
@roles_required('System Administrator')
def document_revoke(request_id):
    item=locked_request(request_id)
    notes=request.form.get('notes','').strip()
    if not item.issued_document or not notes or len(notes)>2000: abort(400)
    item.issued_document.status='revoked';item.issued_document.revoked_at=datetime.now(timezone.utc);item.issued_document.revocation_reason=notes
    audit(item,'DOCUMENT_REVOKED',notes);db.session.commit();flash('Certificate revoked.','success')
    return redirect(url_for('official.document_request_detail',request_id=request_id))

@official_bp.route('/document-settings',methods=['GET','POST'])
@roles_required('System Administrator')
def document_settings():
    from .workflow import ensure_catalog
    ensure_catalog()
    if request.method=='POST':
        try:
            if request.form.get('action')=='signatory':
                name=request.form.get('full_name','').strip();designation=request.form.get('designation','').strip()
                if not name or len(name)>200 or not designation or len(designation)>100: raise ValueError('Enter the approved name and designation.')
                start=date.fromisoformat(request.form.get('effective_from',''))
                end=date.fromisoformat(request.form['effective_until']) if request.form.get('effective_until') else None
                if end and end<start: raise ValueError('End date must follow the start date.')
                db.session.add(DocumentSignatory(full_name=name,designation=designation,authorized_by_id=current_user.id,effective_from=start,effective_until=end,status='active'))
            elif request.form.get('action')=='archive':
                signatory=db.get_or_404(DocumentSignatory,request.form.get('signatory_id',type=int));signatory.status='inactive'
            elif request.form.get('action')=='template':
                dt=db.get_or_404(DocumentType,request.form.get('type_id',type=int));code=request.form.get('template_code')
                if code not in DETAIL_FIELDS: raise ValueError('Choose one of the seven original templates.')
                if db.session.scalar(select(Request.id).where(Request.document_type_id==dt.id)) and template_code(dt)!=code: raise ValueError('A type with existing requests cannot be reassigned to a different certificate.')
                dt.template_code=code;dt.status='active' if request.form.get('active') else 'inactive'
            else: raise ValueError('Invalid settings action.')
            db.session.commit();flash('Document settings saved.','success')
        except ValueError as error: db.session.rollback();flash(str(error),'danger')
        return redirect(url_for('official.document_settings'))
    from app.pagination import paginate_named
    signatory_pagination=paginate_named(select(DocumentSignatory).order_by(DocumentSignatory.id.desc()),'signatories_page')
    type_pagination=paginate_named(select(DocumentType).order_by(DocumentType.name,DocumentType.id),'types_page')
    return render_template('documents/settings.html',signatories=signatory_pagination.items,types=type_pagination.items,
        signatory_pagination=signatory_pagination,type_pagination=type_pagination,codes=DETAIL_FIELDS,today=date.today())

@resident_bp.route('/documents/<int:request_id>/correction',methods=['GET','POST'])
@resident_owner_required
def document_correction(request_id):
    resident=current_user_resident();item=db.session.scalar(select(Request).where(Request.id==request_id,Request.resident_id==resident.id).with_for_update())
    if not item: abort(404)
    if item.status!='NEEDS_CORRECTION': abort(403)
    code=template_code(item.document_type)
    if request.method=='POST':
        try:
            item.additional_data=validate_details(resident,code,request.form)
            purpose=request.form.get('description','').strip()
            if not purpose or len(purpose)>500: raise ValueError('Enter a purpose up to 500 characters.')
            item.description=purpose;item.verified_by_id=None;item.verified_at=None;item.verification_notes=None
            for evidence in item.active_requirements:
                if evidence.filename: evidence.status='uploaded'
            transition_request(item,'PENDING',current_user,'Resident submitted corrected information.')
            from app.notifications import notify_officials
            notify_officials('Document correction submitted', f'Request {item.request_number} has corrected information ready for review.')
            db.session.commit()
            return redirect(url_for('resident.document_request_detail',request_id=item.id))
        except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return render_template('documents/correction.html',item=item,fields=fields_for(resident,code),data=resident_data(resident))
