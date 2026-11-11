"""Staff-assisted document intake with the standard review and issuance workflow."""
from datetime import datetime
from uuid import uuid4
from flask import request, render_template, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import or_
from app.official import official_bp
from app.auth.decorators import official_account_required
from app.permissions import permission_required
from app.extensions import db
from app.models import Resident, Request, DocumentRequirement, DocumentRequestEvent
from app.documents.workflow import ensure_catalog, requirement_names
from app.documents.engine import TEMPLATE_CODES, DETAIL_FIELDS, template_code
from app.operations_common import text_field
from app.image_uploads import save_image, remove_image

@official_bp.route('/document-requests/walk-in',methods=['GET','POST'])
@official_account_required
@permission_required('documents.review')
def document_walk_in():
    document_types=[dt for dt in ensure_catalog() if dt.status=='active' and (dt.template_code or TEMPLATE_CODES.get(dt.code)) in DETAIL_FIELDS]
    selected_id=request.values.get('resident_id',type=int)
    resident=db.session.get(Resident,selected_id) if selected_id else None
    search=request.args.get('q','').strip()[:100]
    query=db.select(Resident).where(Resident.status=='active')
    if search:
        for word in search.split():query=query.where(or_(Resident.first_name.ilike('%'+word+'%'),Resident.last_name.ilike('%'+word+'%'),Resident.middle_name.ilike('%'+word+'%')))
    residents=db.session.scalars(query.order_by(Resident.last_name,Resident.first_name).limit(50)).all()
    if resident and resident.status=='active' and resident not in residents: residents.insert(0,resident)
    filename=None
    if request.method=='POST':
        try:
            if not resident or resident.status!='active': raise ValueError('Select an active resident record. Register a new resident first if needed.')
            document_type=next((d for d in document_types if d.id==request.form.get('document_type_id',type=int)),None)
            if not document_type:raise ValueError('Select an active document with a configured print template.')
            purpose=text_field(request.form,'description',500)
            item=Request(request_number='REQ-'+datetime.now().strftime('%Y%m%d')+'-'+uuid4().hex[:8].upper(),resident_id=resident.id,document_type_id=document_type.id,service_type=document_type.name,description=purpose,status='PENDING',additional_data={'intake_channel':'WALK_IN'})
            db.session.add(item);db.session.flush()
            names=requirement_names(template_code(document_type),{},resident)
            upload=request.files.get('id_image')
            if upload and upload.filename:filename=save_image(upload,'document_requirements')
            for name in names:
                is_id=name in {'Valid government-issued ID','Valid ID or proof of identity','Valid ID of owner / operator'}
                db.session.add(DocumentRequirement(request_id=item.id,requirement_name=name,status='uploaded' if filename and is_id else 'pending',filename=filename if is_id else None,is_required=True))
            if filename and not any(n in {'Valid government-issued ID','Valid ID or proof of identity','Valid ID of owner / operator'} for n in names):raise ValueError('This document has no ID upload requirement.')
            db.session.add(DocumentRequestEvent(request_id=item.id,to_status='PENDING',changed_by_id=current_user.id,notes='Walk-in application recorded by barangay staff. Payment is face-to-face.'))
            from app.audit import record
            record('WALK_IN_DOCUMENT_CREATE','documents','Request',item.id,'Staff recorded walk-in document application')
            from app.notifications import notify_officials
            notify_officials('New walk-in document request',f'{item.request_number} is waiting for review.')
            db.session.commit();flash('Walk-in request recorded. Review the information and requirements before approval.','success')
            return redirect(url_for('official.document_request_detail',request_id=item.id))
        except ValueError as error:
            db.session.rollback()
            if filename:remove_image('document_requirements',filename)
            flash(str(error),'danger')
    return render_template('official/document_walk_in.html',residents=residents,selected_resident=resident,document_types=document_types,search=search)


@official_bp.post('/document-requests/<int:request_id>/walk-in-edit')
@official_account_required
@permission_required('documents.review')
def document_walk_in_edit(request_id):
    from app.documents.routes import locked_request
    item=locked_request(request_id)
    try:
        if (item.additional_data or {}).get('intake_channel')!='WALK_IN' or item.status not in {'PENDING','UNDER_REVIEW','NEEDS_CORRECTION'}:raise ValueError('Only a walk-in request awaiting approval can be edited.')
        item.description=text_field(request.form,'description',500)
        item.verified_at=None;item.verified_by_id=None;item.verification_digest=None
        db.session.add(DocumentRequestEvent(request_id=item.id,from_status=item.status,to_status=item.status,changed_by_id=current_user.id,notes='Walk-in purpose corrected; approval checks must be repeated.'))
        db.session.commit();flash('Walk-in purpose updated. Review the request before approval.','success')
    except ValueError as error:db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('official.document_request_detail',request_id=item.id))
