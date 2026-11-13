"""Authenticated incident submission, restricted review and documented referrals."""
from datetime import date, datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import re
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import select, func, or_
from app.extensions import db
from app.auth.decorators import resident_owner_required, official_account_required, roles_required
from app.models import ResidentComplaint, IncidentCategory, IncidentRoutingRule, GovernmentAgency, AgencyHotline, HotlineVerification, EmergencyIncident, ComplaintAssignment, ComplaintReferral, ComplaintEvidence, ComplaintStatusHistory, User, Role
from app.image_uploads import prepare_image
from app.operations_common import text_field, export_report
from .service import ensure_directory, classify, contacts, admin, can_view, can_review, audit, notify, transition, TRANSITIONS, STATUSES

incidents_bp=Blueprint('incidents',__name__,url_prefix='/incidents')
admin_required=roles_required('System Administrator')


def layout(): return 'admin/_admin_base.html' if admin() else ('official/_official_base.html' if any(r.name=='Barangay Official' for r in current_user.roles) else 'resident/_portal_base.html')


def owned(item_id):
    item=db.get_or_404(ResidentComplaint,item_id)
    if not can_view(item): abort(404)
    return item


def visible_query():
    query=select(ResidentComplaint)
    if admin(): return query
    if any(r.name=='Barangay Official' for r in current_user.roles):
        assigned=select(ComplaintAssignment.complaint_id).where(ComplaintAssignment.user_id==current_user.id,ComplaintAssignment.active.is_(True))
        from app.models import PersonnelProfile
        personnel=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.user_id==current_user.id))
        if personnel and personnel.personnel_type=='Staff': return query.where(ResidentComplaint.id.in_(assigned))
        return query.where(or_(ResidentComplaint.restricted.is_(False),ResidentComplaint.id.in_(assigned)))
    if current_user.resident: return query.where(ResidentComplaint.resident_id==current_user.resident.id)
    abort(403)


def save_evidence(upload):
    if upload.mimetype in {'image/jpeg','image/png'}:
        filename, data = prepare_image(upload, 'incident_evidence')
        return filename, upload.mimetype, data
    if Path(upload.filename or '').suffix.lower()!='.pdf' or upload.mimetype!='application/pdf': raise ValueError('Evidence must be JPEG, PNG or PDF.')
    data=upload.stream.read(5*1024*1024+1)
    if not data.startswith(b'%PDF-') or len(data)>5*1024*1024: raise ValueError('PDF must be valid and no larger than 5 MB.')
    from pypdf import PdfReader, PdfWriter
    try:
        reader=PdfReader(BytesIO(data),strict=True)
        if reader.is_encrypted or not 1<=len(reader.pages)<=50: raise ValueError('Use an unencrypted PDF with 1â€“50 pages.')
        # Copy pages only; remove annotations/actions/forms and embedded files.
        writer=PdfWriter()
        for page in reader.pages:
            for key in ['/Annots','/AA','/Dur','/Trans']: page.pop(key,None)
            writer.add_page(page)
        output=BytesIO();writer.write(output)
    except Exception as error: raise ValueError('Unable to validate this PDF. Upload a standard PDF or image.') from error
    return uuid4().hex + '.pdf', 'application/pdf', output.getvalue()


