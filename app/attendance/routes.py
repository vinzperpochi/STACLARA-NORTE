"""Attendance administration and an authenticated, CSRF-exempt device API."""
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import hmac, secrets, ipaddress
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash
from email_validator import validate_email, EmailNotValidError
from app.extensions import db, csrf
from app.auth.decorators import official_account_required, roles_required
from app.models import PersonnelProfile, RFIDCard, AttendanceDevice, AttendanceLog, AttendanceSession, EmployeeSchedule, EmployeeLeave, AttendanceAdjustment, AttendanceAuditLog, User, Role
from app.image_uploads import save_image, remove_image
from app.operations_common import text_field, export_report
from app.pagination import paginate
from .listing import page_size, page_items, page_window, list_url, dashboard_return_url
from .service import scan, uid_hash, daily_rows, attendance_dataset, session_metrics, utc, MANILA, change_duty_days, duty_days_change_date
from . import capture, local_reader
from .voice import response_voice_code

attendance_bp=Blueprint('attendance',__name__,url_prefix='/attendance')


@attendance_bp.after_request
def add_reader_voice_feedback(response):
    """Old clients ignore this field; scan decisions and status codes stay intact."""
    if request.endpoint in {
        'attendance.registration_mode', 'attendance.registration_tap',
        'attendance.device_scan', 'attendance.device_preview',
    }:
        payload=response.get_json(silent=True) if response.is_json else None
        if payload is None and response.status_code>=400 and request.accept_mimetypes.best=='application/json':
            # Flask's default 401/429 pages are HTML, even for the reader client.
            payload={'success':False,'message':'Unable to process the reader request.'}
            response.mimetype='application/json'
        if isinstance(payload,dict):
            payload['voice_code']=response_voice_code(request.endpoint,payload,response.status_code)
            response.set_data(current_app.json.dumps(payload))
    return response


attendance_bp.add_app_template_global(list_url, 'attendance_list_url')
admin_required=roles_required('System Administrator')
BARANGAY_ROLES = ['Barangay Captain', 'Barangay Secretary', 'Barangay Treasurer', 'Barangay Kagawad', 'Barangay Staff', 'Barangay Tanod', 'Lupon Member', 'BHW', 'VAWC Desk Officer', 'SK Official', 'Others']
ATTENDANCE_ACCOUNT_ROLES=('system administrator','barangay official')


def attendance_accounts():
    """Account eligibility is local to attendance; resident account access is unchanged."""
    return select(User).where(User.is_active.is_(True),User.status=='active',
        User.roles.any((Role.status=='active') & func.lower(Role.name).in_(ATTENDANCE_ACCOUNT_ROLES)))


def is_admin(): return any(r.name=='System Administrator' for r in current_user.roles)


def audit(action,entity_id,details):
    db.session.add(AttendanceAuditLog(actor_id=current_user.id,action=action,entity_id=entity_id,details=details))


def people_query():
    query=select(PersonnelProfile).options(selectinload(PersonnelProfile.schedules))
    if not is_admin(): query=query.where(PersonnelProfile.user_id==current_user.id)
    if request.args.get('department'): query=query.where(PersonnelProfile.department==request.args['department'])
    if request.args.get('personnel_id',type=int): query=query.where(PersonnelProfile.id==request.args.get('personnel_id',type=int))
    if request.args.get('q'): query=query.where(PersonnelProfile.full_name.ilike('%'+request.args['q'][:100]+'%'))
    return query.order_by(PersonnelProfile.full_name,PersonnelProfile.id)


