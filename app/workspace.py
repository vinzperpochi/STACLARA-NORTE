"""Account-owned notifications, profile images, and real calendar data."""
if __name__ == "__main__":
    # IDE "Run Python File" may execute this blueprint instead of run.py.
    # Delegate before importing Flask or any application modules.
    import runpy
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    print("Launching the application through run.py...", flush=True)
    runpy.run_path(str(project_root / "run.py"), run_name="__main__")
    raise SystemExit(0)

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import func, or_
from app.extensions import db
from app.models import Event, Notification, Resident, User
from app.permissions import permission_required, can
from app.image_uploads import save_image, remove_image
from app.audit import record

workspace_bp = Blueprint('workspace', __name__, url_prefix='/workspace')


@workspace_bp.get('/notifications')
@permission_required('workspace')
def notifications():
    items = db.session.scalars(db.select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(25)).all()
    unread = db.session.scalar(db.select(func.count(Notification.id)).where(Notification.user_id == current_user.id, Notification.is_read.is_(False)))
    return jsonify(success=True, data={'unread': unread, 'items': [{'id': n.id, 'title': n.title, 'message': n.message, 'is_read': n.is_read, 'created_at': n.created_at.replace(tzinfo=timezone.utc).isoformat()} for n in items]})


@workspace_bp.post('/notifications/read')
@permission_required('workspace')
def notification_read():
    notification_id = request.form.get('id', type=int)
    query = db.select(Notification).where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    elif request.form.get('all') != '1':
        return jsonify(success=False, message='Select a notification.'), 400
    items = db.session.scalars(query).all()
    if notification_id is not None and not items:
        item = db.session.scalar(db.select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id))
        if item is None:
            abort(404)
    for item in items:
        item.is_read = True
        item.read_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(success=True, data={'updated': len(items)})


@workspace_bp.get('/calendar')
@permission_required('workspace')
def calendar():
    zone = ZoneInfo(current_app.config['SYSTEM_TIMEZONE'])
    now = datetime.now(zone)
    try:
        year = int(request.args.get('year', now.year))
        month = int(request.args.get('month', now.month))
        if not 1900 <= year <= 2200:
            raise ValueError()
        start = datetime(year, month, 1, tzinfo=zone)
        end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=zone)
    except (TypeError, ValueError):
        return jsonify(success=False, message='Invalid calendar month.'), 400
    statuses = ['active', 'PUBLISHED', 'published']
    events = db.session.scalars(db.select(Event).where(Event.status.in_(statuses), Event.starts_at < end.astimezone(timezone.utc), or_(Event.ends_at >= start.astimezone(timezone.utc), (Event.ends_at.is_(None) & (Event.starts_at >= start.astimezone(timezone.utc))))).order_by(Event.starts_at, Event.id).limit(200)).all()
    def local(value):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(zone).isoformat()
    return jsonify(success=True, data={'today': now.date().isoformat(), 'timezone': zone.key, 'year': year, 'month': month, 'events': [{'id': e.id, 'title': e.title, 'starts_at': local(e.starts_at), 'ends_at': local(e.ends_at) if e.ends_at else None, 'venue': e.venue} for e in events]})


@workspace_bp.route('/profile', methods=['GET', 'POST'])
@permission_required('workspace')
def profile():
    if request.method == 'POST':
        old_files = {current_user.profile_photo_filename, current_user.resident.profile_photo_filename if current_user.resident else None}
        new = None
        try:
            if request.form.get('remove') == '1':
                current_user.profile_photo_filename = None
            else:
                crop = {key: request.form.get('crop_'+key) for key in ('zoom', 'x', 'y')} if request.form.get('crop_enabled') == '1' else None
                new = save_image(request.files.get('photo'), 'profile_photos', crop=crop)
                current_user.profile_photo_filename = new
            if current_user.resident:
                current_user.resident.profile_photo_filename = current_user.profile_photo_filename
            record('PROFILE_IMAGE_REMOVE' if new is None else 'PROFILE_IMAGE_UPLOAD', 'profile', 'User', current_user.id)
            db.session.commit()
            for old in old_files - {new}:
                remove_image('profile_photos', old)
            flash('Profile image updated.', 'success')
            return redirect(url_for('workspace.profile'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        except Exception:
            db.session.rollback()
            remove_image('profile_photos', new)
            current_app.logger.exception('Profile image update failed')
            flash('Unable to update image. Please try again.', 'danger')
    from app.profile_management import ProfileContactForm, profile_context
    target = current_user.official or current_user.resident
    return render_template('profile_management.html', contact_form=ProfileContactForm(obj=target), **profile_context(current_user))


@workspace_bp.post('/profile/details')
@permission_required('workspace')
def profile_details():
    from app.profile_management import ProfileContactForm, profile_context
    from app.normalization import clean_text
    official, resident = current_user.official, current_user.resident
    allowed = {'contact_number'} if official else ({'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_number'} if resident else set())
    if not allowed or set(request.form) - allowed - {'csrf_token'}:
        abort(400, description='Only the permitted contact fields can be changed here. Use the verified correction workflow for identity and registry changes.')
    form = ProfileContactForm()
    if not form.validate_on_submit():
        flash('Please correct the highlighted contact information.', 'danger')
        return render_template('profile_management.html', contact_form=form, profile_edit=True, **profile_context(current_user)), 400
    target = official or resident
    for key in allowed:
        setattr(target, key, clean_text(getattr(form, key).data) or None)
    record('PROFILE_CONTACT_UPDATE', 'profile', 'Official' if official else 'Resident', target.id, 'Account holder updated permitted contact fields')
    db.session.commit()
    flash('Your contact information has been saved.', 'success')
    return redirect(url_for('workspace.profile', _anchor='contact'))


@workspace_bp.get('/profile-photo')
@permission_required('workspace')
def profile_photo():
    filename = (current_user.resident.profile_photo_filename if current_user.resident else None) or current_user.profile_photo_filename
    if not filename:
        abort(404)
    response = send_from_directory(Path(current_app.config['STORAGE_ROOT']) / 'profile_photos', filename)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@workspace_bp.get('/residents/<int:resident_id>/photo')
@permission_required('workspace')
def resident_photo(resident_id):
    resident = db.get_or_404(Resident, resident_id)
    owner = current_user.resident
    if not can('residents.manage') and not (owner and (owner.id == resident.id or (owner.household_id is not None and owner.household_id == resident.household_id))):
        abort(403)
    filename = resident.profile_photo_filename
    if not filename or Path(filename).name != filename:
        abort(404)
    response = send_from_directory(Path(current_app.config['STORAGE_ROOT']) / 'profile_photos', filename)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@workspace_bp.get('/users/<int:user_id>/photo')
@permission_required('workspace')
def user_photo(user_id):
    if user_id != current_user.id and not can('users.manage'):
        abort(403)
    user = db.get_or_404(User, user_id)
    filename = (user.resident.profile_photo_filename if user.resident else None) or user.profile_photo_filename
    if not filename or Path(filename).name != filename:
        abort(404)
    response = send_from_directory(Path(current_app.config['STORAGE_ROOT']) / 'profile_photos', filename)
    response.headers['Cache-Control'] = 'private, no-store'
    return response