@incidents_bp.route('/submit',methods=['GET','POST'])
@resident_owner_required
def submit():
    ensure_directory();db.session.commit()
    if request.method=='POST':
        try:
            resident=current_user.resident
            count=db.session.scalar(select(func.count(ResidentComplaint.id)).where(ResidentComplaint.resident_id==resident.id,ResidentComplaint.created_at>=datetime.now(timezone.utc)-timedelta(minutes=1)))
            if count>=5: raise ValueError('You have submitted several reports. For immediate danger, use the emergency call options; otherwise wait a minute before submitting again.')
            title=text_field(request.form,'title',200);description=text_field(request.form,'description',10000);location=text_field(request.form,'location',255)
            urgency=request.form.get('urgency','normal')
            if urgency not in {'normal','urgent','emergency'}: raise ValueError('Select a valid urgency.')
            category=db.session.scalar(select(IncidentCategory).where(IncidentCategory.code==request.form.get('category'),IncidentCategory.active.is_(True)))
            if not category: raise ValueError('Select an active incident category.')
            local=datetime.fromisoformat(request.form.get('incident_at',''))
            from app.attendance.service import MANILA
            occurred=local.replace(tzinfo=MANILA).astimezone(timezone.utc)
            if occurred>datetime.now(timezone.utc)+timedelta(minutes=2): raise ValueError('Incident time cannot be in the future.')
            danger=request.form.get('immediate_danger')=='yes';external=request.form.get('external_review')=='yes'
            routing=classify(category.code,description,urgency,danger,external)
            latitude=longitude=None
            if request.form.get('latitude') or request.form.get('longitude'):
                latitude=float(request.form['latitude']);longitude=float(request.form['longitude'])
                if not (-90<=latitude<=90 and -180<=longitude<=180): raise ValueError('Enter valid location coordinates.')
            case_id=None
            if request.form.get('blotter_case_id'):
                from app.models import BlotterCase
                case=db.get_or_404(BlotterCase,int(request.form['blotter_case_id']))
                if case.complainant_id!=resident.id: abort(404)
                case_id=case.id
            item=ResidentComplaint(resident_id=resident.id,blotter_case_id=case_id,reference='INC-'+uuid4().hex[:20].upper(),title=title,category_id=category.id,description=description,incident_at=occurred,location=location,latitude=latitude,longitude=longitude,urgency=urgency,immediate_danger=danger,classification=routing['classification'],routing_snapshot=routing,restricted=routing['restricted'])
            db.session.add(item);db.session.flush();item.reference=f'INC-{item.id:08d}'
            uploads=[u for u in request.files.getlist('evidence') if u.filename]
            if len(uploads)>4: raise ValueError('Attach at most four evidence files.')
            total_limit = current_app.config.get('INCIDENT_EVIDENCE_TOTAL_BYTES')
            if total_limit:
                total_bytes = 0
                for upload in uploads:
                    total_bytes += upload.stream.seek(0, 2)
                    upload.stream.seek(0)
                if total_bytes > total_limit:
                    raise ValueError('Combined evidence files must be 4 MB or smaller.')
            for upload in uploads:
                filename, mime, data = save_evidence(upload)
                if total_limit and len(data) > total_limit:
                    raise ValueError('A processed evidence file exceeds 4 MB. Please choose a smaller file.')
                db.session.add(ComplaintEvidence(
                    complaint_id=item.id, filename=filename, mime_type=mime,
                    file_data=data, original_name=Path(upload.filename).name[:200],
                    uploaded_by_id=current_user.id,
                ))
            if routing['classification']=='EMERGENCY': db.session.add(EmergencyIncident(complaint_id=item.id))
            db.session.add(ComplaintStatusHistory(complaint_id=item.id,actor_id=current_user.id,to_status='SUBMITTED',public_response='Report received by the barangay system. Emergency response is not confirmed.'))
            audit(item,'SUBMITTED',current_user,'Routing recommendation saved with rule/version; no external transmission')
            notify(item,'Incident report submitted',f'{item.reference} is awaiting authorized review.')
            notify(item,'Urgent incident needs review' if item.classification=='EMERGENCY' else 'New complaint needs review',f'{item.reference} is available in Complaints & Incidents.',True)
            db.session.commit();flash('Report submitted. For immediate danger, call emergency services without waiting for a reply.','success')
            return redirect(url_for('incidents.detail',complaint_id=item.id))
        except (ValueError,KeyError) as error:
            db.session.rollback()
            flash(str(error),'danger')
        except Exception:
            db.session.rollback()
            raise
    from app.attendance.service import MANILA
    return render_template('incidents/submit.html',categories=db.session.scalars(select(IncidentCategory).where(IncidentCategory.active.is_(True)).order_by(IncidentCategory.id)).all(),resident=current_user.resident,current_time=datetime.now(MANILA).strftime('%Y-%m-%dT%H:%M'),emergency=request.args.get('emergency')=='1')