@attendance_bp.get('/')
@official_account_required
def dashboard():
    try: day=date.fromisoformat(request.args.get('date',datetime.now(MANILA).date().isoformat()))
    except ValueError: abort(400)
    import calendar
    people=db.session.scalars(people_query()).all()
    period=request.args.get('period',7,type=int)
    if period not in {7,30,90}: period=7
    cache=attendance_dataset(min(day.replace(day=1),day-timedelta(days=period-1)),day.replace(day=calendar.monthrange(day.year,day.month)[1]),people)
    rows=daily_rows(day,people,cache)
    present=sum(bool(r['sessions']) for r in rows);scheduled=sum(r['scheduled'] and r['status']!='On leave' for r in rows)
    stats={'Personnel':len(people),'Present':present,'Absent':sum(r['status']=='Absent' for r in rows),'Late':sum(r['late_minutes']>0 for r in rows),'On leave':sum(r['status']=='On leave' for r in rows),'Clocked in':sum(r['status']=='Clocked in' for r in rows),'Working hours':round(sum(r['worked_minutes'] for r in rows)/60,2),'Attendance %':round(100*present/scheduled,1) if scheduled else 0}
    ids=[p.id for p in people]
    log_query=select(AttendanceLog)
    if not is_admin() or any(request.args.get(key) for key in ['q','department','personnel_id']): log_query=log_query.where(AttendanceLog.personnel_id.in_(ids))
    feed_pagination=paginate(log_query.options(selectinload(AttendanceLog.personnel)).order_by(AttendanceLog.created_at.desc(),AttendanceLog.id.desc()),request.args.get('feed_page',1,type=int),5)
    trends=[{'date':(day-timedelta(days=offset)).isoformat(),'present':sum(bool(r['sessions']) for r in daily_rows(day-timedelta(days=offset),people,cache))} for offset in range(period-1,-1,-1)]
    departments={p.department:sum(bool(r['sessions']) for r in rows if r['person'].department==p.department) for p in people}
    month_days=[{'date':day.replace(day=d),'present':sum(bool(r['sessions']) for r in daily_rows(day.replace(day=d),people,cache))} for d in range(1,calendar.monthrange(day.year,day.month)[1]+1)]
    statuses=['Clocked in','Present','Late','Absent','On leave','Awaiting scan','Off duty']
    status=request.args.get('status','')
    visible_rows=[row for row in rows if row['status']==status] if status in statuses else rows
    pagination=page_items(visible_rows)
    leave_query=select(EmployeeLeave).where(EmployeeLeave.personnel_id.in_(ids)).options(selectinload(EmployeeLeave.personnel)).order_by(EmployeeLeave.created_at.desc(),EmployeeLeave.id.desc())
    leave_pagination=paginate(leave_query,request.args.get('leave_page',1,type=int),5)
    missing_personnel_link=not is_admin() and not people and db.session.scalar(select(PersonnelProfile.id).where(PersonnelProfile.user_id==current_user.id)) is None
    response=current_app.make_response(render_template('attendance/dashboard.html',rows=pagination.items,pagination=pagination,people=people,statuses=statuses,stats=stats,day=day,logs=feed_pagination.items,feed_pagination=feed_pagination,trends=trends,period=period,month_days=month_days,calendar_offset=day.replace(day=1).weekday(),departments=departments,manage=is_admin(),metrics=session_metrics,leaves=leave_pagination.items,leave_pagination=leave_pagination,missing_personnel_link=missing_personnel_link))
    response.headers['Cache-Control']='private, no-store'
    return response


@attendance_bp.route('/personnel',methods=['GET','POST'])
@admin_required
def personnel():
    if request.method=='POST':
        flash('Use the combined Personnel & RFID form to save the person, schedule and scanned card together.','info')
    return redirect(url_for('attendance.devices'),code=303 if request.method=='POST' else 302)