@incidents_bp.post('/classify')
@resident_owner_required
def classification():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): abort(400)
    ensure_directory()
    result=classify(str(data.get('category','UNKNOWN'))[:40],str(data.get('description',''))[:10000],str(data.get('urgency','normal'))[:20],data.get('immediate_danger') is True,data.get('external_review') is True)
    db.session.commit();return jsonify(success=True,data=result)


@incidents_bp.get('/')
@roles_required('Resident','Barangay Official','System Administrator')
def dashboard():
    query=visible_query();status=request.args.get('status');q=request.args.get('q','')[:100]
    if status: query=query.where(ResidentComplaint.status==status)
    if q: query=query.where(or_(ResidentComplaint.reference.ilike('%'+q+'%'),ResidentComplaint.title.ilike('%'+q+'%')))
    if request.args.get('emergency')=='1': query=query.where(ResidentComplaint.classification=='EMERGENCY')
    if request.args.get('assigned')=='1': query=query.where(ResidentComplaint.id.in_(select(ComplaintAssignment.complaint_id).where(ComplaintAssignment.user_id==current_user.id,ComplaintAssignment.active.is_(True))))
    all_visible=db.session.scalars(visible_query()).all()
    from app.pagination import paginate_named
    pagination=paginate_named(query.order_by((ResidentComplaint.classification=='EMERGENCY').desc(),ResidentComplaint.created_at.desc()))
    items=pagination.items
    stats={'Total complaints':len(all_visible),'Pending':sum(c.status=='SUBMITTED' for c in all_visible),'Active emergencies':sum(c.classification=='EMERGENCY' and c.status not in {'RESOLVED','CLOSED'} for c in all_visible),'Investigating':sum(c.status=='UNDER_INVESTIGATION' for c in all_visible),'Referrals':sum(len(c.referrals) for c in all_visible),'Resolved':sum(c.status in {'RESOLVED','CLOSED'} for c in all_visible)}
    resolved=[(c.resolved_at.replace(tzinfo=timezone.utc)-c.created_at.replace(tzinfo=timezone.utc)).total_seconds()/86400 for c in all_visible if c.resolved_at]
    category_counts={c.category.name:sum(v.category_id==c.category_id for v in all_visible) for c in all_visible}
    return render_template('incidents/dashboard.html',base=layout(),items=items,stats=stats,statuses=STATUSES,pagination=pagination,reviewer=any(r.name in {'Barangay Official','System Administrator'} for r in current_user.roles),category_counts=category_counts,average_days=round(sum(resolved)/len(resolved),1) if resolved else None)


@incidents_bp.get('/<int:complaint_id>')
@roles_required('Resident','Barangay Official','System Administrator')
def detail(complaint_id):
    item=owned(complaint_id);reviewer=can_review(item)
    if reviewer: audit(item,'VIEW',current_user,'Private incident viewed');db.session.commit()
    users=db.session.scalars(select(User).join(User.roles).where(Role.name.in_(['Barangay Official','System Administrator']),User.is_active.is_(True),User.status=='active').distinct()).all() if admin() else []
    return render_template('incidents/detail.html',base=layout(),item=item,reviewer=reviewer,manage=admin(),next_statuses=sorted(TRANSITIONS.get(item.status,set())),agencies=db.session.scalars(select(GovernmentAgency).where(GovernmentAgency.active.is_(True))).all(),users=users,live_contacts=contacts(item.routing_snapshot.get('agency_codes',[])))