@attendance_bp.route('/personnel/<int:personnel_id>',methods=['GET','POST'])
@admin_required
def personnel_detail(personnel_id):
    person=db.get_or_404(PersonnelProfile,personnel_id)
    if request.method=='POST':
        try:
            action=request.form.get('action')
            details='Personnel configuration updated; attendance history retained'
            if action=='active': person.active=not person.active
            elif action=='details':
                for key,limit in [('full_name',200),('position',100),('department',100),('mobile',30),('employment_status',40)]: setattr(person,key,text_field(request.form,key,limit,key in {'full_name','position'}))
                email=text_field(request.form,'email',255,False)
                person.email=validate_email(email,check_deliverability=False).normalized if email else ''
                if person.mobile and not person.mobile.replace('+','').isdigit(): raise ValueError('Enter a valid mobile number.')
            elif action=='card':
                digest,suffix=uid_hash(request.form.get('rfid_uid',''))
                if db.session.scalar(select(RFIDCard).where(RFIDCard.uid_hash==digest)): raise ValueError('Card already registered; use a new RFID UID.')
                for card in person.cards: card.active=False;card.revoked_at=datetime.now(timezone.utc)
                db.session.flush()
                db.session.add(RFIDCard(personnel_id=person.id,uid_hash=digest,uid_suffix=suffix))
            elif action=='link_account':
                if person.user_id is not None: raise ValueError('This personnel record already has a system account. The saved account link cannot be overwritten here.')
                try: user_id=int(request.form.get('user_id',''))
                except (ValueError,TypeError): raise ValueError('Select an active account to link.')
                account=db.session.scalar(attendance_accounts().where(User.id==user_id).with_for_update())
                if not account: raise ValueError('Select an active official or staff account. Resident accounts are not eligible for RFID attendance.')
                person=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.id==personnel_id).with_for_update().execution_options(populate_existing=True))
                if person.user_id is not None: raise ValueError('This personnel record already has a saved account link.')
                if db.session.scalar(select(PersonnelProfile.id).where(PersonnelProfile.user_id==account.id)):
                    raise ValueError('That account already has a personnel record. Its RFID assignment cannot be duplicated.')
                person.user=account
            elif action=='revoke':
                card=db.get_or_404(RFIDCard,int(request.form.get('card_id','0')))
                if card.personnel_id!=person.id: abort(404)
                card.active=False;card.revoked_at=datetime.now(timezone.utc)
            elif action=='schedule':
                start=time.fromisoformat(request.form.get('start_time',''));end=time.fromisoformat(request.form.get('end_time',''))
                weekdays=[int(v) for v in request.form.getlist('weekdays')]
                if start==end or not weekdays or any(v not in range(7) for v in weekdays): raise ValueError('Select valid hours and work days.')
                options={key:int(request.form.get(key,'0')) for key in ['grace_minutes','cutoff_minutes','minimum_session_minutes','max_sessions']}
                if not 0<=options['grace_minutes']<=120 or not 1<=options['cutoff_minutes']<=1440 or not 1<=options['minimum_session_minutes']<=480 or not 1<=options['max_sessions']<=10: raise ValueError('Invalid schedule limits.')
                effective=date.fromisoformat(request.form.get('effective_from',''));until=date.fromisoformat(request.form['effective_until']) if request.form.get('effective_until') else None
                if until and until<effective: raise ValueError('End date must follow start date.')
                db.session.add(EmployeeSchedule(personnel_id=person.id,name=text_field(request.form,'name',80),start_time=start,end_time=end,weekdays=weekdays,effective_from=effective,effective_until=until,flexible=request.form.get('flexible')=='yes',**options))
            elif action=='schedule_days':
                person=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.id==personnel_id).with_for_update().execution_options(populate_existing=True))
                schedule=db.session.scalar(select(EmployeeSchedule).where(EmployeeSchedule.id==int(request.form.get('schedule_id','0')),EmployeeSchedule.personnel_id==person.id).with_for_update().execution_options(populate_existing=True))
                if not schedule: abort(404)
                old_days=list(schedule.weekdays)
                updated,effective=change_duty_days(schedule,[int(day) for day in request.form.getlist('weekdays')],datetime.now(MANILA).date())
                details=f'Schedule #{schedule.id} duty days {old_days} to {sorted(updated.weekdays)}; resulting schedule #{updated.id}; effective {effective or "unchanged"}; attendance history retained'
            elif action=='schedule_off':
                schedule=db.get_or_404(EmployeeSchedule,int(request.form.get('schedule_id','0')))
                if schedule.personnel_id!=person.id: abort(404)
                # End future applicability without erasing historical schedule calculations.
                today=datetime.now(MANILA).date()
                if schedule.effective_from>=today: schedule.active=False
                else: schedule.effective_until=today-timedelta(days=1)
            elif action=='pin':
                pin=text_field(request.form,'pin',32)
                if not pin.isdigit() or len(pin)<6: raise ValueError('PIN must contain at least six digits.')
                person.pin_hash=generate_password_hash(pin)
            else: raise ValueError('Unknown action.')
            audit('PERSONNEL_'+action.upper(),person.id,details);db.session.commit();flash('Saved.','success')
        except ValueError as error: db.session.rollback();flash(str(error),'danger')
        except IntegrityError: db.session.rollback();flash('This RFID card or account already has an assignment. The saved records were not changed.','danger')
        return redirect(url_for('attendance.personnel_detail',personnel_id=person.id))
    available_accounts=db.session.scalars(attendance_accounts().where(~select(PersonnelProfile.id).where(PersonnelProfile.user_id==User.id).exists()).order_by(User.username)).all() if person.user_id is None else []
    today=datetime.now(MANILA).date()
    card_pagination=paginate(select(RFIDCard).where(RFIDCard.personnel_id==person.id).order_by(RFIDCard.active.desc(),RFIDCard.id.desc()),request.args.get('cards_page',1,type=int),5)
    schedule_pagination=paginate(select(EmployeeSchedule).where(EmployeeSchedule.personnel_id==person.id).order_by(EmployeeSchedule.active.desc(),EmployeeSchedule.effective_from.desc(),EmployeeSchedule.id.desc()),request.args.get('schedules_page',1,type=int),5)
    change_dates={schedule.id:duty_days_change_date(schedule,today) for schedule in schedule_pagination.items}
    return render_template('attendance/personnel_detail.html',person=person,today=today,available_accounts=available_accounts,schedule_change_dates=change_dates,card_pagination=card_pagination,schedule_pagination=schedule_pagination)


@attendance_bp.route('/devices',methods=['GET','POST'])
@admin_required
def devices():
    photo=None;old_photo=None;committed=False;inactive_person=None;existing_assignment=None;registration_error=None
    if request.method=='POST':
        try:
            action=request.form.get('action','register_card')
            if action=='register_card':
                captured=capture.get(request.form.get('capture_id',''),current_user.id)
                if captured['state']!='captured': raise ValueError('Scan a card using the scan button before registering.')
                digest,suffix=captured['digest'],captured['suffix']
                if db.session.scalar(select(RFIDCard).where(RFIDCard.uid_hash==digest)): raise ValueError('This RFID UID already exists in card history (active or revoked). Use an unregistered card/tag.')
                first=text_field(request.form,'first_name',100);last=text_field(request.form,'last_name',99)
                role=request.form.get('barangay_role','')
                if role not in BARANGAY_ROLES: raise ValueError('Select a barangay role.')
                if role=='Others': role=text_field(request.form,'other_role',100)
                name=' '.join(f'{first} {last}'.split())
                account_mode=request.form.get('account_mode','none')
                if account_mode not in {'existing','none'}: raise ValueError('Choose whether this person has a system account.')
                if db.engine.dialect.name=='postgresql':
                    lock_key=int.from_bytes(sha256(('rfid-person:'+name.casefold()).encode()).digest()[:8],signed=True)
                    db.session.execute(select(func.pg_advisory_xact_lock(lock_key)))
                linked_person=None;account=None
                if account_mode=='existing':
                    try: user_id=int(request.form.get('user_id',''))
                    except (ValueError,TypeError): raise ValueError('Select the person\'s existing system account.')
                    account=db.session.scalar(attendance_accounts().where(User.id==user_id).with_for_update())
                    if not account: raise ValueError('Select an active system account for an official or staff member. Resident accounts are not eligible for RFID attendance.')
                    linked_person=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.user_id==account.id))
                matches=db.session.scalars(select(PersonnelProfile).where(func.lower(PersonnelProfile.full_name)==name.lower())).all()
                if len(matches)>1: raise ValueError('Several personnel records have this name. Open the correct record under Personnel to manage its cards.')
                named_person=matches[0] if matches else None
                if linked_person and named_person and named_person.id!=linked_person.id:
                    raise ValueError('The selected account and entered name belong to different personnel records. Check the account and name.')
                person=linked_person or named_person
                if person:
                    person=db.session.scalar(select(PersonnelProfile).where(PersonnelProfile.id==person.id).with_for_update().execution_options(populate_existing=True))
                if person and person.cards:
                    existing_assignment=person
                    raise ValueError('This personnel/user already has an RFID registration. Open Manage record to view the saved card, link an account, or replace it. Do not register the person again.')
                if person and person.user_id is not None:
                    if account is None: raise ValueError('This personnel record already has a linked account. Choose Has a system account and select it.')
                    if person.user_id!=account.id: raise ValueError('This personnel record is already linked to another system account.')
                if person and person.user and (not person.user.is_active or person.user.status!='active'):
                    raise ValueError('The linked system account is inactive. Activate that account before linking an RFID card.')
                if person and not person.active:
                    inactive_person=person
                    if request.form.get('reactivate_personnel')!='yes' or request.form.get('reactivate_personnel_id')!=str(person.id):
                        raise ValueError('This existing personnel record is inactive. Tick Reactivate this personnel record below, then save again. Your scanned card is retained while valid.')
                    person.active=True
                    audit('PERSONNEL_REACTIVATED',person.id,'Super Admin explicitly reactivated the personnel record while registering a scanned card')
                if person is None:
                    person=PersonnelProfile(user=account,employee_id='RFID-'+secrets.token_hex(6).upper(),full_name=name,photo_filename='',position=role,personnel_type='Official' if role!='Barangay Staff' else 'Staff',department='',mobile='',email='',employment_status='')
                    db.session.add(person);db.session.flush()
                elif account is not None:
                    person.user=account
                if not person.schedules:
                    try:
                        start=time.fromisoformat(request.form.get('start_time',''))
                        end=time.fromisoformat(request.form.get('end_time',''))
                        effective=date.fromisoformat(request.form.get('effective_from',''))
                        weekdays=sorted(set(int(value) for value in request.form.getlist('weekdays')))
                        grace=int(request.form.get('grace_minutes','15'))
                    except (ValueError,TypeError): raise ValueError('Set the first work schedule: valid start/end time, effective date, work days and grace minutes.')
                    if start==end or not weekdays or any(day not in range(7) for day in weekdays) or not 0<=grace<=120:
                        raise ValueError('Select different shift start/end times, at least one work day and grace minutes from 0 to 120.')
                    db.session.add(EmployeeSchedule(personnel_id=person.id,name='Primary schedule',start_time=start,end_time=end,weekdays=weekdays,effective_from=effective,grace_minutes=grace))
                for key,limit in [('department',100),('mobile',30),('email',255),('employment_status',40),('employee_id',50)]:
                    value=text_field(request.form,key,limit,False)
                    if not value: continue
                    if key=='email': value=validate_email(value,check_deliverability=False).normalized
                    if key=='mobile' and not value.replace('+','').isdigit(): raise ValueError('Enter a valid mobile number.')
                    if key=='employee_id' and db.session.scalar(select(PersonnelProfile.id).where(PersonnelProfile.employee_id==value,PersonnelProfile.id!=person.id)):
                        raise ValueError('Employee ID is already assigned to another person.')
                    setattr(person,key,value)
                if request.files.get('photo') and request.files['photo'].filename:
                    photo=save_image(request.files['photo'],'profile_photos');old_photo=person.photo_filename;person.photo_filename=photo
                person.full_name=name;person.position=role
                db.session.add(RFIDCard(personnel_id=person.id,uid_hash=digest,uid_suffix=suffix))
                audit('CARD_REGISTERED',person.id,'Personnel, schedule and scanned RFID saved together; '+(f'linked to system account #{account.id}' if account else 'registered without a system account'));db.session.commit();committed=True
                capture.finish(request.form['capture_id'],current_user.id,'consumed')
                remove_image('profile_photos',old_photo)
                flash(f'Personnel record, schedule and RFID card ending {suffix} saved for {person.full_name}.','success')
                return redirect(url_for('attendance.devices',registered=person.id))
            else:
                raise ValueError('Unknown registration action.')
        except (ValueError,EmailNotValidError) as error:
            db.session.rollback()
            if not committed: remove_image('profile_photos',photo)
            registration_error=str(error);flash(registration_error,'danger')
        except IntegrityError:
            db.session.rollback()
            if not committed: remove_image('profile_photos',photo)
            registration_error='The card, account or employee ID was just registered. Check the existing record before trying again.'
            flash(registration_error,'danger')
        except Exception:
            db.session.rollback()
            if not committed: remove_image('profile_photos',photo)
            raise
    directory_query=select(PersonnelProfile).options(selectinload(PersonnelProfile.user),selectinload(PersonnelProfile.cards),selectinload(PersonnelProfile.schedules))
    search=request.args.get('q','').strip()[:100]
    if search: directory_query=directory_query.where(or_(PersonnelProfile.full_name.ilike('%'+search+'%'),PersonnelProfile.employee_id.ilike('%'+search+'%')))
    if request.args.get('department'): directory_query=directory_query.where(PersonnelProfile.department==request.args['department'])
    if request.args.get('active') in ('yes','no'): directory_query=directory_query.where(PersonnelProfile.active.is_(request.args['active']=='yes'))
    pagination=paginate(directory_query.order_by(PersonnelProfile.full_name,PersonnelProfile.id),request.args.get('page',1,type=int),page_size())
    total_personnel=db.session.scalar(select(func.count(PersonnelProfile.id))) or 0
    accounts=db.session.scalars(attendance_accounts().options(selectinload(User.roles),selectinload(User.official)).order_by(User.username)).all()
    linked_profiles=db.session.scalars(select(PersonnelProfile).where(PersonnelProfile.user_id.in_([account.id for account in accounts])).options(selectinload(PersonnelProfile.cards))).all()
    profiles={person.user_id:person for person in linked_profiles}
    account_options=[]
    for account in accounts:
        profile=profiles.get(account.id)
        saved_cards=sorted(profile.cards,key=lambda card:card.id) if profile else []
        active_card=next((card for card in saved_cards if card.active),None)
        shown_card=active_card or (saved_cards[-1] if saved_cards else None)
        name=profile.full_name if profile else (account.official.full_name if account.official else '')
        first,last=name.rsplit(' ',1) if ' ' in name else (name,'')
        account_options.append({'id':account.id,'username':account.username,'email':account.email,'roles':', '.join(role.name for role in account.roles),'first_name':first,'last_name':last,'position':profile.position if profile else (account.official.position if account.official else ''),'personnel_id':profile.id if profile else None,'personnel_active':profile.active if profile else True,'personnel_name':profile.full_name if profile else ''})
        account_options[-1].update(rfid_registered=bool(saved_cards),rfid_suffix=shown_card.uid_suffix if shown_card else '',rfid_active=bool(active_card))
    active_cards=db.session.scalar(select(func.count(RFIDCard.id)).where(RFIDCard.active.is_(True))) or 0
    retained_capture=None
    if request.method=='POST' and not committed and request.form.get('capture_id'):
        try:
            previous=capture.get(request.form['capture_id'],current_user.id)
            if previous['state']=='captured': retained_capture=previous
        except ValueError: pass
    registered=db.session.get(PersonnelProfile,request.args.get('registered',type=int)) if request.args.get('registered',type=int) else None
    registered=(registered if registered and registered.cards else None) or existing_assignment
    response=current_app.make_response(render_template('attendance/devices.html',people=pagination.items,pagination=pagination,total_personnel=total_personnel,active_cards=active_cards,barangay_roles=BARANGAY_ROLES,today=datetime.now(MANILA).date(),account_options=account_options,inactive_person=inactive_person,retained_capture=retained_capture,registered=registered,registration_error=registration_error))
    response.headers['Cache-Control']='private, no-store';return response