@incidents_bp.post('/<int:complaint_id>/status')
@official_account_required
def update_status(complaint_id):
    item=owned(complaint_id)
    if not can_review(item): abort(403)
    try:
        transition(item,request.form.get('status'),current_user,text_field(request.form,'public_response',3000),text_field(request.form,'private_notes',5000,False));db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('incidents.detail',complaint_id=item.id))


@incidents_bp.post('/<int:complaint_id>/follow-up')
@resident_owner_required
def follow_up(complaint_id):
    item=owned(complaint_id)
    if item.resident_id!=current_user.resident.id: abort(404)
    try:
        if item.status=='CLOSED': raise ValueError('Contact the barangay to request reopening before adding a follow-up.')
        message=text_field(request.form,'message',3000)
        db.session.add(ComplaintStatusHistory(complaint_id=item.id,actor_id=current_user.id,from_status=item.status,to_status=item.status,public_response='Resident follow-up: '+message))
        audit(item,'RESIDENT_FOLLOW_UP',current_user,'Resident follow-up added')
        notify(item,'Incident follow-up received',f'{item.reference} has a resident follow-up.',True);db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('incidents.detail',complaint_id=item.id))


@incidents_bp.post('/<int:complaint_id>/response-status')
@official_account_required
def response_status(complaint_id):
    item=owned(complaint_id)
    if not can_review(item): abort(403)
    try:
        if item.classification!='EMERGENCY': raise ValueError('Response status applies to emergency incidents.')
        stage=request.form.get('response_status')
        if stage not in {'CONTACT_ATTEMPTED','RESPONDER_ACKNOWLEDGED','RESPONSE_IN_PROGRESS','COMPLETED'}: raise ValueError('Select a response stage.')
        source=text_field(request.form,'confirmation_source',255)
        incident=db.session.scalar(select(EmergencyIncident).where(EmergencyIncident.complaint_id==item.id))
        allowed={'NOT_CONFIRMED':{'CONTACT_ATTEMPTED','RESPONDER_ACKNOWLEDGED'},'CONTACT_ATTEMPTED':{'RESPONDER_ACKNOWLEDGED'},'RESPONDER_ACKNOWLEDGED':{'RESPONSE_IN_PROGRESS'},'RESPONSE_IN_PROGRESS':{'COMPLETED'},'COMPLETED':set()}
        if stage not in allowed.get(item.response_status,set()): raise ValueError('Record response stages in sequence with actual confirmation.')
        item.response_status=stage;incident.response_status=stage;incident.confirmation_source=source
        db.session.add(ComplaintStatusHistory(complaint_id=item.id,actor_id=current_user.id,from_status=item.status,to_status=item.status,public_response='Officer-recorded response update: '+stage.replace('_',' ').title()+'.',private_notes='Confirmation reference: '+source))
        audit(item,'RESPONSE_STATUS',current_user,'Officer-recorded confirmation; complaint not automatically resolved')
        notify(item,'Emergency response update',f'{item.reference}: an officer-recorded response update is available.');db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('incidents.detail',complaint_id=item.id))


@incidents_bp.post('/<int:complaint_id>/assign')
@admin_required
def assign(complaint_id):
    item=owned(complaint_id)
    try:
        user=db.get_or_404(User,int(request.form.get('user_id','0')))
        if not user.is_active or user.status!='active' or not any(r.name in {'Barangay Official','System Administrator'} for r in user.roles): raise ValueError('Select an active reviewer.')
        for assignment in item.assignments: assignment.active=False
        db.session.add(ComplaintAssignment(complaint_id=item.id,user_id=user.id,assigned_by_id=current_user.id));audit(item,'ASSIGNED',current_user,'Authorized personnel assigned')
        from app.models import Notification
        db.session.add(Notification(user_id=user.id,title='Incident assigned to you',message=f'{item.reference} needs your review.',status='active'))
        if 'ASSIGNED' in TRANSITIONS.get(item.status,set()): transition(item,'ASSIGNED',current_user,'The report has been assigned to authorized barangay personnel.')
        db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('incidents.detail',complaint_id=item.id))