@attendance_bp.post('/registration/start')
@admin_required
def registration_start():
    try:
        if local_reader.enabled():
            device=local_reader.ensure(current_user.id)
        else:
            readers=db.session.scalars(select(AttendanceDevice).where(AttendanceDevice.active.is_(True))).all()
            if len(readers)!=1: raise ValueError('A single reader must be configured by the system administrator.')
            device=readers[0]
        return jsonify(capture_id=capture.begin(device.id,current_user.id))
    except (ValueError,TypeError) as error: return jsonify(message=str(error)),409


@attendance_bp.get('/registration/<token>')
@admin_required
def registration_status(token):
    try:
        value=capture.get(token,current_user.id)
        response=jsonify(state=value['state'],ready=value['ready'],suffix=value['suffix'],message=value['message'])
        response.headers['Cache-Control']='no-store'
        return response
    except ValueError as error: return jsonify(message=str(error)),404


@attendance_bp.post('/registration/<token>/cancel')
@admin_required
def registration_cancel(token):
    capture.finish(token,current_user.id)
    return jsonify(success=True)


@attendance_bp.post('/api/registration-mode')
@csrf.exempt
def registration_mode():
    device=authenticated_device()
    if request.content_length and request.content_length>4096: abort(413)
    data=request.get_json(silent=True)
    if data is not None and not isinstance(data,dict): return jsonify(message='Send a JSON object.'),400
    data=data or {}
    feedback=None
    acknowledged=None
    try:
        if data.get('ack_capture_id'):
            result=capture.reader_feedback(device.id,data['ack_capture_id'],acknowledge=True)
            if result['acknowledged']: acknowledged=data['ack_capture_id']
        if data.get('watch_capture_id'):
            feedback=capture.reader_feedback(device.id,data['watch_capture_id'])
        else:
            feedback=capture.next_reader_feedback(device.id)
    except ValueError as error:
        return jsonify(message=str(error)),400
    device.last_seen_at=datetime.now(timezone.utc);db.session.commit()
    return jsonify(capture_id=capture.mode(device.id),registration_feedback=feedback,feedback_acknowledged=acknowledged,time=datetime.now(timezone.utc).isoformat())