@incidents_bp.post('/<int:complaint_id>/referral')
@official_account_required
def referral(complaint_id):
    item=owned(complaint_id)
    if not can_review(item): abort(403)
    try:
        if item.status in {'CLOSED','RESOLVED'}: raise ValueError('Reopen the complaint before creating a new referral.')
        agency=db.get_or_404(GovernmentAgency,int(request.form.get('agency_id','0')))
        if not agency.active: raise ValueError('Agency is inactive.')
        reason=text_field(request.form,'reason',3000)
        referral=ComplaintReferral(complaint_id=item.id,agency_id=agency.id,approved_by_id=current_user.id,reason=reason)
        db.session.add(referral)
        if item.status!='FOR_EXTERNAL_REFERRAL': transition(item,'FOR_EXTERNAL_REFERRAL',current_user,'A formal referral was approved for preparation. No external handoff has been confirmed.')
        audit(item,'REFERRAL_APPROVED',current_user,'Printable referral approved; no automatic external transmission')
        notify(item,'Referral approved',f'{item.reference}: referral to {agency.name} approved. Open your complaint for next steps.');db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('incidents.detail',complaint_id=item.id))


@incidents_bp.post('/referrals/<int:referral_id>/handoff')
@official_account_required
def handoff(referral_id):
    item=db.get_or_404(ComplaintReferral,referral_id);complaint=owned(item.complaint_id)
    if not can_review(complaint): abort(403)
    try:
        source=text_field(request.form,'handoff_source',255)
        if request.form.get('confirmed')!='yes': raise ValueError('Confirm the documented handoff.')
        if item.transmitted_at: raise ValueError('A handoff has already been recorded.')
        if complaint.status!='FOR_EXTERNAL_REFERRAL': raise ValueError('The complaint must be ready for referral.')
        item.transmitted_at=datetime.now(timezone.utc);item.handoff_source=source;item.status='HANDOFF_RECORDED'
        transition(complaint,'REFERRED_TO_EXTERNAL_AGENCY',current_user,f'Documented referral handoff to {item.agency.name} recorded. Agency response is pending.')
        audit(complaint,'HANDOFF_RECORDED',current_user,'Officer recorded handoff evidence');db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('incidents.detail',complaint_id=complaint.id))


@incidents_bp.post('/referrals/<int:referral_id>/response')
@official_account_required
def agency_response(referral_id):
    referral=db.get_or_404(ComplaintReferral,referral_id);item=owned(referral.complaint_id)
    if not can_review(item): abort(403)
    try:
        if not referral.transmitted_at: raise ValueError('Record the handoff before agency response.')
        referral.response=text_field(request.form,'response',3000);referral.status='RESPONSE_RECORDED'
        db.session.add(ComplaintStatusHistory(complaint_id=item.id,actor_id=current_user.id,from_status=item.status,to_status=item.status,public_response=f'Agency update: {referral.response}'))
        notify(item,'Agency update recorded',f'{item.reference}: an agency update is available.');audit(item,'AGENCY_RESPONSE',current_user,'Officer recorded agency update');db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(url_for('incidents.detail',complaint_id=item.id))


@incidents_bp.get('/referrals/<int:referral_id>/print')
@official_account_required
def referral_print(referral_id):
    referral=db.get_or_404(ComplaintReferral,referral_id);item=owned(referral.complaint_id)
    if not can_review(item): abort(403)
    audit(item,'REFERRAL_PRINT',current_user,'Approved referral rendered for authorized handoff');db.session.commit()
    response=current_app.make_response(render_template('incidents/referral_print.html',referral=referral,item=item));response.headers['Cache-Control']='private, no-store';return response


@incidents_bp.get('/evidence/<int:evidence_id>')
@roles_required('Resident','Barangay Official','System Administrator')
def evidence(evidence_id):
    evidence=db.get_or_404(ComplaintEvidence,evidence_id);item=owned(evidence.complaint_id)
    audit(item,'EVIDENCE_VIEW',current_user,'Private evidence viewed');db.session.commit()
    options = {
        'as_attachment': evidence.mime_type == 'application/pdf',
        'download_name': evidence.original_name,
        'mimetype': evidence.mime_type,
    }
    if evidence.file_data is not None:
        response = send_file(BytesIO(evidence.file_data), **options)
    else:
        response = send_from_directory(
            Path(current_app.config['STORAGE_ROOT']) / 'incident_evidence',
            evidence.filename, **options,
        )
    response.headers['Cache-Control']='private, no-store';response.headers['X-Content-Type-Options']='nosniff';return response


@incidents_bp.route('/directory',methods=['GET','POST'])
@roles_required('Resident','Barangay Official','System Administrator')
def directory():
    ensure_directory();db.session.commit()
    if request.method=='POST':
        if not admin(): abort(403)
        try:
            action=request.form.get('action')
            if action=='agency':
                code=text_field(request.form,'code',30).upper()
                if not re.fullmatch(r'[A-Z0-9_]+',code): raise ValueError('Use letters/numbers/underscores for the agency code.')
                db.session.add(GovernmentAgency(code=code,name=text_field(request.form,'name',180),service_area=text_field(request.form,'coverage',180),jurisdiction=text_field(request.form,'jurisdiction',3000)))
            elif action=='hotline':
                agency=db.get_or_404(GovernmentAgency,int(request.form.get('agency_id','0')))
                number=text_field(request.form,'number',30)
                if not re.fullmatch(r'\+?[0-9 ()\-]{3,30}',number): raise ValueError('Enter a valid telephone number.')
                source=text_field(request.form,'verification_source',500)
                if not source.startswith('https://'): raise ValueError('Enter an official HTTPS verification source.')
                verified=date.fromisoformat(request.form.get('verified_on',''))
                if verified>date.today(): raise ValueError('Verification date cannot be in the future.')
                hotline=db.session.get(AgencyHotline,int(request.form['hotline_id'])) if request.form.get('hotline_id') else AgencyHotline()
                if not hotline: abort(404)
                hotline.agency_id=agency.id;hotline.number=number;hotline.availability=text_field(request.form,'availability',150);hotline.coverage=text_field(request.form,'coverage',180);hotline.verification_source=source;hotline.verified_on=verified;hotline.active=True;hotline.emergency=request.form.get('emergency')=='yes'
                db.session.add(hotline);db.session.flush();db.session.add(HotlineVerification(hotline_id=hotline.id,actor_id=current_user.id,source=source,verified_on=verified))
            elif action=='deactivate': db.get_or_404(AgencyHotline,int(request.form.get('hotline_id','0'))).active=False
            elif action=='agency_toggle':
                agency=db.get_or_404(GovernmentAgency,int(request.form.get('agency_id','0')));agency.active=not agency.active
            else: raise ValueError('Unknown directory action.')
            audit(None,'DIRECTORY_UPDATE',current_user,'Agency/hotline configuration updated');db.session.commit();flash('Directory saved.','success')
        except ValueError as error: db.session.rollback();flash(str(error),'danger')
        return redirect(url_for('incidents.directory'))
    agencies=db.session.scalars(select(GovernmentAgency).order_by(GovernmentAgency.name)).all()
    from app.pagination import paginate_named, paginate_items
    agency_pagination=paginate_named(select(GovernmentAgency).order_by(GovernmentAgency.name,GovernmentAgency.id),'agencies_page')
    hotline_pagination=paginate_named(select(AgencyHotline).order_by(AgencyHotline.id.desc()),'hotlines_page') if admin() else None
    contact_pagination=paginate_items(contacts([a.code for a in agencies]),'contacts_page')
    return render_template('incidents/directory.html',base=layout(),agencies=agencies,agency_rows=agency_pagination.items,
        hotlines=hotline_pagination.items if hotline_pagination else [],verified_contacts=contact_pagination.items,
        agency_pagination=agency_pagination,hotline_pagination=hotline_pagination,contact_pagination=contact_pagination,manage=admin(),today=date.today())