@attendance_bp.post('/api/registration-tap')
@csrf.exempt
def registration_tap():
    device=authenticated_device()
    if request.content_length and request.content_length>8192: abort(413)
    data=request.get_json(silent=True)
    if not isinstance(data,dict): return jsonify(message='Send a JSON scan.'),400
    try:
        digest,suffix=uid_hash(data.get('uid'))
        known_card=db.session.scalar(select(RFIDCard).where(RFIDCard.uid_hash==digest))
        duplicate=known_card is not None
        capture.receive(str(data.get('capture_id','')),device.id,digest,suffix,duplicate)
        return jsonify(success=not duplicate,registration=True,employee=known_card.personnel.full_name if known_card else None,message='Card already registered. Tap another card.' if duplicate else 'Card captured for registration.')
    except ValueError as error: return jsonify(success=False,registration=True,message=str(error)),400


def authenticated_device():
    if request.headers.get('X-RFID-Local-Test')=='1':
        device=local_reader.authenticate()
    else:
        device=credential_device()
    recent=db.session.scalar(select(func.count(AttendanceLog.id)).where(AttendanceLog.device_id==device.id,AttendanceLog.created_at>=datetime.now(timezone.utc)-timedelta(minutes=1)))
    if recent>=120: abort(429)
    return device


def credential_device():
    try:
        local=ipaddress.ip_address(request.remote_addr or '').is_loopback
    except ValueError: local=False
    if not request.is_secure and not local: abort(403,description='HTTPS is required for remote attendance devices.')
    raw=request.headers.get('Authorization','')
    if not raw.startswith('Bearer ') or ':' not in raw: abort(401)
    device_id,token=raw[7:].split(':',1)
    if not device_id.isdigit() or len(device_id)>10 or len(token)>100: abort(401)
    device=db.session.get(AttendanceDevice,int(device_id))
    if not device or not device.active or not hmac.compare_digest(device.credential_hash,sha256(token.encode()).hexdigest()): abort(401)
    if device.hardware=='Development test only' and not current_app.config.get('ATTENDANCE_DEV_MODE'): abort(403)
    return device


@attendance_bp.post('/api/scan')
@csrf.exempt
def device_scan():
    device=authenticated_device()
    if request.content_length and request.content_length>8192: abort(413)
    data=request.get_json(silent=True)
    if not isinstance(data,dict): return jsonify(success=False,message='Send a JSON scan event.'),400
    try:
        occurred=datetime.fromisoformat(data['occurred_at'].replace('Z','+00:00')) if data.get('occurred_at') else None
        if occurred and occurred.tzinfo is None: raise ValueError('Offline events must include a timezone.')
        if capture.blocks_attendance(device.id,(occurred or datetime.now(timezone.utc)).timestamp()):
            return jsonify(success=False,message='Reader reserved for RFID registration. Finish or cancel registration before attendance.'),409
        event,replayed=scan(device,data.get('event_id'),data.get('uid'),occurred,data.get('pin'),data.get('action','AUTO'))
        db.session.commit()
        return jsonify(success=event.accepted,replayed=replayed,event_id=event.event_id,action=event.action,message=event.message,employee=event.personnel.full_name if event.accepted else None,time=utc(event.occurred_at).astimezone(MANILA).isoformat()),200 if event.accepted else 422
    except (ValueError,TypeError) as error:
        db.session.rollback();return jsonify(success=False,message=str(error)),400


@attendance_bp.post('/api/preview')
@csrf.exempt
def device_preview():
    """Read the next action without clocking in; the final scan revalidates it."""
    device=authenticated_device()
    if request.content_length and request.content_length>8192: abort(413)
    data=request.get_json(silent=True)
    if not isinstance(data,dict): return jsonify(success=False,message='Send a JSON card lookup.'),400
    owner_name=None
    try:
        now=datetime.now(timezone.utc)
        if capture.blocks_attendance(device.id,now.timestamp()):
            return jsonify(success=False,message='Reader is reserved for card registration.'),409
        digest,_=uid_hash(data.get('uid'))
        card=db.session.scalar(select(RFIDCard).where(RFIDCard.uid_hash==digest,RFIDCard.active.is_(True)))
        if not card: raise ValueError('Unregistered or revoked RFID card.')
        person=card.personnel
        owner_name=person.full_name
        if not person.active or (person.user and (not person.user.is_active or person.user.status!='active')): raise ValueError('Personnel account is inactive.')
        if device.require_pin: raise ValueError('This reader requires an employee PIN. Use a PIN-capable client or disable the reader PIN requirement.')
        opened=db.session.scalar(select(AttendanceSession).where(AttendanceSession.personnel_id==person.id,AttendanceSession.time_out.is_(None)))
        if not opened:
            from .service import schedule_for
            schedule_for(person,now)
        device.last_seen_at=now;db.session.commit()
        response=jsonify(success=True,employee=person.full_name,action='OUT' if opened else 'IN')
        response.headers['Cache-Control']='no-store'
        return response
    except (ValueError,TypeError) as error:
        db.session.rollback();return jsonify(success=False,employee=owner_name,message=str(error)),422


@attendance_bp.post('/api/heartbeat')
@csrf.exempt
def heartbeat():
    device=authenticated_device();device.last_seen_at=datetime.now(timezone.utc);db.session.commit()
    return jsonify(success=True,device_id=device.id,hardware=device.hardware,require_pin=device.require_pin,time=datetime.now(timezone.utc).isoformat())


@attendance_bp.post('/leave')
@official_account_required
def leave():
    try:
        person=db.get_or_404(PersonnelProfile,int(request.form.get('personnel_id','0')))
        if not is_admin() and person.user_id!=current_user.id: abort(403)
        start=date.fromisoformat(request.form.get('start_date',''));end=date.fromisoformat(request.form.get('end_date',''))
        if end<start or (end-start).days>366: raise ValueError('Select a valid leave range up to one year.')
        item=EmployeeLeave(personnel_id=person.id,start_date=start,end_date=end,reason=text_field(request.form,'reason',255));db.session.add(item);db.session.flush();audit('LEAVE_REQUESTED',item.id,'Leave request submitted');db.session.commit()
    except ValueError as error: db.session.rollback();flash(str(error),'danger')
    return redirect(dashboard_return_url('leave-requests'))


@attendance_bp.post('/leave/<int:leave_id>')
@admin_required
def approve_leave(leave_id):
    item=db.get_or_404(EmployeeLeave,leave_id)
    if request.form.get('status') not in {'approved','rejected'}: abort(400)
    item.status=request.form['status'];item.approved_by_id=current_user.id;audit('LEAVE_'+item.status.upper(),item.id,'Leave decision recorded');db.session.commit()
    return redirect(dashboard_return_url('leave-requests'))