@incidents_bp.route('/rules',methods=['GET','POST'])
@admin_required
def rules():
    ensure_directory()
    if request.method=='POST':
        try:
            rule=db.get_or_404(IncidentRoutingRule,int(request.form.get('rule_id','0')))
            codes=request.form.getlist('agency_codes')
            allowed={a.code for a in db.session.scalars(select(GovernmentAgency)).all()}
            if not codes or any(c not in allowed for c in codes): raise ValueError('Select responsible agencies.')
            classification=request.form.get('classification')
            if classification not in {'EMERGENCY','REFERRAL','BARANGAY','REVIEW'}: raise ValueError('Invalid classification.')
            keywords=[v.strip().casefold() for v in text_field(request.form,'keywords',2000,False).split(',') if v.strip()]
            priority=int(request.form.get('priority','50'))
            if not 0<=priority<=1000: raise ValueError('Priority must be 0â€“1000.')
            rule.agency_codes=codes;rule.classification=classification;rule.keywords=keywords;rule.priority=priority;rule.active=request.form.get('active')=='yes';rule.version+=1
            audit(None,'ROUTING_RULE_UPDATE',current_user,f'Rule {rule.id} version {rule.version}')
            flash('Routing rule saved.','success')
        except ValueError as error: db.session.rollback();flash(str(error),'danger')
    db.session.commit()
    from app.pagination import paginate_named
    pagination=paginate_named(select(IncidentRoutingRule).order_by(IncidentRoutingRule.priority,IncidentRoutingRule.id))
    return render_template('incidents/rules.html',rules=pagination.items,pagination=pagination,agencies=db.session.scalars(select(GovernmentAgency)).all())


@incidents_bp.get('/reports')
@official_account_required
def reports():
    try:
        start=date.fromisoformat(request.args.get('start_date',(date.today()-timedelta(days=30)).isoformat()));end=date.fromisoformat(request.args.get('end_date',date.today().isoformat()))
        if end<start or (end-start).days>366: raise ValueError('Select a valid range up to one year.')
        query=visible_query().where(func.date(ResidentComplaint.created_at)>=start,func.date(ResidentComplaint.created_at)<=end).order_by(ResidentComplaint.created_at,ResidentComplaint.id)
        if request.args.get('format'):
            items=db.session.scalars(query).all()
            audit(None,'REPORT_EXPORT',current_user,'Authorized incident summary exported');db.session.commit()
            return export_report('Barangay Incident Summary',['Reference','Category','Submitted','Priority','Status','Referrals'],[[i.reference,i.category.name,i.created_at.strftime('%Y-%m-%d'),i.classification,i.status,len(i.referrals)] for i in items],request.args['format'])
        from app.pagination import paginate_named
        pagination=paginate_named(query)
        return render_template('incidents/reports.html',base=layout(),items=pagination.items,pagination=pagination,start=start,end=end)
    except ValueError as error: flash(str(error),'danger');return redirect(url_for('incidents.dashboard'))


@incidents_bp.get('/workspace')
@official_account_required
def workspace():
    from .resident_workspace import management_reports
    pagination=management_reports(visible_query(),request.args.get('page',1,type=int),request.args.get('kind',''),request.args.get('q',''))
    return render_template('incidents/workspace.html',base=layout(),reports=pagination.items,pagination=pagination)


@incidents_bp.before_request
def enforce_management_access():
    if current_user.is_authenticated and any(r.name in {'Barangay Official','System Administrator'} for r in current_user.roles):
        from app.permissions import can
        if not can('blotters.manage'):abort(403)