@attendance_bp.post('/sessions/<int:session_id>/adjust')
@admin_required
def adjust(session_id):
    session=db.get_or_404(AttendanceSession,session_id)
    try:
        reason=text_field(request.form,'reason',2000)
        before={'time_in':utc(session.time_in).isoformat(),'time_out':utc(session.time_out).isoformat() if session.time_out else None,'overtime_approved':session.overtime_approved}
        start=datetime.fromisoformat(request.form['time_in']).replace(tzinfo=MANILA).astimezone(timezone.utc)
        end=datetime.fromisoformat(request.form['time_out']).replace(tzinfo=MANILA).astimezone(timezone.utc) if request.form.get('time_out') else None
        if end and (end<=start or end-start>timedelta(hours=24)): raise ValueError('Time out must follow time in within 24 hours.')
        if start.astimezone(MANILA).date() not in {session.work_date,session.work_date+timedelta(days=1)}: raise ValueError('Correction must stay within the work date/overnight shift.')
        others=db.session.scalars(select(AttendanceSession).where(AttendanceSession.personnel_id==session.personnel_id,AttendanceSession.id!=session.id)).all()
        if any((end is None or utc(other.time_in)<end) and (other.time_out is None or utc(other.time_out)>start) for other in others): raise ValueError('Correction overlaps another attendance session.')
        session.time_in=start;session.time_out=end;session.overtime_approved=request.form.get('overtime_approved')=='yes'
        from .service import bounds
        scheduled_start,_=bounds(session.schedule,session.work_date);session.late_minutes=0 if session.schedule.flexible else max(0,int((start-scheduled_start).total_seconds()/60)-session.schedule.grace_minutes)
        after={'time_in':start.isoformat(),'time_out':end.isoformat() if end else None,'overtime_approved':session.overtime_approved}
        db.session.add(AttendanceAdjustment(session_id=session.id,actor_id=current_user.id,reason=reason,before=before,after=after));audit('SESSION_ADJUSTED',session.id,'Adjustment recorded with original values retained');db.session.commit()
    except (ValueError,KeyError) as error: db.session.rollback();flash(str(error),'danger')
    return redirect(dashboard_return_url('daily-records',date=session.work_date.isoformat()))


@attendance_bp.get('/reports')
@official_account_required
def reports():
    try:
        start=date.fromisoformat(request.args.get('start_date',datetime.now(MANILA).date().isoformat()));end=date.fromisoformat(request.args.get('end_date',start.isoformat()))
        if end<start or (end-start).days>366: raise ValueError('Select a range up to one year.')
        people=db.session.scalars(people_query()).all();rows=[]
        if request.args.get('format'):
            cache=attendance_dataset(start,end,people)
            for offset in range((end-start).days+1): rows.extend(daily_rows(start+timedelta(days=offset),people,cache))
            values=[[r['person'].employee_id,r['person'].full_name,r['person'].position,r['person'].department,r['date'].isoformat(),', '.join(utc(s.time_in).astimezone(MANILA).strftime('%H:%M') for s in r['sessions']),', '.join(utc(s.time_out).astimezone(MANILA).strftime('%H:%M') if s.time_out else 'Open' for s in r['sessions']),round(r['worked_minutes']/60,2),r['late_minutes'],r['overtime_minutes'],r['undertime_minutes'],r['status']] for r in rows]
            return export_report('Barangay Daily Time Record (Asia/Manila)',['ID','Name','Position','Department','Date','Time in','Time out','Hours','Late min','OT min','Undertime min','Status'],values,request.args['format'])
        pagination=page_window(len(people)*((end-start).days+1))
        if people:
            # Calculate only the visible date/person pairs; exports still include all matches.
            first=(pagination.page-1)*pagination.per_page
            stop=min(first+pagination.per_page,pagination.total)
            groups=[]
            for offset in range(first//len(people),(stop-1)//len(people)+1):
                lo=max(0,first-offset*len(people));hi=min(len(people),stop-offset*len(people))
                groups.append((start+timedelta(days=offset),people[lo:hi]))
            visible_people={person.id:person for _,group in groups for person in group}
            cache=attendance_dataset(groups[0][0],groups[-1][0],list(visible_people.values()))
            for day,group in groups: rows.extend(daily_rows(day,group,cache))
        options_query=select(PersonnelProfile).order_by(PersonnelProfile.full_name)
        if not is_admin(): options_query=options_query.where(PersonnelProfile.user_id==current_user.id)
        personnel_options=db.session.scalars(options_query).all()
        response=current_app.make_response(render_template('attendance/reports.html',rows=rows,pagination=pagination,start=start,end=end,manage=is_admin(),personnel_options=personnel_options))
        response.headers['Cache-Control']='private, no-store'
        return response
    except ValueError as error: flash(str(error),'danger');return redirect(url_for('attendance.dashboard'))


@attendance_bp.get('/personnel/<int:personnel_id>/photo')
@official_account_required
def photo(personnel_id):
    person=db.get_or_404(PersonnelProfile,personnel_id)
    if not is_admin() and person.user_id!=current_user.id: abort(403)
    if not person.photo_filename:
        return current_app.response_class('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80"><rect width="80" height="80" fill="#e5eee7"/><circle cx="40" cy="28" r="14" fill="#60816a"/><path d="M12 78a28 28 0 0156 0" fill="#60816a"/></svg>',mimetype='image/svg+xml',headers={'Cache-Control':'private, no-store'})
    response=send_from_directory(current_app.config['STORAGE_ROOT']+'/profile_photos',person.photo_filename)
    response.headers['Cache-Control']='private, no-store';return response
